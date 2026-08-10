from .db import db_cursor


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

# A listing is versioned: a re-scrape that finds a changed field inserts a new
# row with the same (source, ad_id) rather than updating in place, so the
# same ad can have several rows. Every query that lists/counts properties
# must read through this "latest version only" view instead of the raw table,
# or edited listings show up twice (once per version).
_LATEST_PROPERTIES = """
    (SELECT DISTINCT ON (source, ad_id) *
     FROM properties
     ORDER BY source, ad_id, id DESC) properties
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
    user_id=None,
):
    # is_favorite lets the frontend show each card's saved state without an
    # N+1 request per card. Only joined when a user is actually logged in
    # (user_id is not None) - a public/logged-out request skips the join
    # entirely and every row is just marked FALSE.
    if user_id is not None:
        favorite_join = """
            LEFT JOIN favorites fav
                ON fav.user_id = %s AND fav.source = properties.source AND fav.ad_id = properties.ad_id
        """
        favorite_join_params = [user_id]
        is_favorite_select = "(fav.id IS NOT NULL) AS is_favorite"
    else:
        favorite_join = ""
        favorite_join_params = []
        is_favorite_select = "FALSE AS is_favorite"

    # _PROPERTY_COLUMNS' bare column names (id, etc.) would be ambiguous once
    # the favorites join is active (favorites also has an id column) - always
    # qualify with the properties. prefix, same fix as get_favorite_properties.
    qualified_columns = ", ".join(
        f"properties.{col.strip()}" for col in _PROPERTY_COLUMNS.strip().split(",")
    )
    sql = f"""
        SELECT {qualified_columns}, COUNT(*) OVER() as total_count, {is_favorite_select}
        FROM {_LATEST_PROPERTIES}
        {favorite_join}
        WHERE 1=1
    """
    params = list(favorite_join_params)

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

    sql += " ORDER BY properties.id DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    with db_cursor() as cur:
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

    return properties, total_count


def get_property_by_id(property_id):
    with db_cursor() as cur:
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

    return result


def get_all_properties(include_archived=False):
    where = "" if include_archived else "WHERE archived = FALSE"
    with db_cursor() as cur:
        cur.execute(
            f"""
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
            FROM {_LATEST_PROPERTIES}
            {where}
            ORDER BY id
            """
        )
        rows = cur.fetchall()
        properties = [_row_to_dict(cur, row) for row in rows]

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

    with db_cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {_LATEST_PROPERTIES} WHERE {base_where}")
        total = cur.fetchone()[0]

        cur.execute(f"SELECT count(*) FROM {_LATEST_PROPERTIES} WHERE {search_where}", search_params)
        total_filtered = cur.fetchone()[0]

        cur.execute(
            f"""
            SELECT {_PROPERTY_COLUMNS}
            FROM {_LATEST_PROPERTIES}
            WHERE {search_where}
            ORDER BY {sort_col} {sort_dir} NULLS LAST, id DESC
            LIMIT %s OFFSET %s
            """,
            (*search_params, limit, offset),
        )
        rows = cur.fetchall()
        properties = [_row_to_dict(cur, row) for row in rows]

    return {"total": total, "total_filtered": total_filtered, "items": properties}


def add_favorite(user_id, source, ad_id):
    """Save a listing for a user. Idempotent - favoriting twice is a no-op."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO favorites (user_id, source, ad_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, source, ad_id) DO NOTHING
            """,
            (user_id, source, ad_id),
        )


def remove_favorite(user_id, source, ad_id):
    """Un-save a listing for a user. Idempotent - removing a non-favorite is a no-op."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM favorites WHERE user_id = %s AND source = %s AND ad_id = %s",
            (user_id, source, ad_id),
        )


def is_favorite(user_id, source, ad_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM favorites WHERE user_id = %s AND source = %s AND ad_id = %s",
            (user_id, source, ad_id),
        )
        return cur.fetchone() is not None


def get_favorite_properties(user_id):
    """A user's saved listings, resolved to each one's latest version.

    Joins through _LATEST_PROPERTIES (not the raw table) so a favorite of a
    listing that's since been re-scraped with a change shows the current
    version, not the stale row it was originally saved from. Archived
    listings (delisted since being favorited) are excluded, same as every
    other public-facing property query.
    """
    # _PROPERTY_COLUMNS' bare column names (id, etc.) would be ambiguous once
    # joined against favorites, which also has an id column - qualify every
    # column with the properties. prefix instead of reusing it as-is.
    qualified_columns = ", ".join(
        f"properties.{col.strip()}" for col in _PROPERTY_COLUMNS.strip().split(",")
    )
    with db_cursor() as cur:
        cur.execute(
            f"""
            SELECT {qualified_columns}, TRUE AS is_favorite
            FROM {_LATEST_PROPERTIES}
            JOIN favorites f ON f.source = properties.source AND f.ad_id = properties.ad_id
            WHERE f.user_id = %s AND properties.archived = FALSE
            ORDER BY f.created_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        return [_row_to_dict(cur, row) for row in rows]


def archive_property(property_id):
    """Archive a property by ID. Admin only."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE properties SET archived = TRUE WHERE id = %s",
            (property_id,)
        )


def unarchive_property(property_id):
    """Unarchive a property by ID. Admin only."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE properties SET archived = FALSE WHERE id = %s",
            (property_id,)
        )
