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
    governorate,
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
        # The "Ville" filter selects a governorate (see frontend dropdown).
        sql += " AND LOWER(governorate) = LOWER(%s)"
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
                governorate,
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
                governorate,
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


_ADMIN_SORT_COLUMNS = {
    "id": "id",
    "title": "title",
    "location": "COALESCE(governorate, city, address)",
    "subcategory": "subcategory",
    "listing_type": "listing_type",
    "price": "price",
    "area": "area",
    "bedrooms": "bedrooms",
    "source": "source",
}


def search_properties_admin(
    search=None,
    archived_only=False,
    offset=0,
    limit=25,
    sort_by="id",
    sort_dir="desc",
    city=None,
    subcategory=None,
    listing_type=None,
    min_price=None,
    max_price=None,
    min_area=None,
    max_area=None,
    bedrooms=None,
):
    """Server-side paginated search for the admin archiving DataTable.

    `search` matches (as a single free-text term) against ad_id, title,
    city, address, governorate and source. The remaining params are the same
    structured filters as the public catalog search (governorate, category,
    transaction type, price/surface range, bedrooms) and combine with
    `search` (AND). `archived_only` restricts to archived rows; otherwise
    both archived and non-archived rows are included. Sorting and pagination
    happen in SQL so only one page of rows ever reaches the browser,
    regardless of how large the properties table gets.

    Returns a dict with:
      - total: row count for the current archived_only scope (unfiltered by
        the search term/structured filters) — DataTables' "recordsTotal"
      - total_filtered: row count after also applying the search term and
        structured filters — DataTables' "recordsFiltered", used to compute
        the page count
      - items: the current page of properties
    """
    conn = get_conn()
    cur = conn.cursor()

    sort_col = _ADMIN_SORT_COLUMNS.get(sort_by, "id")
    sort_dir = "ASC" if str(sort_dir).lower() == "asc" else "DESC"

    base_conditions = []
    if archived_only:
        base_conditions.append("archived = TRUE")
    base_where = " AND ".join(base_conditions) if base_conditions else "TRUE"

    search_conditions = list(base_conditions)
    search_params = []
    if search and search.strip():
        term = search.strip()
        like = f"%{term}%"
        sub = [
            "title ILIKE %s",
            "city ILIKE %s",
            "address ILIKE %s",
            "governorate ILIKE %s",
            "source ILIKE %s",
            "ad_id ILIKE %s",
        ]
        sub_params = [like, like, like, like, like, like]
        search_conditions.append("(" + " OR ".join(sub) + ")")
        search_params.extend(sub_params)
    if city:
        search_conditions.append("LOWER(governorate) = LOWER(%s)")
        search_params.append(city)
    if subcategory:
        search_conditions.append("subcategory = %s")
        search_params.append(subcategory)
    if listing_type:
        search_conditions.append("listing_type = %s")
        search_params.append(listing_type)
    if min_price is not None:
        search_conditions.append("price >= %s")
        search_params.append(min_price)
    if max_price is not None:
        search_conditions.append("price <= %s")
        search_params.append(max_price)
    if min_area is not None:
        search_conditions.append("area >= %s")
        search_params.append(min_area)
    if max_area is not None:
        search_conditions.append("area <= %s")
        search_params.append(max_area)
    if bedrooms is not None:
        search_conditions.append("bedrooms >= %s")
        search_params.append(bedrooms)
    search_where = " AND ".join(search_conditions) if search_conditions else "TRUE"

    cur.execute(f"SELECT count(*) FROM properties WHERE {base_where}")
    total = cur.fetchone()[0]

    cur.execute(f"SELECT count(*) FROM properties WHERE {search_where}", search_params)
    total_filtered = cur.fetchone()[0]

    cur.execute(
        f"""
        SELECT {_PROPERTY_COLUMNS}
        FROM properties
        WHERE {search_where}
        ORDER BY {sort_col} {sort_dir} NULLS LAST, id DESC
        LIMIT %s OFFSET %s
        """,
        (*search_params, limit, offset),
    )

    rows = cur.fetchall()
    properties = [_row_to_dict(cur, row) for row in rows]

    cur.close()
    conn.close()
    return {"total": total, "total_filtered": total_filtered, "items": properties}


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
