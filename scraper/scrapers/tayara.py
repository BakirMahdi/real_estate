import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

SOURCE = "tayara"
MAX_PAGES = 10000  # Scrape all pages (very high limit)
DETAIL_WORKERS = 8

LISTING_CATEGORIES = (
    ("sale", "https://www.tayara.tn/listing/c/immobilier/a-vendre/"),
    ("rent", "https://www.tayara.tn/listing/c/immobilier/a-louer/"),
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


def parse_area(description):
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:m\s*(?:2|²)?|mètre|metre|hectare)", description, re.IGNORECASE)
    if not match:
        return None

    area = float(match.group(1).replace(",", "."))
    if "hectare" in match.group(0).lower():
        area *= 10000

    return int(area)


def parse_rooms(description, title):
    text = f"{title} {description}".lower()
    bedrooms = None

    s_plus_match = re.search(r"s\s*\+\s*(\d+)", text)
    if s_plus_match:
        bedrooms = int(s_plus_match.group(1))

    if bedrooms is None:
        bedroom_match = re.search(r"(\d+)\s*(chambre|pièce|piece)", text)
        if bedroom_match:
            bedrooms = int(bedroom_match.group(1))

    return bedrooms


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


def scrape_detail_page(url):
    """Fetch the Tayara item page for all images and the full description."""
    try:
        response = requests.get(url, headers=_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        next_data = soup.find("script", id="__NEXT_DATA__")

        if not next_data:
            return [], ""

        page_props = json.loads(next_data.string).get("props", {}).get("pageProps", {})
        ad_details = page_props.get("adDetails") or {}
        images = list(ad_details.get("images") or [])
        description = clean_text(ad_details.get("description"))
        return images, description
    except Exception as e:
        print(f"DEBUG: Failed to scrape Tayara detail page {url}: {e}")
        return [], ""


def enrich_from_detail(data):
    """Use the item detail page when it has more images or a longer description."""
    url = data.get("url")
    if not url:
        return data

    listing_images = data.get("images") or []
    listing_description = data.get("description") or ""
    if len(listing_images) >= 2 and len(listing_description) >= 300:
        return data

    detail_images, full_description = scrape_detail_page(url)

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

    data = {
        "source": SOURCE,
        "ad_id": ad_id or None,
        "type": property_type,
        "listing_type": determine_listing_type(title, description, url, default_listing_type),
        "title": title,
        "description": description,
        "price": float(ad.get("price") or 0),
        "area": parse_area(description),
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

    if property_type == "house":
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
        response = requests.get(page_url, headers=_HEADERS, timeout=20)
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


def scrape_category(listing_type, base_url, seen_ad_ids, max_pages=MAX_PAGES, progress_callback=None):
    listings = []

    # Fetch all listing pages concurrently
    all_hits_by_page = {}
    pages_completed = 0
    total_pages = max_pages
    
    with ThreadPoolExecutor(max_workers=max_pages) as executor:
        futures = {
            executor.submit(_fetch_page, listing_type, base_url, p): p
            for p in range(1, max_pages + 1)
        }
        for future in as_completed(futures):
            page_number, hits = future.result()
            all_hits_by_page[page_number] = hits
            pages_completed += 1
            
            # Update progress callback
            if progress_callback:
                items_found = sum(len(h) for h in all_hits_by_page.values())
                progress_callback(pages_completed, total_pages, items_found)

    # Collect candidates in page order to maintain determinism
    candidates = []
    for page_number in range(1, max_pages + 1):
        for ad in all_hits_by_page.get(page_number, []):
            ad_id = clean_text(ad.get("id"))
            if not ad_id or ad_id in seen_ad_ids:
                continue
            if not is_real_estate_listing(ad):
                continue
            data = extract_listing(ad, default_listing_type=listing_type)
            seen_ad_ids.add(ad_id)
            candidates.append(data)

    # Identify which listings need detail enrichment and fetch them concurrently
    needs_enrichment = [
        d for d in candidates
        if len(d.get("images") or []) < 2 or len(d.get("description") or "") < 300
    ]
    enriched_map = {}
    if needs_enrichment:
        with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
            futures = {executor.submit(enrich_from_detail, d): d["ad_id"] for d in needs_enrichment}
            for future in as_completed(futures):
                result = future.result()
                enriched_map[result["ad_id"]] = result

    for data in candidates:
        if data["ad_id"] in enriched_map:
            listings.append(enriched_map[data["ad_id"]])
        else:
            listings.append(data)

    print(f"DEBUG: Extracted {len(listings)} real estate listings from Tayara ({listing_type}).")
    return listings


def scrape_tayara(max_pages=MAX_PAGES, progress_callback=None):
    listings = []
    seen_ad_ids = set()

    for listing_type, base_url in LISTING_CATEGORIES:
        category_listings = scrape_category(
            listing_type,
            base_url,
            seen_ad_ids,
            max_pages=max_pages,
            progress_callback=progress_callback,
        )
        listings.extend(category_listings)
        print(f"DEBUG: Extracted {len(category_listings)} new {listing_type} listings from Tayara.")

    print(f"DEBUG: Extracted {len(listings)} unique real estate listings from Tayara.")
    return listings
