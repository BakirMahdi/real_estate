import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import json


def clean_text(s):
    return str(s).strip().replace("\n", " ").replace("\r", "").strip() if s else ""


SOURCE = "affare"
BASE_URL = "https://www.affare.tn/petites-annonces/tunisie/immobilier?o="
MAX_PAGES = 10000  # Scrape all pages (very high limit)
DETAIL_WORKERS = 5

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

_RENT_KEYWORDS = ["location", "louer", "a louer", "à louer", "vacances", "lld", "ll ", "mois"]
_SALE_KEYWORDS = ["vente", "vendre", "a vendre", "à vendre"]

# Amenity keyword lists (used for text-based detection)
_FURNISHED_KEYWORDS = ("meublé", "meublee", "meublée", "meuble", "furnished")
_TERRACE_KEYWORDS = ("terrasse", "terrace", "balcon", "balkony")
_POOL_KEYWORDS = ("piscine", "pool")
_GARAGE_KEYWORDS = ("garage", "parking couvert")


def _has_keyword(text: str, keywords: tuple) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def _parse_amenities_from_text(title: str, description: str) -> dict:
    """Detect garage, terrace, pool from free-text when structured fields are absent."""
    combined = f"{title} {description}"
    return {
        "garage": _has_keyword(combined, _GARAGE_KEYWORDS),
        "terrace": _has_keyword(combined, _TERRACE_KEYWORDS),
        "pool": _has_keyword(combined, _POOL_KEYWORDS),
    }



def parse_price(price_str: str) -> float:
    """Extract the first numeric value from a price string."""
    if not price_str:
        return 0.0
    m = re.search(r"[\d\s]+", price_str.replace("\xa0", " "))
    if m:
        digits = re.sub(r"\s", "", m.group())
        return float(digits) if digits else 0.0
    return 0.0


def determine_listing_type(title: str, description: str, url: str) -> str:
    combined = (title + " " + description + " " + url).lower()
    if any(kw in combined for kw in _SALE_KEYWORDS):
        return "sale"
    if any(kw in combined for kw in _RENT_KEYWORDS):
        return "rent"
    return "sale"


def determine_property_type(title: str, description: str, schema_type: str = "") -> str:
    """Map Schema.org type or title keywords to our internal property types."""
    # Schema.org type mapping
    schema_map = {
        "Apartment": "apartment",
        "House": "house",
        "LandLot": "land",
        "Residence": "house",
        "SingleFamilyResidence": "house",
        "Accommodation": "house",
    }
    if schema_type in schema_map:
        return schema_map[schema_type]

    combined = (title + " " + description).lower()
    if "terrain" in combined or "lotissement" in combined or "foncier" in combined:
        return "land"
    if "appartement" in combined or "duplex" in combined or "appart" in combined:
        return "apartment"
    if "bureau" in combined or "local commercial" in combined:
        return "office"
    if "studio" in combined:
        return "studio"
    return "house"


def scrape_affare_detail(url: str):
    """Fetch one Affare property detail page and return structured data."""
    ad_id_match = re.search(r"-(\d+)$", url.rstrip("/"))
    if not ad_id_match:
        return None
    ad_id = ad_id_match.group(1)

    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"DEBUG: Affare detail {url} returned {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # --- Extract from Schema.org JSON-LD (most reliable) ---
        schema_data = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                if isinstance(data, dict) and data.get("@type") in (
                    "Product", "Apartment", "House", "Residence",
                    "LandLot", "SingleFamilyResidence", "Accommodation"
                ):
                    schema_data = data
                    break
            except Exception:
                pass

        # Title
        title_tag = soup.find("h1")
        title = clean_text(title_tag.text) if title_tag else clean_text(schema_data.get("name", ""))
        if not title:
            return None

        # Description
        desc_div = soup.find(class_=lambda c: c and "Annonce_dessto" in c)
        description = clean_text(desc_div.text) if desc_div else clean_text(schema_data.get("description", ""))

        # Price — from Schema.org offers
        price = 0.0
        offers = schema_data.get("offers", {})
        if offers.get("price"):
            try:
                price = float(offers["price"])
            except (ValueError, TypeError):
                pass
        if price == 0:
            price_tag = soup.find(class_=lambda c: c and "Annonce_price" in c)
            if price_tag:
                price = parse_price(price_tag.text)

        # Property type — from Schema.org itemOffered
        item_offered = schema_data.get("itemOffered", {})
        schema_item_type = item_offered.get("@type", "")
        prop_type = determine_property_type(title, description, schema_item_type)

        # --- Extract structured params (Meublée, Parking, etc.) ---
        furnished = None
        garage = None
        params_divs = soup.find_all(class_=lambda c: c and "Annonce_flx" in c)
        for div in params_divs:
            label_div = div.find(lambda t: t.name and not t.get("class"))
            value_div = div.find(class_=lambda c: c and "Annonce_prop" in c)
            if not label_div or not value_div:
                # Fall back: just scan the whole text
                text = div.text.lower()
                if "meublée" in text or "meublé" in text:
                    furnished = "oui" in text
                elif "parking" in text:
                    garage = "oui" in text
                continue
            label = label_div.text.strip().lower()
            value = value_div.text.strip().lower()
            if "meublé" in label:
                furnished = "oui" in value
            elif "parking" in label:
                garage = "oui" in value

        # Text-based amenity detection from description for terrace/pool,
        # and as fallback for furnished/garage
        text_amenities = _parse_amenities_from_text(title, description)
        if furnished is None:
            furnished = _has_keyword(f"{title} {description}", _FURNISHED_KEYWORDS)
        if garage is None:
            garage = text_amenities["garage"]
        terrace = text_amenities["terrace"]
        pool = text_amenities["pool"]

        area = None
        floor_size = item_offered.get("floorSize", {})
        if floor_size.get("value"):
            try:
                area = int(float(floor_size["value"]))
            except (ValueError, TypeError):
                pass
        if area is None:
            # Fallback: scan detail params
            for div in soup.find_all(class_=lambda c: c and "Annonce_flx" in c):
                text = div.text.lower()
                if "superficie" in text:
                    m = re.search(r"(\d+)", text.split("superficie")[-1])
                    if m:
                        area = int(m.group(1))
                        break

        # Bedrooms — from Schema.org numberOfRooms
        bedrooms = None
        if item_offered.get("numberOfRooms"):
            try:
                bedrooms = int(item_offered["numberOfRooms"])
            except (ValueError, TypeError):
                pass
        if bedrooms is None:
            for div in soup.find_all(class_=lambda c: c and "Annonce_flx" in c):
                text = div.text.lower()
                if "chambre" in text:
                    m = re.search(r"(\d+)", text.split("chambre")[0].strip().split()[-1] if text.split("chambre")[0].strip() else "0")
                    if m:
                        bedrooms = int(m.group(1))
                        break

        # Images — preload links and gallery images
        images = []
        for link_tag in soup.find_all("link", rel="preload", as_="image"):
            href = link_tag.get("href", "")
            if "/large/" in href:
                images.append(href)

        # Also check Schema.org image list
        schema_images = schema_data.get("image", [])
        if isinstance(schema_images, list):
            for img_url in schema_images:
                if img_url not in images:
                    images.append(img_url)
        elif isinstance(schema_images, str) and schema_images not in images:
            images.append(schema_images)

        # Location — Schema.org address
        address_schema = item_offered.get("address", {})
        address_region = clean_text(address_schema.get("addressRegion", ""))
        city = clean_text(address_schema.get("addressLocality", ""))
        if not city:
            # Fallback to meta info
            meta_infos = soup.find_all(class_=lambda c: c and "Annonce_metaInfo" in c)
            if meta_infos:
                raw_loc = clean_text(meta_infos[0].text)
                parts = [p.strip() for p in raw_loc.split("•") if p.strip()]
                city = parts[0] if parts else "Tunisie"

        address = f"{city}, {address_region}".strip(", ") if address_region else city

        # Listing type
        listing_type = determine_listing_type(title, description, url)

        # Business function from Schema.org
        business_func = offers.get("businessFunction", "")
        if "Sell" in business_func:
            listing_type = "sale"
        elif "LeaseOut" in business_func or "Rent" in business_func:
            listing_type = "rent"

        return {
            "source": SOURCE,
            "ad_id": ad_id,
            "type": prop_type,
            "listing_type": listing_type,
            "title": title,
            "description": description,
            "price": price,
            "area": area,
            "city": city or "Tunisie",
            "address": address or city or "Tunisie",
            "url": url,
            "bedrooms": bedrooms,
            "garage": garage,
            "furnished": furnished,
            "terrace": terrace,
            "pool": pool,
            "subcategory": prop_type,
            "images": list(dict.fromkeys(images)),  # deduplicate, preserve order
        }
    except Exception as e:
        print(f"DEBUG: Affare detail error for {url}: {e}")
        return None


def fetch_page_links(page: int) -> list:
    """Fetch one listing page and return all property detail URLs on it."""
    url = f"{BASE_URL}{page}"
    print(f"DEBUG: Connecting to Affare page {page}: {url}")
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        print(f"DEBUG: Affare page {page} status: {r.status_code}")
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/annonce/" in href:
                full_url = href if href.startswith("http") else "https://www.affare.tn" + href
                links.append(full_url)
        unique = list(set(links))
        print(f"DEBUG: Affare page {page} found {len(unique)} property links.")
        return unique
    except Exception as e:
        print(f"DEBUG: Affare page {page} failed: {e}")
        return []


def scrape_affare(max_pages: int = MAX_PAGES, progress_callback=None) -> list:
    """Scrape Affare Tunisia real estate listings across multiple pages."""
    all_links: set = set()
    pages_completed = 0
    total_pages = max_pages

    with ThreadPoolExecutor(max_workers=max_pages) as executor:
        futures = [executor.submit(fetch_page_links, p) for p in range(1, max_pages + 1)]
        for future in as_completed(futures):
            all_links.update(future.result())
            pages_completed += 1
            
            # Update progress callback
            if progress_callback:
                progress_callback(pages_completed, total_pages, len(all_links))

    print(f"DEBUG: Total unique Affare links to scrape: {len(all_links)}")
    listings = []

    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(scrape_affare_detail, link): link for link in all_links}
        for future in as_completed(futures):
            data = future.result()
            if data:
                listings.append(data)

    print(f"DEBUG: Extracted {len(listings)} unique real estate listings from Affare.")
    return listings
