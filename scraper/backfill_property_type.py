"""Backfill: make property_type the correct fine-grained category everywhere.

Historically one source set a real property_type; `mubawab` and `tayara`
collapsed every non-land ad into "house", so ~8k apartments, studios and offices
were mislabelled, and a keyword bug flipped some terrains' subcategory to house.
This re-derives the canonical category for every row from its existing
(property_type, subcategory) pair — see scraper/classify.py, the
same rule the scrapers now apply live — and writes property_type = subcategory
= that canonical value. Rows that become `land` have their house-only
attributes (bedrooms/garage/furnished/terrace/pool) cleared, since they don't
apply to a plot.

Run inside the backend container:
    docker compose exec backend python -m scraper.backfill_property_type            # dry run
    docker compose exec backend python -m scraper.backfill_property_type --apply    # write changes
"""

import csv
import datetime
import sys
from collections import Counter

from .classify import canonical_property_type
from .db import get_conn

HOUSE_ONLY_ATTRS = ("bedrooms", "garage", "furnished", "terrace", "pool")


def run(apply_changes=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, source, property_type, subcategory FROM properties")
    rows = cur.fetchall()

    changes = []  # (id, source, old_type, old_sub, new_type)
    transitions = Counter()  # (old_type -> new_type) tallies
    for pid, source, pt, sub in rows:
        new_type = canonical_property_type(pt, sub)
        # A row needs fixing if its type is wrong OR its subcategory no longer
        # matches the canonical type (we keep the two columns in sync).
        if new_type != pt or (sub or "") != new_type:
            changes.append((pid, source, pt, sub, new_type))
            transitions[(pt, new_type)] += 1

    print(f"Scanned {len(rows)} rows. Rows to update: {len(changes)}\n")
    print("Transitions (old property_type -> new property_type):")
    for (old, new), n in sorted(transitions.items(), key=lambda kv: -kv[1]):
        marker = "" if old != new else "   (subcategory-only fix)"
        print(f"    {old or '∅':<10} -> {new:<10} {n}{marker}")

    if not apply_changes:
        print("\nDry run only -- no rows changed. Re-run with --apply to write these corrections.")
        cur.close()
        conn.close()
        return

    if not changes:
        print("\nNothing to apply.")
        cur.close()
        conn.close()
        return

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"logs/classification_backfill_{timestamp}.csv"
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "source", "old_property_type", "old_subcategory", "new_type"])
        for pid, source, pt, sub, new_type in changes:
            writer.writerow([pid, source, pt, sub, new_type])
    print(f"\nAudit log written to {log_path}")

    # Batch by target type: one UPDATE per distinct new_type. Land also clears
    # the house-only attributes.
    by_type = {}
    for pid, _source, _pt, _sub, new_type in changes:
        by_type.setdefault(new_type, []).append(pid)

    for new_type, ids in by_type.items():
        if new_type == "land":
            clears = ", ".join(f"{attr} = NULL" for attr in HOUSE_ONLY_ATTRS)
            cur.execute(
                f"""
                UPDATE properties
                SET property_type = 'land', subcategory = 'land', {clears}
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
        else:
            cur.execute(
                """
                UPDATE properties
                SET property_type = %s, subcategory = %s
                WHERE id = ANY(%s)
                """,
                (new_type, new_type, ids),
            )
        print(f"    {new_type}: updated {len(ids)} rows")

    conn.commit()
    print(f"\nApplied {len(changes)} reclassifications.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    run(apply_changes="--apply" in sys.argv)
