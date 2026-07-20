import os
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

from ..amenities import extract_amenities_present
from ..cancellation import raise_if_cancelled
from ..http_client import get_session


def clean_text(s):
    return str(s).strip().replace("\n", " ").replace("\r", "").strip() if s else ""


SOURCE = "expat"
BASE_URL = "https://www.expat.com/fr/immobilier/afrique/tunisie/"
MAX_PAGES = 2000  # Safety cap; real pagination stops as soon as a batch is empty
PAGE_BATCH_SIZE = int(os.getenv("SCRAPER_PAGE_BATCH_SIZE", "8"))  # Concurrent page fetches per batch
DETAIL_WORKERS = int(os.getenv("SCRAPER_DETAIL_WORKERS", "10"))  # Concurrent detail-page fetches

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Map URL path segments to listing types
_RENT_PATH_KEYWORDS = ["louer", "location", "a-louer"]
_SALE_PATH_KEYWORDS = ["vendre", "vente", "a-vendre"]

# Map URL path segments to property types
_TYPE_PATH_MAP = {
    "appartement": "apartment",
    "maison": "house",
    "villa": "house",
    "duplex": "house",
    "terrain": "land",
    "bureau": "office",
    "studio": "studio",
    "local": "office",
}


def parse_price(price_str: str) -> float:
    """Extract numeric value from a price string, ignoring currency symbols."""
    if not price_str:
        return 0.0
    digits = re.sub(r"[^\d]", "", price_str)
    return float(digits) if digits else 0.0


def determine_listing_type_from_url(url: str, title: str, description: str) -> str:
    """Determine if this is a sale or rent listing from the URL first, then text.

    Previously this fell back to "rent" whenever neither the URL nor the
    text gave a sale signal, without ever checking for a rent signal either
    — so any ad with no keywords at all (e.g. a bare land listing) silently
    became "rent" instead of leaving the ambiguity to a neutral default.
    Now both signals are checked and the default matches the other scrapers.
    """
    url_lower = url.lower()
    for kw in _SALE_PATH_KEYWORDS:
        if kw in url_lower:
            return "sale"
    for kw in _RENT_PATH_KEYWORDS:
        if kw in url_lower:
            return "rent"
    # Fallback to title/description
    combined = (title + " " + description).lower()
    if any(kw in combined for kw in ["vente", "a vendre", "vendre"]):
        return "sale"
    if any(kw in combined for kw in ["location", "a louer", "louer"]):
        return "rent"
    return "sale"


def determine_property_type(url: str, title: str, description: str) -> str:
    """Determine property type from URL slug and title/description keywords."""
    url_lower = url.lower()
    for slug, ptype in _TYPE_PATH_MAP.items():
        if slug in url_lower:
            return ptype
    combined = (title + " " + description).lower()
    if "terrain" in combined or "lotissement" in combined:
        return "land"
    if "appartement" in combined or "appart" in combined:
        return "apartment"
    if "bureau" in combined or "local" in combined:
        return "office"
    if "studio" in combined:
        return "studio"
    return "house"


def scrape_expat_detail(url: str):
    """Fetch a single Expat property detail page and return structured data."""
    # Skip non-property links (guides, category pages without numeric ID)
    ad_id_match = re.search(r"/(\d+)-[^/]+\.html", url)
    if not ad_id_match:
        return None

    ad_id = ad_id_match.group(1)

    try:
        r = get_session().get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"DEBUG: Expat detail {url} returned {r.status_code}")
            return None
        soup = BeautifulSoup(r.text, "html.parser")

        # Title
        title_tag = soup.find("h1")
        title = clean_text(title_tag.text) if title_tag else ""
        if not title:
            return None

        # Description – class contains "description"
        desc_div = soup.find(class_="housing-item--description")
        description = clean_text(desc_div.text) if desc_div else ""

        # Price – typography class with price-like content
        price = 0.0
        price_tag = soup.find("p", class_=lambda c: c and "typography" in c and "primary" in c)
        if price_tag:
            price = parse_price(price_tag.text)

        # Area & bedrooms from property-details list
        area = None
        bedrooms = None
        for li in soup.find_all("li", class_="property-details-section--list--item"):
            text = li.text.lower().strip()
            m_area = re.search(r"(\d+)\s*m[²2]?", text)
            if m_area and ("m²" in text or "surface" in text or "superficie" in text or "m2" in text):
                value = int(m_area.group(1))
                if 1 <= value <= 1_000_000:
                    area = value
            m_rooms = re.search(r"(\d+)\s*chambre", text)
            if m_rooms:
                value = int(m_rooms.group(1))
                if 0 <= value <= 20:
                    bedrooms = value

        # Images – /upload/housing/ path
        images = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if "/upload/housing/" in src:
                full_src = src if src.startswith("http") else "https://www.expat.com" + src
                images.append(full_src)

        # Location – class contains "location"
        location = "Tunisie"
        loc_tag = soup.find(class_="location-section")
        if loc_tag:
            # Get text but skip the "Voir la carte" button text
            loc_header = loc_tag.find(class_="location-section--header")
            if loc_header:
                loc_text = loc_header.text.replace("Voir la carte", "").strip()
                # Remove "Localisation géographique" label
                loc_text = loc_text.replace("Localisation géographique", "").strip()
                if loc_text:
                    location = clean_text(loc_text)

        city = location.split(",")[0].strip() if "," in location else location

        prop_type = determine_property_type(url, title, description)
        listing_type = determine_listing_type_from_url(url, title, description)

        # Amenity detection from full page text (Expat has no structured fields).
        # Shared, negation-aware extractor - consistent with tayara/mubawab.
        amenities = extract_amenities_present(soup.get_text())
        garage = amenities["garage"]
        furnished = amenities["furnished"]
        terrace = amenities["terrace"]
        pool = amenities["pool"]

        return {
            "source": SOURCE,
            "ad_id": ad_id,
            "type": prop_type,
            "listing_type": listing_type,
            "title": title,
            "description": description,
            "price": price,
            "area": area,
            "city": city,
            "address": location,
            "url": url,
            "bedrooms": bedrooms,
            "garage": garage,
            "furnished": furnished,
            "terrace": terrace,
            "pool": pool,
            "subcategory": prop_type,
            "images": list(dict.fromkeys(images)),  # deduplicate preserving order
        }
    except Exception as e:
        print(f"DEBUG: Expat detail error for {url}: {e}")
        return None


def fetch_page_links(page: int) -> list:
    """Fetch one listing page and return all property detail URLs found."""
    url = BASE_URL if page == 1 else f"{BASE_URL}{page}/"
    print(f"DEBUG: Connecting to Expat page {page}: {url}")
    try:
        r = get_session().get(url, headers=_HEADERS, timeout=20)
        print(f"DEBUG: Expat page {page} status: {r.status_code}")
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if (
                "/immobilier/afrique/tunisie" in href
                and ".html" in href
                and "guide" not in href
                and "forum" not in href
                and re.search(r"/\d+-[^/]+\.html", href)
            ):
                full_url = href if href.startswith("http") else "https://www.expat.com" + href
                links.append(full_url)
        unique = list(set(links))
        print(f"DEBUG: Expat page {page} found {len(unique)} property links.")
        return unique
    except Exception as e:
        print(f"DEBUG: Expat page {page} failed: {e}")
        return []


def _classify_link(url: str) -> str:
    """Best-effort phase classification (rent/sale/land) from the URL slug."""
    if determine_property_type(url, "", "") == "land":
        return "land"
    url_lower = url.lower()
    if any(kw in url_lower for kw in _SALE_PATH_KEYWORDS):
        return "sale"
    if any(kw in url_lower for kw in _RENT_PATH_KEYWORDS):
        return "rent"
    return "rent"


def _collect_links(max_pages=MAX_PAGES, progress_callback=None, cancel_event=None) -> set:
    """Fetch listing pages in small batches, stopping once a batch is empty."""
    all_links: set = set()
    pages_completed = 0
    page = 1

    while page <= max_pages:
        raise_if_cancelled(cancel_event)
        batch = list(range(page, min(page + PAGE_BATCH_SIZE, max_pages + 1)))
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = [executor.submit(fetch_page_links, p) for p in batch]
            batch_links_found = 0
            for future in as_completed(futures):
                raise_if_cancelled(cancel_event, executor)
                links = future.result()
                batch_links_found += len(links)
                all_links.update(links)
                pages_completed += 1

                if progress_callback:
                    progress_callback("rent", "listing", pages_completed, 0, len(all_links))

        if batch_links_found == 0:
            break
        page += PAGE_BATCH_SIZE

    print(f"DEBUG: Total unique Expat links to scrape: {len(all_links)}")
    return all_links


def _extract_ad_id(url: str):
    m = re.search(r"/(\d+)-[^/]+\.html", url)
    return m.group(1) if m else None


def _scrape_details(phase, links, progress_callback=None, cancel_event=None, known_ad_ids=None) -> list:
    """Fetch detail pages for one phase's links, reporting progress per page.

    Links whose ad_id is already in the DB are passed through as lightweight
    "known" markers instead of being downloaded again.
    """
    known_ad_ids = known_ad_ids or set()
    listings = []

    to_fetch = []
    for url in links:
        ad_id = _extract_ad_id(url)
        if ad_id and ad_id in known_ad_ids:
            listings.append({"source": SOURCE, "ad_id": ad_id, "_known": True})
        else:
            to_fetch.append(url)

    total = len(to_fetch)
    done = 0
    if to_fetch:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            futures = {executor.submit(scrape_expat_detail, link): link for link in to_fetch}
            for future in as_completed(futures):
                raise_if_cancelled(cancel_event, executor)
                data = future.result()
                if data:
                    listings.append(data)
                done += 1
                if progress_callback:
                    progress_callback(phase, "enriching", done, total, len(listings))
    elif progress_callback:
        progress_callback(phase, "enriching", 0, 0, len(listings))

    return listings


def iter_scrape_phases(max_pages: int = MAX_PAGES, progress_callback=None, cancel_event=None,
                       known_ad_ids=None):
    """Yield (phase, listings) one phase at a time: rent, then sale, then land.

    Detail URLs are classified by their slug so each phase only fetches its own
    detail pages; the orchestrator flushes each phase to the DB and frees the
    memory before the next one starts. Ads already in the DB (known_ad_ids) are
    not re-downloaded.
    """
    all_links = _collect_links(max_pages, progress_callback, cancel_event)

    groups = {"rent": [], "sale": [], "land": []}
    for link in sorted(all_links):
        groups[_classify_link(link)].append(link)
    del all_links

    for phase in ("rent", "sale", "land"):
        listings = _scrape_details(phase, groups[phase], progress_callback, cancel_event, known_ad_ids)
        print(f"DEBUG: Expat {phase} phase: {len(listings)} listings.")
        yield phase, listings


def scrape_expat(max_pages: int = MAX_PAGES, progress_callback=None, cancel_event=None,
                 known_ad_ids=None) -> list:
    """Backward-compatible wrapper: run all phases and return one flat list."""
    listings = []
    for _phase, items in iter_scrape_phases(max_pages, progress_callback, cancel_event, known_ad_ids):
        listings.extend(items)
    print(f"DEBUG: Extracted {len(listings)} unique real estate listings from Expat.")
    return listings
