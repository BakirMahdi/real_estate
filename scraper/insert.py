from .db import get_conn


def property_exists(source, ad_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM properties WHERE source = %s AND ad_id = %s",
        (source, ad_id),
    )
    result = cur.fetchone()
    cur.close()
    conn.close()
    return result is not None


def bulk_get_existing_ids(source, ad_ids):
    """Return the set of ad_ids that already exist in the DB for the given source."""
    if not ad_ids:
        return set()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT ad_id FROM properties WHERE source = %s AND ad_id = ANY(%s)",
        (source, list(ad_ids)),
    )
    existing = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return existing


def bulk_get_latest_properties(source, ad_ids):
    """Return a dict mapping ad_id to its latest property row dict in the DB."""
    if not ad_ids:
        return {}
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (source, ad_id)
            ad_id, property_type, listing_type, title, description, price, area,
            city, address, url, bedrooms, garage, furnished, terrace, pool,
            subcategory, images
        FROM properties
        WHERE source = %s AND ad_id = ANY(%s)
        ORDER BY source, ad_id, id DESC
        """,
        (source, list(ad_ids)),
    )
    rows = cur.fetchall()
    latest_by_id = {}
    for row in rows:
        desc = cur.description
        row_dict = {desc[idx][0]: row[idx] for idx in range(len(desc))}
        latest_by_id[row_dict["ad_id"]] = row_dict
    cur.close()
    conn.close()
    return latest_by_id


def is_same_property(scraped, latest_db):
    """Compare all extracted fields of a scraped ad against the latest DB entry to see if they are identical."""
    if not latest_db:
        return False

    def normalize_str(val):
        return str(val or "").strip()

    # Compare string fields
    if normalize_str(scraped.get("title")) != normalize_str(latest_db.get("title")):
        return False
    if normalize_str(scraped.get("description")) != normalize_str(latest_db.get("description")):
        return False
    if normalize_str(scraped.get("city")) != normalize_str(latest_db.get("city")):
        return False
    if normalize_str(scraped.get("address")) != normalize_str(latest_db.get("address")):
        return False
    if normalize_str(scraped.get("url")) != normalize_str(latest_db.get("url")):
        return False
    if normalize_str(scraped.get("type") or scraped.get("property_type")) != normalize_str(latest_db.get("property_type")):
        return False
    if normalize_str(scraped.get("listing_type")) != normalize_str(latest_db.get("listing_type")):
        return False
    if normalize_str(scraped.get("subcategory")) != normalize_str(latest_db.get("subcategory")):
        return False

    # Compare numeric fields
    def get_float(val):
        if val is None:
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def get_int(val):
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    if get_float(scraped.get("price")) != get_float(latest_db.get("price")):
        return False
    if get_int(scraped.get("area")) != get_int(latest_db.get("area")):
        return False

    # Compare type-specific options (only relevant if house)
    is_house_scraped = (scraped.get("type") or scraped.get("property_type")) == "house"
    is_house_db = latest_db.get("property_type") == "house"

    if is_house_scraped != is_house_db:
        return False

    if is_house_scraped:
        if get_int(scraped.get("bedrooms")) != get_int(latest_db.get("bedrooms")):
            return False

        for key in ["garage", "furnished", "terrace", "pool"]:
            val_scraped = scraped.get(key)
            val_db = latest_db.get(key)
            b_scraped = bool(val_scraped) if val_scraped is not None else None
            b_db = bool(val_db) if val_db is not None else None
            if b_scraped != b_db:
                return False

    # Compare images
    scraped_imgs = scraped.get("images") or []
    db_imgs = latest_db.get("images") or []
    if len(scraped_imgs) != len(db_imgs):
        return False
    if scraped_imgs != db_imgs:
        return False

    return True



def _type_specific_values(data):
    if data["type"] == "house":
        return (
            data.get("bedrooms"),
            data.get("garage"),
            data.get("furnished"),
            data.get("terrace"),
            data.get("pool"),
        )

    return (
        None,
        None,
        None,
        None,
        None,
    )


def insert_property(data):
    conn = get_conn()
    cur = conn.cursor()

    house_land_values = _type_specific_values(data)

    cur.execute("""
        INSERT INTO properties (
            source, ad_id, property_type, listing_type,
            title, description, price, area, city, address, url,
            bedrooms, garage, furnished, terrace, pool,
            subcategory, images
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        data["source"],
        data["ad_id"],
        data["type"],
        data["listing_type"],
        data["title"],
        data["description"],
        data["price"],
        data["area"],
        data["city"],
        data["address"],
        data["url"],
        *house_land_values,
        data.get("subcategory"),
        data.get("images", []),
    ))

    conn.commit()
    cur.close()
    conn.close()


def bulk_insert_properties(items):
    """Insert multiple properties in a single connection/transaction. Returns (inserted, errors) counts."""
    if not items:
        return 0, 0

    conn = get_conn()
    cur = conn.cursor()
    inserted = 0
    errors = 0

    for data in items:
        try:
            house_land_values = _type_specific_values(data)
            cur.execute("""
                INSERT INTO properties (
                    source, ad_id, property_type, listing_type,
                    title, description, price, area, city, address, url,
                    bedrooms, garage, furnished, terrace, pool,
                    subcategory, images
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                data["source"],
                data["ad_id"],
                data["type"],
                data["listing_type"],
                data["title"],
                data["description"],
                data["price"],
                data["area"],
                data["city"],
                data["address"],
                data["url"],
                *house_land_values,
                data.get("subcategory"),
                data.get("images", []),
            ))
            inserted += 1
        except Exception as e:
            conn.rollback()
            errors += 1
            print(f"ERROR bulk-inserting {data.get('source')}/{data.get('ad_id')}: {type(e).__name__}: {e}")

    conn.commit()
    cur.close()
    conn.close()
    return inserted, errors
