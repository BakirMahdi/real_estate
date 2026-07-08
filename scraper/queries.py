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
    images,
    archived
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
    include_archived=False,
    archived_only=False,
):
    conn = get_conn()
    cur = conn.cursor()

    sql = f"""
        SELECT {_PROPERTY_COLUMNS}, COUNT(*) OVER() as total_count
        FROM (
            SELECT DISTINCT ON (source, ad_id) *
            FROM properties
            ORDER BY source, ad_id, id DESC
        ) properties
        WHERE 1=1
    """
    params = []

    if archived_only:
        sql += " AND archived = TRUE"
    elif not include_archived:
        sql += " AND archived = FALSE"

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
    
    total_count = 0
    properties = []
    if rows:
        raw_properties = [_row_to_dict(cur, row) for row in rows]
        total_count = raw_properties[0]["total_count"]
        for p in raw_properties:
            p.pop("total_count", None)
        properties = raw_properties

    cur.close()
    conn.close()
    return properties, total_count


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


def get_all_properties(include_archived=False):
    conn = get_conn()
    cur = conn.cursor()
    
    if include_archived:
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
                images,
                archived
            FROM properties
            ORDER BY id
            """
        )
    else:
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
                images,
                archived
            FROM properties
            WHERE archived = FALSE
            ORDER BY id
            """
        )
    
    rows = cur.fetchall()
    properties = [_row_to_dict(cur, row) for row in rows]

    cur.close()
    conn.close()
    return properties


def search_properties_by_id(search_id, include_archived=False):
    """Search for properties by ID (exact match) or ad_id (exact match). Admin only."""
    conn = get_conn()
    cur = conn.cursor()
    
    # Try to convert to integer for exact ID match
    try:
        search_id_int = int(search_id)
        if include_archived:
            cur.execute(
                f"""
                SELECT {_PROPERTY_COLUMNS}
                FROM properties
                WHERE id = %s OR ad_id = %s
                ORDER BY id DESC
                """,
                (search_id_int, search_id)
            )
        else:
            cur.execute(
                f"""
                SELECT {_PROPERTY_COLUMNS}
                FROM properties
                WHERE (id = %s OR ad_id = %s) AND archived = FALSE
                ORDER BY id DESC
                """,
                (search_id_int, search_id)
            )
    except ValueError:
        # Not an integer, search by ad_id only with exact match
        if include_archived:
            cur.execute(
                f"""
                SELECT {_PROPERTY_COLUMNS}
                FROM properties
                WHERE ad_id = %s
                ORDER BY id DESC
                """,
                (search_id,)
            )
        else:
            cur.execute(
                f"""
                SELECT {_PROPERTY_COLUMNS}
                FROM properties
                WHERE ad_id = %s AND archived = FALSE
                ORDER BY id DESC
                """,
                (search_id,)
            )
    
    rows = cur.fetchall()
    properties = [_row_to_dict(cur, row) for row in rows]

    cur.close()
    conn.close()
    return properties


def archive_property(property_id):
    """Archive a property by ID. Admin only."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE properties SET archived = TRUE WHERE id = %s",
        (property_id,)
    )
    conn.commit()
    cur.close()
    conn.close()


def unarchive_property(property_id):
    """Unarchive a property by ID. Admin only."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE properties SET archived = FALSE WHERE id = %s",
        (property_id,)
    )
    conn.commit()
    cur.close()
    conn.close()
