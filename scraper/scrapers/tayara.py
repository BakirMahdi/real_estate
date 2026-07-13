import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from ..cancellation import raise_if_cancelled
from ..classify import canonical_property_type
from ..http_client import get_session

import os

SOURCE = "tayara"
MAX_PAGES = 500  # Safety cap; real pagination stops as soon as a batch is empty
PAGE_BATCH_SIZE = int(os.getenv("SCRAPER_PAGE_BATCH_SIZE", "8"))  # Concurrent page fetches per batch
DETAIL_WORKERS = int(os.getenv("SCRAPER_DETAIL_WORKERS", "10"))  # Concurrent detail-page fetches

# Phase order: rent (non-land) first, then sale (non-land), then land (rent+sale)
LISTING_CATEGORIES = (
    ("rent", "https://www.tayara.tn/listing/c/immobilier/a-louer/"),
    ("sale", "https://www.tayara.tn/listing/c/immobilier/a-vendre/"),
)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

REAL_ESTATE_SUBCATEGORY_IDS = {
    "60be84bd50ab95b45b08a09c",
    "60be84bd50ab95b45b08a09d",
    "60be84bd50ab95b45b08a09e",
    "60be84be50ab95b45b08a09f",
    "60be84be50ab95b45b08a0a1",
}

LAND_SUBCATEGORY_IDS = {
    "60be84be50ab95b45b08a0a1",
}

PROPERTY_KEYWORDS = (
    "appartement",
    "bureau",
    "fonds de commerce",
    "hectare",
    "immeuble",
    "local commercial",
    "maison",
    "m2",
    "m²",
    "s+",
    "studio",
    "superficie",
    "terrain",
    "villa",
    "أرض",
    "ارض",
    "شقة",
    "عقار",
    "فيلا",
    "محل",
    "منزل",
)

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

FURNISHED_KEYWORDS = ("meublé", "meublee", "meublée", "furnished")
TERRACE_KEYWORDS = ("terrasse", "terrace", "balcon", "balkon", "balkony")
POOL_KEYWORDS = ("piscine", "pool")
GARAGE_KEYWORDS = ("garage", "parking couvert")
BUILDABLE_KEYWORDS = ("constructible", "buildable", "قابل للبناء")
ROAD_ACCESS_KEYWORDS = (
    "accès route",
    "acces route",
    "route goudronnée",
    "route goudronnee",
    "accès direct",
    "acces direct",
    "accès directe",
    "بطريق",
)


def clean_text(value):
    return str(value or "").strip()


def _is_truncated(description):
    """Listing-page descriptions are sometimes cut off mid-sentence with a
    trailing "..."/"…", even well past the 300-char "good enough" length
    threshold. Length alone can't catch this, so it forces a detail-page
    fetch for the real, complete description."""
    return str(description or "").rstrip().endswith(("...", "…"))


def has_keyword(text, keywords):
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def determine_listing_type(title, description, url, default="sale"):
    text = f"{title} {description} {url}".lower()
    rent_score = sum(1 for keyword in RENT_KEYWORDS if keyword in text)
    sale_score = sum(1 for keyword in SALE_KEYWORDS if keyword in text)

    if rent_score > sale_score:
        return "rent"
    if sale_score > rent_score:
        return "sale"
    if "a-louer" in text or "louer" in url.lower():
        return "rent"
    if "a-vendre" in text or "vendre" in url.lower():
        return "sale"
    return default


def parse_area(text):
    # Accepts both Latin ("m2", "m²", "mètre") and Arabic ("م2", "م²") unit
    # notations, since listings mix French and Arabic freely and the surface
    # is sometimes only stated in the title (never in the description).
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:m\s*(?:2|²)?|mètre|metre|hectare|م\s*(?:2|²)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None

    area = float(match.group(1).replace(",", "."))
    if "hectare" in match.group(0).lower():
        area *= 10000

    area = int(area)
    return area if 1 <= area <= 1_000_000 else None


def parse_rooms(description, title):
    text = f"{title} {description}".lower()
    bedrooms = None

    # "S+N" is the Tunisian apartment-type shorthand (S+2, S+3, ...), and is
    # sometimes prefixed with a digit too (e.g. "2S+6"). A plain "s" would
    # also match the last letter of any *word* ending in "s" (mois, ans,
    # maisons, chambres, garages...) immediately followed by a "+<number>"
    # token elsewhere in the text (e.g. "mois +230 caution", "chambres + 2
    # Terrasses"), misreading an unrelated count as a bedroom count. The
    # negative lookbehind only rules out a preceding Latin letter (so a
    # leading digit, space, start-of-string, or Arabic character all still
    # count as valid starts) — a plain \b would also reject "2S+6" (digit
    # directly before "s") and Arabic listings that run "s+3" straight into
    # the next Arabic word with no space (e.g. "s+3علا"), since digits and
    # Arabic letters both count as \w in Python's regex. The \d{1,2} cap is a
    # second safety net since a real room count never reaches 3+ digits.
    s_plus_match = re.search(r"(?<![a-z])s\s*\+\s*(\d{1,2})", text)
    if s_plus_match:
        bedrooms = int(s_plus_match.group(1))

    if bedrooms is None:
        bedroom_match = re.search(r"(\d{1,2})\s*(chambre|pièce|piece)", text)
        if bedroom_match:
            bedrooms = int(bedroom_match.group(1))

    return bedrooms if bedrooms is not None and 0 <= bedrooms <= 20 else None


def parse_house_features(title, description):
    text = f"{title} {description}"
    return {
        "garage": has_keyword(text, GARAGE_KEYWORDS),
        "furnished": has_keyword(text, FURNISHED_KEYWORDS),
        "terrace": has_keyword(text, TERRACE_KEYWORDS),
        "pool": has_keyword(text, POOL_KEYWORDS),
    }


def is_real_estate_listing(ad):
    metadata = ad.get("metadata", {})
    subcategory = clean_text(metadata.get("subCategory"))

    if subcategory:
        return subcategory in REAL_ESTATE_SUBCATEGORY_IDS

    category = clean_text(metadata.get("category")).lower()
    if category == "immobilier":
        return True

    text = f"{ad.get('title', '')} {ad.get('description', '')}".lower()
    return any(keyword in text for keyword in PROPERTY_KEYWORDS)


def determine_property_type(ad):
    metadata = ad.get("metadata", {})
    subcategory = clean_text(metadata.get("subCategory"))

    if subcategory in LAND_SUBCATEGORY_IDS:
        return "land"

    text = f"{ad.get('title', '')} {ad.get('description', '')}".lower()
    land_keywords = ("terrain", "lotissement", "hectare", "أرض", "ارض")
    return "land" if any(keyword in text for keyword in land_keywords) else "house"


def _listing_type_from_params(ad_params):
    """Read the authoritative rent/sale from an ad's detail "adParams".

    The detail page carries a structured {"label": "Type de transaction",
    "value": "À Vendre"|"À Louer"} attribute — the only reliable rent/sale
    signal now that the category URLs no longer separate them. Returns
    "sale"/"rent", or None if the attribute is absent.
    """
    for param in ad_params or []:
        if clean_text(param.get("label", "")).lower() == "type de transaction":
            value = clean_text(param.get("value", "")).lower()
            if "vendre" in value or "vente" in value:
                return "sale"
            if "louer" in value or "location" in value:
                return "rent"
    return None


def scrape_detail_page(url):
    """Fetch the Tayara item page: images, full description, and rent/sale type."""
    try:
        response = get_session().get(url, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        next_data = soup.find("script", id="__NEXT_DATA__")

        if not next_data:
            return [], "", None

        page_props = json.loads(next_data.string).get("props", {}).get("pageProps", {})
        ad_details = page_props.get("adDetails") or {}
        images = list(ad_details.get("images") or [])
        description = clean_text(ad_details.get("description"))
        listing_type = _listing_type_from_params(ad_details.get("adParams"))
        return images, description, listing_type
    except Exception as e:
        print(f"DEBUG: Failed to scrape Tayara detail page {url}: {e}")
        return [], "", None


def enrich_from_detail(data):
    """Use the item detail page when it has more images or a longer description."""
    url = data.get("url")
    if not url:
        return data

    listing_images = data.get("images") or []
    listing_description = data.get("description") or ""

    detail_images, full_description, detail_listing_type = scrape_detail_page(url)

    # Authoritative rent/sale from the detail page overrides the provisional
    # (feed/keyword) guess — see _listing_type_from_params.
    if detail_listing_type:
        data["listing_type"] = detail_listing_type

    if len(detail_images) > len(listing_images):
        data["images"] = detail_images
    elif detail_images and not listing_images:
        data["images"] = detail_images

    if full_description and len(full_description) > len(listing_description):
        data["description"] = full_description

    return data


def extract_listing(ad, default_listing_type="sale"):
    ad_id = clean_text(ad.get("id"))
    title = clean_text(ad.get("title")) or "Sans titre"
    description = clean_text(ad.get("description"))
    location = ad.get("location", {})
    city = clean_text(location.get("governorate")) or "Inconnu"
    delegation = clean_text(location.get("delegation"))
    property_type = determine_property_type(ad)
    url = f"https://www.tayara.tn/item/{ad_id}/" if ad_id else LISTING_CATEGORIES[0][1]

    # Land ads are cross-listed under both the "a-louer" and "a-vendre" top
    # category pages and deduped by whichever is crawled first (rent), so the
    # crawl phase is not a reliable rent/sale signal for land like it is for
    # houses/apartments. Fall back to "sale" (the common case) instead when
    # no explicit keyword settles it.
    listing_type_default = "sale" if property_type == "land" else default_listing_type

    metadata = ad.get("metadata", {})
    subcat_id = clean_text(metadata.get("subCategory"))
    subcat_mapping = {
        "60be84bd50ab95b45b08a09c": "apartment",
        "60be84bd50ab95b45b08a09d": "house",
        "60be84bd50ab95b45b08a09e": "office",
        "60be84be50ab95b45b08a09f": "studio",
        "60be84be50ab95b45b08a0a1": "land",
    }
    subcategory = subcat_mapping.get(subcat_id)
    if not subcategory:
        subcategory = "land" if property_type == "land" else "house"
    # Unify into one correct fine-grained category (tayara's metadata subCategory
    # is a strong signal), so property_type is no longer collapsed to house/land.
    property_type = subcategory = canonical_property_type(property_type, subcategory)

    data = {
        "source": SOURCE,
        "ad_id": ad_id or None,
        "type": property_type,
        "listing_type": determine_listing_type(title, description, url, listing_type_default),
        "title": title,
        "description": description,
        "price": float(ad.get("price") or 0),
        "area": parse_area(f"{title} {description}"),
        "city": city,
        "address": delegation or city,
        "url": url,
        "bedrooms": None,
        "garage": None,
        "furnished": None,
        "terrace": None,
        "pool": None,
        "subcategory": subcategory,
        "images": list(ad.get("images") or []),
    }

    if property_type != "land":
        bedrooms = parse_rooms(description, title)
        data.update({
            "bedrooms": bedrooms,
            **parse_house_features(title, description),
        })

    return data


def build_page_url(base_url, page_number):
    if page_number == 1:
        return base_url

    return f"{base_url}?page={page_number}"


def extract_hits_from_html(html, include_golden_listing=False):
    soup = BeautifulSoup(html, "html.parser")
    next_data = soup.find("script", id="__NEXT_DATA__")

    if not next_data:
        print("DEBUG: CRITICAL: __NEXT_DATA__ tag not found.")
        return []

    json_data = json.loads(next_data.string)
    page_props = json_data.get("props", {}).get("pageProps", {})
    action = page_props.get("searchedListingsAction", {})
    hits = list(action.get("newHits") or [])
    golden_listing = page_props.get("goldenListing")

    if include_golden_listing and golden_listing:
        hits.append(golden_listing)

    return hits


def _fetch_page(listing_type, base_url, page_number):
    """Fetch a single Tayara listing page and return parsed hits."""
    page_url = build_page_url(base_url, page_number)
    print(f"DEBUG: Connecting to Tayara {listing_type} page {page_number}: {page_url}")
    try:
        response = get_session().get(page_url, headers=_HEADERS, timeout=20)
        print(f"DEBUG: Tayara page {page_number} status code: {response.status_code}")
        if response.status_code != 200:
            print(f"DEBUG: Tayara page {page_number} blocked or error. Status: {response.status_code}")
            return page_number, []
        hits = extract_hits_from_html(response.text, include_golden_listing=page_number == 1)
        print(f"DEBUG: Found {len(hits)} raw Tayara listings on page {page_number}.")
        return page_number, hits
    except Exception as e:
        print(f"DEBUG: Tayara page {page_number} failed: {e}")
        return page_number, []


def _collect_candidates(phase, listing_type, base_url, seen_ad_ids, max_pages=MAX_PAGES,
                        progress_callback=None, cancel_event=None):
    """Fetch listing pages and return raw (un-enriched) candidate dicts."""
    # Fetch listing pages in small concurrent batches, stopping as soon as a
    # batch comes back empty (i.e. we've gone past the last real page).
    # Firing all max_pages requests at once used to trigger the site's
    # rate limiting, which then stalled the whole scrape with timeouts.
    all_hits_by_page = {}
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
            batch_hits_found = 0
            for future in as_completed(futures):
                raise_if_cancelled(cancel_event, executor)
                page_number, hits = future.result()
                all_hits_by_page[page_number] = hits
                batch_hits_found += len(hits)
                pages_completed += 1

                if progress_callback:
                    items_found = sum(len(h) for h in all_hits_by_page.values())
                    progress_callback(phase, "listing", pages_completed, 0, items_found)

        if batch_hits_found == 0:
            break
        page += PAGE_BATCH_SIZE

    # Collect candidates in page order to maintain determinism
    candidates = []
    for page_number in sorted(all_hits_by_page):
        for ad in all_hits_by_page[page_number]:
            ad_id = clean_text(ad.get("id"))
            if not ad_id or ad_id in seen_ad_ids:
                continue
            if not is_real_estate_listing(ad):
                continue
            data = extract_listing(ad, default_listing_type=listing_type)
            seen_ad_ids.add(ad_id)
            candidates.append(data)

    return candidates


def _enrich_candidates(phase, candidates, progress_callback=None, cancel_event=None):
    """Fetch detail pages for candidates that are missing images/description."""
    # Every new ad is detail-fetched now: the listing feed no longer carries the
    # transaction type (rent/sale), so it must be read from each ad's detail page.
    # The fetch also fills in images/description along the way.
    needs_enrichment = list(candidates)
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
        # Carry type/listing_type so known markers can still be routed to the
        # right display phase (they're never re-inserted, so these are hints).
        {"source": SOURCE, "ad_id": d["ad_id"], "_known": True,
         "type": d.get("type"), "listing_type": d.get("listing_type")}
        for d in candidates if d["ad_id"] in known_ad_ids
    ]
    new = [d for d in candidates if d["ad_id"] not in known_ad_ids]
    return known, new


def iter_scrape_phases(max_pages=MAX_PAGES, progress_callback=None, cancel_event=None,
                       known_ad_ids=None):
    """Yield (phase, listings) one phase at a time: rent, then sale, then land.

    Rent/sale phases contain only non-land properties; land listings found in
    both categories are held back (as small raw dicts) and enriched/yielded in
    the final land phase, so the orchestrator can flush each phase to the DB
    and free the memory before the next one starts. Ads already in the DB
    (known_ad_ids) skip enrichment entirely.
    """
    known_ad_ids = known_ad_ids or set()
    seen_ad_ids = set()

    # Tayara's /a-louer/ and /a-vendre/ category URLs stopped filtering by
    # transaction type -- both now return the same mixed feed -- so crawling both
    # just deduped the second to nothing (that's why "Vente" showed 0). Crawl the
    # feed once; the real rent/sale comes from each ad's detail page
    # ("Type de transaction"), applied during enrichment. Land is split off by
    # property_type. Progress is reported under a real phase name ("rent") since
    # the callback only knows the three fixed phases.
    _, feed_url = LISTING_CATEGORIES[0]
    candidates = _collect_candidates(
        "rent", "sale", feed_url, seen_ad_ids,
        max_pages=max_pages, progress_callback=progress_callback, cancel_event=cancel_event,
    )
    known, new = _split_known(candidates, known_ad_ids)
    all_items = known + _enrich_candidates("rent", new, progress_callback, cancel_event)

    def phase_of(item):
        if item.get("type") == "land":
            return "land"
        lt = item.get("listing_type")
        return lt if lt in ("rent", "sale") else "sale"

    buckets = {"rent": [], "sale": [], "land": []}
    for item in all_items:
        buckets[phase_of(item)].append(item)

    for phase in ("rent", "sale", "land"):
        print(f"DEBUG: Tayara {phase} phase: {len(buckets[phase])} listings.")
        yield phase, buckets[phase]


def scrape_tayara(max_pages=MAX_PAGES, progress_callback=None, cancel_event=None, known_ad_ids=None):
    """Backward-compatible wrapper: run all phases and return one flat list."""
    listings = []
    for _phase, items in iter_scrape_phases(max_pages, progress_callback, cancel_event, known_ad_ids):
        listings.extend(items)
    print(f"DEBUG: Extracted {len(listings)} unique real estate listings from Tayara.")
    return listings
