"""Validate and run SELECT queries the Gemini agent writes for itself.

This is defense in depth on top of the real backstop, which is that the
query runs as the `agent_ro` Postgres role (see db_access.py) that only has
SELECT granted on `properties`. Even a validation bug here can't leak
`users` rows or write data, because the DB itself will refuse.
"""

import re

from .db_access import get_readonly_conn

MAX_ROWS = 200

# Raw technical identifiers that must never reach the agent as bare numbers
# (so they can't be shown to a user as a "reference"). Stripped from every
# result set regardless of what the query SELECTs. When `id` is selected it is
# still turned into a clickable `fiche_url` (see run_query) - the number ends
# up only inside a link href, never as a standalone value.
HIDDEN_COLUMNS = {"id", "ad_id"}

# A single leading SELECT/WITH, case-insensitive, optionally preceded by
# whitespace or comments-as-whitespace is what we accept. Multiple
# semicolon-separated statements are rejected outright: psycopg2/libpq will
# happily execute all of them in one round trip, which is exactly the
# "stack a second statement" injection this guards against.
_ALLOWED_START = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|grant|revoke|truncate|create|copy|"
    r"pg_sleep|pg_read_file|dblink)\b",
    re.IGNORECASE,
)


class UnsafeQuery(Exception):
    pass


def _validate(sql: str) -> None:
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        raise UnsafeQuery("Only a single statement is allowed.")
    if not _ALLOWED_START.match(stripped):
        raise UnsafeQuery("Only SELECT/WITH queries are allowed.")
    if _FORBIDDEN_KEYWORDS.search(stripped):
        raise UnsafeQuery("Query contains a forbidden keyword.")


def run_query(sql: str) -> dict:
    """Execute an agent-generated SELECT and return up to MAX_ROWS rows.

    Raises UnsafeQuery before ever touching the DB if the query doesn't
    look like a single read-only statement.
    """
    _validate(sql)

    conn = get_readonly_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql)
        all_columns = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS)
        cur.close()

        id_idx = next((i for i, c in enumerate(all_columns) if c.lower() == "id"), None)
        keep = [i for i, c in enumerate(all_columns) if c.lower() not in HIDDEN_COLUMNS]

        columns = [all_columns[i] for i in keep]
        out_rows = [[row[i] for i in keep] for row in rows]

        # Expose the on-site detail-page link derived from the (hidden) id, so
        # the agent can present listings as clickable links without ever
        # seeing/printing the raw id number.
        if id_idx is not None:
            columns.append("fiche_url")
            for out_row, raw in zip(out_rows, rows):
                out_row.append(f"/property/{raw[id_idx]}")

        return {
            "columns": columns,
            "rows": out_rows,
            "truncated": len(rows) == MAX_ROWS,
        }
    finally:
        conn.close()
