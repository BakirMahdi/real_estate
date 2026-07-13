"""One-off backfill: add the `governorate` column (if missing) and populate it
for every existing row from its city/address.

Run inside the backend container:
    docker compose exec backend python -m scraper.backfill_governorate
"""

from .db import get_conn
from .governorate import resolve_governorate


def run():
    conn = get_conn()
    cur = conn.cursor()

    # Ensure the column exists (idempotent).
    cur.execute("ALTER TABLE properties ADD COLUMN IF NOT EXISTS governorate TEXT")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_properties_governorate ON properties(governorate)"
    )
    conn.commit()

    cur.execute("SELECT id, city, address FROM properties")
    rows = cur.fetchall()

    ids = [pid for pid, _city, _address in rows]
    govs = [resolve_governorate(city, address) for _pid, city, address in rows]
    updated = len(ids)

    # One batched UPDATE instead of one per row - unnest() pairs the two
    # arrays element-wise into a set of (id, governorate) rows to join
    # against, same pattern as main.py's archive_missing_ads.
    if ids:
        cur.execute(
            """
            UPDATE properties AS p
            SET governorate = batch.gov
            FROM unnest(%s::int[], %s::text[]) AS batch(id, gov)
            WHERE p.id = batch.id
            """,
            (ids, govs),
        )

    conn.commit()

    # Quick summary of the resulting distribution.
    cur.execute(
        "SELECT governorate, COUNT(*) FROM properties GROUP BY governorate ORDER BY COUNT(*) DESC"
    )
    distribution = cur.fetchall()

    cur.close()
    conn.close()

    print(f"Backfilled governorate for {updated} rows.")
    for gov, count in distribution:
        print(f"  {gov}: {count}")


if __name__ == "__main__":
    run()
