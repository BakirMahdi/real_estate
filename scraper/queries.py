from .db import get_conn


def _row_to_dict(cursor, row):
    return {desc[0]: row[idx] for idx, desc in enumerate(cursor.description)}


_PROPERTY_COLUMNS = """
    id,
    source,
    ad_id,
    property_type,
    listing_type,
    title,
    description,
    price,
    area,
    city,
    address,
    url,
    bedrooms,
    garage,
    furnished,
    terrace,
    pool,
    subcategory,
    images
"""


def get_properties(
    city=None,
    property_type=None,
    listing_type=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    bedrooms=None,
    query=None,
    subcategory=None,
    limit=20,
    offset=0,
):
    conn = get_conn()
    cur = conn.cursor()

    sql = f"""
        SELECT {_PROPERTY_COLUMNS}
        FROM properties
        WHERE 1=1
    """
    params = []

    if city:
        sql += " AND LOWER(city) = LOWER(%s)"
        params.append(city)
    if property_type:
        sql += " AND property_type = %s"
        params.append(property_type)
    if listing_type:
        sql += " AND listing_type = %s"
        params.append(listing_type)
    if min_price is not None:
        sql += " AND price >= %s"
        params.append(min_price)
    if max_price is not None:
        sql += " AND price <= %s"
        params.append(max_price)
    if min_area is not None:
        sql += " AND area >= %s"
        params.append(min_area)
    if max_area is not None:
        sql += " AND area <= %s"
        params.append(max_area)
    if bedrooms is not None:
        sql += " AND bedrooms >= %s"
        params.append(bedrooms)
    if subcategory:
        sql += " AND subcategory = %s"
        params.append(subcategory)
    if query:
        sql += " AND (title ILIKE %s OR description ILIKE %s OR city ILIKE %s OR address ILIKE %s)"
        query_param = f"%{query}%"
        params.extend([query_param, query_param, query_param, query_param])

    sql += " ORDER BY id DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    properties = [_row_to_dict(cur, row) for row in rows]

    cur.close()
    conn.close()
    return properties


def get_property_by_id(property_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT {_PROPERTY_COLUMNS}
        FROM properties
        WHERE id = %s
        """,
        (property_id,),
    )
    row = cur.fetchone()
    result = _row_to_dict(cur, row) if row else None

    cur.close()
    conn.close()
    return result


def get_all_properties():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            source,
            ad_id,
            property_type,
            listing_type,
            title,
            description,
            price,
            area,
            city,
            address,
            url,
            subcategory,
            images
        FROM properties
        ORDER BY id
        """
    )
    rows = cur.fetchall()
    properties = [_row_to_dict(cur, row) for row in rows]

    cur.close()
    conn.close()
    return properties
