import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote, urljoin

import requests
from bs4 import BeautifulSoup
from requests import RequestException

from ..amenities import extract_amenities_present
from ..cancellation import raise_if_cancelled
from ..classify import canonical_property_type
from ..http_client import get_session

import os

BASE_URL = "https://www.mubawab.tn"
SOURCE = "mubawab"
MAX_PAGES = 500  # Safety cap; real pagination stops as soon as a batch is empty
PAGE_BATCH_SIZE = int(os.getenv("SCRAPER_PAGE_BATCH_SIZE", "8"))  # Concurrent page fetches per batch
DETAIL_WORKERS = int(os.getenv("SCRAPER_DETAIL_WORKERS", "10"))  # Concurrent detail-page fetches

# Phase order: rent (non-land) first, then sale (non-land), then land (rent+sale)
RENT_CATEGORY = ("rent", "https://www.mubawab.tn/fr/ct/tunis/immobilier-a-louer")
SALE_CATEGORY = ("sale", "https://www.mubawab.tn/fr/ct/tunis/immobilier-a-vendre")
LAND_CATEGORY = ("sale", "https://www.mubawab.tn/fr/sc/terrains-a-vendre")

LISTING_CATEGORIES = (SALE_CATEGORY, RENT_CATEGORY, LAND_CATEGORY)

RENT_KEYWORDS = (
    "à louer",
    "a louer",
    "louer",
    "location",
    "locatio",
    "nuitée",
    "nuité",
    "كراء",
    "للكراء",
    "إيجار",
    "ايجار",
)

SALE_KEYWORDS = (
    "à vendre",
    "a vendre",
    "vendre",
    "vente",
    "للبيع",
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def clean_text(value):
    return " ".join(str(value or "").split())


def _is_truncated(description):
    """Card-listing descriptions are often cut off mid-sentence with a
    trailing "..."/"…", even well past the 300-char "good enough" length
    threshold (e.g. "Prix : 340 000..."). Length alone can't catch this, so
    it forces a detail-page fetch for the real, complete description."""
    return str(description or "").rstrip().endswith(("...", "…"))


def parse_number(value):
    """Parse a French/Maghreb-formatted number, distinguishing a thousands
    separator from a decimal point.

    Ads write both: thousands-grouped prices ("250.000 DT" -> 250000, always
    grouped in chunks of exactly 3 digits from the right) and decimal areas
    ("150.5 m\u00b2" -> 150, "90,75 m\u00b2" -> 90). Since a real thousands group is
    always exactly 3 digits, a trailing group of 1-2 digits after a separator
    can only be a decimal fraction, not a thousands group - so it's dropped
    (the DB stores area/price as whole numbers, not floats).
    """
    match = re.search(r"\d+(?:[\s\u00a0.,]\d+)*", value or "")
    if not match:
        return None

    groups = re.split(r"[\s\u00a0.,]", match.group(0))
    if len(groups) > 1 and len(groups[-1]) in (1, 2):
        groups = groups[:-1]

    number = "".join(groups)
    return int(number) if number else None


def parse_price(value):
    number = parse_number(value)
    return float(number or 0)


def build_page_url(base_url, page_number):
    if page_number == 1:
        return base_url

    return f"{base_url}:p:{page_number}"


def determine_listing_type(title, description, url, default="sale"):
    text = f"{title} {description} {url}".lower()
    rent_score = sum(1 for keyword in RENT_KEYWORDS if keyword in text)
    sale_score = sum(1 for keyword in SALE_KEYWORDS if keyword in text)

    if rent_score > sale_score:
        return "rent"
    if sale_score > rent_score:
        return "sale"
    if "louer" in url.lower():
        return "rent"
    if "vendre" in url.lower():
        return "sale"
    return default


_LAND_KEYWORDS = ("terrain", "lotissement", "hectare")
_HOUSE_KEYWORDS = ("maison", "villa", "appartement", "studio", "immeuble", "bureau")


def _first_keyword_type(text):
    """Whichever of land_keywords/house_keywords appears first in `text`
    names the actual property ("Terrain ... ideal pour villa" is land,
    "Maison avec terrain" is a house). Returns "land"/"house"/None (neither
    keyword set present)."""
    text = (text or "").lower()
    land_pos = min((text.find(k) for k in _LAND_KEYWORDS if k in text), default=-1)
    house_pos = min((text.find(k) for k in _HOUSE_KEYWORDS if k in text), default=-1)
    if land_pos != -1 and (house_pos == -1 or land_pos < house_pos):
        return "land"
    if house_pos != -1 and (land_pos == -1 or house_pos < land_pos):
        return "house"
    return None


def determine_property_type(title, description, url):
    # The title is the reliable signal for what is actually being sold. A
    # listing titled "Terrain a vendre a X" is a land ad even when its
    # description mentions building on it ("ideal pour une villa", "convient a
    # un promoteur d'immeuble") -- previously any house keyword anywhere in the
    # description flipped such ads to "house", misclassifying hundreds of
    # terrains. So decide from the title first, then fall back to the same
    # first-mention rule over the full text (title+description+url) when the
    # title alone has neither keyword - previously that fallback path always
    # resolved a tie to "house", reintroducing a smaller-scale version of the
    # same bug for ads whose title was generic.
    by_title = _first_keyword_type(title)
    if by_title is not None:
        return by_title

    by_text = _first_keyword_type(f"{title} {description} {url}")
    return by_text or "house"


def determine_subcategory(title, description, url, property_type):
    text = f"{title} {description} {url}".lower()
    if "appartement" in text:
        return "apartment"
    if "villa" in text or "maison" in text or "riad" in text or "dar" in text:
        return "house"
    if "terrain" in text or "lotissement" in text:
        return "land"
    if any(k in text for k in ("bureau", "commerce", "magasin", "local", "dépôt", "depot")):
        return "office"
    if "studio" in text or "chambre" in text:
        return "studio"
    return property_type


def extract_location(card):
    location_tag = card.select_one(".listingH3")
    location = clean_text(location_tag.get_text(" ", strip=True) if location_tag else "")

    if not location:
        return "Unknown", "Unknown"

    parts = [part.strip() for part in location.split(",") if part.strip()]
    city = parts[-1] if parts else location
    return city, location


def extract_features(card):
    area = None
    bedrooms = None

    for feature in card.select(".adDetailFeature"):
        text = clean_text(feature.get_text(" ", strip=True)).lower()
        value = parse_number(text)

        if value is None:
            continue

        if re.search(r"\d+\s*m", text) and 1 <= value <= 1_000_000:
            area = value
        elif "chambre" in text and 0 <= value <= 20:
            bedrooms = value

    return area, bedrooms


def extract_house_features(card, title, description):
    # The structured ".adFeature" chips are strong positive signals, so feed
    # them into the shared extractor alongside the free text. Same negation-aware
    # logic as tayara, so amenities are labelled consistently across sources.
    feature_texts = [
        clean_text(feature.get_text(" ", strip=True))
        for feature in card.select(".adFeature")
    ]
    combined_text = " ".join([title, description, *feature_texts])
    return extract_amenities_present(combined_text)

def extract_ad_id(url):
    match = re.search(r"/(?:pa|a|p)/(\d+)", url or "")
    return match.group(1) if match else None


def _build_ad_image_path(ad_id):
    if not ad_id or len(ad_id) < 4:
        return None
    return f"/ad/{ad_id[0]}/{ad_id[1:4]}/{ad_id[4:]}F/"


def _image_priority(url):
    lowered = url.lower()
    if "/h/" in lowered:
        return 0
    if "/m/" in lowered:
        return 1
    return 2


def _normalize_image_key(url):
    normalized = unquote(url).split("?")[0]
    normalized = re.sub(r"/(h|m)/", "/", normalized, flags=re.IGNORECASE)
    return normalized.lower()


def _is_ad_image(url, ad_path):
    if not url or not ad_path:
        return False

    lowered = unquote(url).lower()
    if ad_path.lower() not in lowered:
        return False

    if any(part in lowered for part in ("/business/", "/banner/", "/assets/", "loading.gif")):
        return False

    return True


def dedupe_images(urls):
    best = {}
    for url in urls:
        key = _normalize_image_key(url)
        if key not in best or _image_priority(url) < _image_priority(best[key]):
            best[key] = url
    return list(best.values())


def _collect_image_sources(soup, ad_path):
    sources = []

    for element in soup.select("img, [data-url], picture source"):
        for attr in ("data-url", "src", "data-src", "data-lazy-src", "srcset"):
            value = element.get(attr)
            if not value:
                continue

            candidate = value.split(",")[0].strip().split(" ")[0]
            if _is_ad_image(candidate, ad_path):
                sources.append(candidate)

    return sources


def extract_full_description(soup):
    parts = []
    seen = set()

    for block in soup.select(".blockProp"):
        paragraphs = block.select("p")
        if paragraphs:
            for paragraph in paragraphs:
                text = clean_text(paragraph.get_text(" ", strip=True))
                if text and len(text) > 15 and text not in seen:
                    parts.append(text)
                    seen.add(text)
            continue

        text = clean_text(block.get_text(" ", strip=True))
        if text and len(text) > 15 and text not in seen:
            parts.append(text)
            seen.add(text)

    return "\n\n".join(parts)


def scrape_detail_page(url, ad_id):
    """Fetch a Mubawab detail page and extract all ad images and the full description."""
    ad_path = _build_ad_image_path(ad_id)

    try:
        response = get_session().get(url, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "html.parser")

        images = dedupe_images(_collect_image_sources(soup, ad_path))
        description = extract_full_description(soup)
        soup.decompose()  # free the parsed document now, not at the next GC pass
        return images, description
    except Exception as e:
        print(f"DEBUG: Failed to scrape Mubawab detail page {url}: {e}")
        return [], ""


def extract_listing(card, default_listing_type="sale"):
    link = card.get("linkRef")
    title_tag = card.select_one(".listingTit a")
    price_tag = card.select_one(".priceTag")
    description_tag = card.select_one(".listingP.descLi")

    url = urljoin(BASE_URL, link or title_tag.get("href", ""))
    title = clean_text(title_tag.get_text(" ", strip=True) if title_tag else "")
    card_description = clean_text(description_tag.get_text(" ", strip=True) if description_tag else "")
    price = parse_price(price_tag.get_text(" ", strip=True) if price_tag else "")
    city, address = extract_location(card)
    area, bedrooms = extract_features(card)
    property_type = determine_property_type(title, card_description, url)
    subcategory = determine_subcategory(title, card_description, url, property_type)
    # Unify the two signals into one correct fine-grained category so
    # property_type reflects apartment/studio/office too, not just house/land.
    property_type = subcategory = canonical_property_type(property_type, subcategory)
    ad_id = extract_ad_id(url)

    # Land ads found in the general rent/sale categories are held back and
    # merged into the dedicated land phase regardless of which category page
    # they were first seen on, so that crawl phase is not a reliable
    # rent/sale signal for them (unlike house/apartment ads, where the
    # category page split is accurate). Default to "sale" instead when no
    # explicit keyword settles it.
    listing_type_default = "sale" if property_type == "land" else default_listing_type

    card_images = []
    for img in card.select("img"):
        img_url = img.get("data-url") or img.get("src") or img.get("data-src")
        if img_url:
            card_images.append(img_url)

    data = {
        "source": SOURCE,
        "ad_id": ad_id,
        "type": property_type,
        "listing_type": determine_listing_type(title, card_description, url, listing_type_default),
        "title": title or "Sans titre",
        "description": card_description,
        "price": price,
        "area": area,
        "city": city,
        "address": address,
        "url": url,
        "bedrooms": None,
        "garage": None,
        "furnished": None,
        "terrace": None,
        "pool": None,
        "subcategory": subcategory,
        "images": card_images,
    }

    # Every non-land property (house, apartment, studio, office) can have
    # bedrooms and the other building features; only land has none.
    if property_type != "land":
        data.update({
            "bedrooms": bedrooms,
            **extract_house_features(card, title, card_description),
        })

    return data


def enrich_from_detail(data):
    """Visit the ad detail page to get all images and the full description."""
    url = data.get("url")
    ad_id = data.get("ad_id")

    if not url or not ad_id:
        return data

    detail_images, full_description = scrape_detail_page(url, ad_id)

    if detail_images:
        data["images"] = detail_images
    if full_description:
        data["description"] = full_description

    return data


def _fetch_page(listing_type, base_url, page_number):
    """Fetch a single Mubawab listing page and return extracted listing dicts.

    The cards are turned into plain dicts here, before the DOM is freed, on
    purpose: a BeautifulSoup Tag keeps a reference to the whole parsed page, so
    returning Tags and accumulating them across hundreds of pages pins every
    page's full document in RAM at once — which grew the memory footprint page
    by page until the process ran out of memory and crashed.
    """
    page_url = build_page_url(base_url, page_number)
    print(f"DEBUG: Connecting to Mubawab {listing_type} page {page_number}: {page_url}")
    try:
        response = get_session().get(page_url, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "html.parser")
        cards = soup.select("div.listingBox[linkRef]")
        listings = [extract_listing(card, default_listing_type=listing_type) for card in cards]
        print(f"DEBUG: Found {len(listings)} raw Mubawab listings on page {page_number}.")
        soup.decompose()  # release the parsed document immediately
        return page_number, listings
    except RequestException as e:
        print(f"DEBUG: Mubawab page {page_number} request failed: {e}")
        return page_number, []


def _collect_candidates(phase, listing_type, base_url, seen_ad_ids, max_pages=MAX_PAGES,
                        progress_callback=None, cancel_event=None):
    """Fetch listing pages and return raw (un-enriched) candidate dicts."""
    # Fetch listing pages in small concurrent batches, stopping as soon as a
    # batch comes back empty (i.e. we've gone past the last real page).
    # Firing all max_pages requests at once used to trigger the site's
    # rate limiting, which then stalled the whole scrape with timeouts.
    all_listings_by_page = {}
    pages_completed = 0
    page = 1

    while page <= max_pages:
        raise_if_cancelled(cancel_event)
        batch = list(range(page, min(page + PAGE_BATCH_SIZE, max_pages + 1)))
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {
                executor.submit(_fetch_page, listing_type, base_url, p): p
                for p in batch
            }
            batch_cards_found = 0
            for future in as_completed(futures):
                raise_if_cancelled(cancel_event, executor)
                page_number, listings = future.result()
                all_listings_by_page[page_number] = listings
                batch_cards_found += len(listings)
                pages_completed += 1

                if progress_callback:
                    items_found = sum(len(c) for c in all_listings_by_page.values())
                    progress_callback(phase, "listing", pages_completed, 0, items_found)

        if batch_cards_found == 0:
            break
        page += PAGE_BATCH_SIZE

    # Collect candidates in page order
    candidates = []
    for page_number in sorted(all_listings_by_page):
        for data in all_listings_by_page[page_number]:
            if not data["ad_id"] or data["ad_id"] in seen_ad_ids:
                continue
            seen_ad_ids.add(data["ad_id"])
            candidates.append(data)

    return candidates


def _enrich_candidates(phase, candidates, progress_callback=None, cancel_event=None):
    """Fetch detail pages only for candidates missing images/description.

    Same system as the Tayara scraper: a card that already has enough images
    and a long-enough description is kept as-is, skipping its detail-page
    request entirely — most of the enrichment time used to be spent
    re-fetching data the listing cards already contained.
    """
    needs_enrichment = [
        d for d in candidates
        if len(d.get("images") or []) < 2
        or len(d.get("description") or "") < 300
        or _is_truncated(d.get("description"))
    ]
    total_to_enrich = len(needs_enrichment)
    enriched_map = {}
    if needs_enrichment:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            futures = {executor.submit(enrich_from_detail, d): d["ad_id"] for d in needs_enrichment}
            enriched_count = 0
            for future in as_completed(futures):
                raise_if_cancelled(cancel_event, executor)
                result = future.result()
                enriched_map[result["ad_id"]] = result
                enriched_count += 1
                if progress_callback:
                    progress_callback(phase, "enriching", enriched_count, total_to_enrich, len(candidates))

    return [enriched_map.get(d["ad_id"], d) for d in candidates]


def _split_known(candidates, known_ad_ids):
    """Split candidates into already-in-DB markers and to-be-enriched new ones."""
    known = [
        {"source": SOURCE, "ad_id": d["ad_id"], "_known": True}
        for d in candidates if d["ad_id"] in known_ad_ids
    ]
    new = [d for d in candidates if d["ad_id"] not in known_ad_ids]
    return known, new


def iter_scrape_phases(max_pages=MAX_PAGES, progress_callback=None, cancel_event=None,
                       known_ad_ids=None):
    """Yield (phase, listings) one phase at a time: rent, then sale, then land.

    Rent/sale phases contain only non-land properties; land listings found in
    those categories are held back and combined with the dedicated
    terrains-a-vendre category in the final land phase, so the orchestrator can
    flush each phase to the DB and free the memory before the next one starts.
    Ads already in the DB (known_ad_ids) skip enrichment entirely.
    """
    known_ad_ids = known_ad_ids or set()
    seen_ad_ids = set()
    held_land = []

    for phase, (listing_type, base_url) in (("rent", RENT_CATEGORY), ("sale", SALE_CATEGORY)):
        candidates = _collect_candidates(
            phase, listing_type, base_url, seen_ad_ids,
            max_pages=max_pages, progress_callback=progress_callback, cancel_event=cancel_event,
        )
        non_land = [d for d in candidates if d["type"] != "land"]
        held_land.extend(d for d in candidates if d["type"] == "land")
        known, new = _split_known(non_land, known_ad_ids)
        listings = known + _enrich_candidates(phase, new, progress_callback, cancel_event)
        print(f"DEBUG: Mubawab {phase} phase: {len(listings)} listings ({len(known)} known).")
        yield phase, listings

    # Land phase: the dedicated terrains category plus lands held back above
    land_type, land_url = LAND_CATEGORY
    land_candidates = _collect_candidates(
        "land", land_type, land_url, seen_ad_ids,
        max_pages=max_pages, progress_callback=progress_callback, cancel_event=cancel_event,
    )
    held_land.extend(land_candidates)
    known, new = _split_known(held_land, known_ad_ids)
    land_listings = known + _enrich_candidates("land", new, progress_callback, cancel_event)
    print(f"DEBUG: Mubawab land phase: {len(land_listings)} listings ({len(known)} known).")
    yield "land", land_listings


def scrape_mubawab(max_pages=MAX_PAGES, progress_callback=None, cancel_event=None, known_ad_ids=None):
    """Backward-compatible wrapper: run all phases and return one flat list."""
    results = []
    for _phase, items in iter_scrape_phases(max_pages, progress_callback, cancel_event, known_ad_ids):
        results.extend(items)
    print(f"DEBUG: Extracted {len(results)} unique listings from Mubawab.")
    return results
