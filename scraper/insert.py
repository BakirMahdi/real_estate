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
