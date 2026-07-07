import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import re


def clean_text(s):
    return str(s).strip().replace("\n", " ").replace("\r", "").strip() if s else ""


SOURCE = "expat"
BASE_URL = "https://www.expat.com/fr/immobilier/afrique/tunisie/"
MAX_PAGES = 100  # Increased to get all pages
DETAIL_WORKERS = 5

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# Amenity keywords
_FURNISHED_KEYWORDS = ("meublé", "meublee", "meublée", "furnished")
_TERRACE_KEYWORDS = ("terrasse", "terrace", "balcon", "balkony")
_POOL_KEYWORDS = ("piscine", "pool")
_GARAGE_KEYWORDS = ("garage", "parking couvert")


def _has_keyword(text: str, keywords: tuple) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


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
    """Determine if this is a sale or rent listing from the URL first, then text."""
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
    return "rent"


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
        r = requests.get(url, headers=_HEADERS, timeout=20)
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
                area = int(m_area.group(1))
            m_rooms = re.search(r"(\d+)\s*chambre", text)
            if m_rooms:
                bedrooms = int(m_rooms.group(1))

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

        # Amenity detection from full page text (Expat has no structured fields)
        full_text = soup.get_text()
        garage = _has_keyword(full_text, _GARAGE_KEYWORDS)
        furnished = _has_keyword(full_text, _FURNISHED_KEYWORDS)
        terrace = _has_keyword(full_text, _TERRACE_KEYWORDS)
        pool = _has_keyword(full_text, _POOL_KEYWORDS)

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
        r = requests.get(url, headers=_HEADERS, timeout=20)
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


def scrape_expat(max_pages: int = MAX_PAGES) -> list:
    """Scrape Expat Tunisia real estate listings across multiple pages."""
    all_links: set = set()

    with ThreadPoolExecutor(max_workers=max_pages) as executor:
        futures = [executor.submit(fetch_page_links, p) for p in range(1, max_pages + 1)]
        for future in as_completed(futures):
            all_links.update(future.result())

    print(f"DEBUG: Total unique Expat links to scrape: {len(all_links)}")
    listings = []

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(scrape_expat_detail, link): link for link in all_links}
        for future in as_completed(futures):
            data = future.result()
            if data:
                listings.append(data)

    print(f"DEBUG: Extracted {len(listings)} unique real estate listings from Expat.")
    return listings
