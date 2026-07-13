"""One-off backfill: re-run the hardened extraction logic (area, bedrooms,
listing_type) against every already-scraped row and correct any that were
parsed wrong by the bugs fixed in scraper/scrapers/{tayara,mubawab,expat}.py
(the Arabic-surface-in-title miss, the "mois +230 caution" -> 230-bedroom
false match, and the land-ad rent/sale default fallback).

Only touches a field when the recomputed value is backed by an explicit
signal (a keyword match, a unit token, an in-range number) -- never guesses
to "fix" a value that has no signal either way, so existing correct data
isn't churned.

Run inside the backend container:
    docker compose exec backend python -m scraper.backfill_extraction            # dry run, prints a report
    docker compose exec backend python -m scraper.backfill_extraction --apply    # writes the corrections
"""

import csv
import datetime
import sys

from .db import get_conn
from .scrapers.tayara import parse_area as tayara_parse_area
from .scrapers.tayara import parse_rooms as tayara_parse_rooms
from .scrapers.tayara import RENT_KEYWORDS as TAYARA_RENT_KEYWORDS
from .scrapers.tayara import SALE_KEYWORDS as TAYARA_SALE_KEYWORDS
from .scrapers.mubawab import RENT_KEYWORDS as MUBAWAB_RENT_KEYWORDS
from .scrapers.mubawab import SALE_KEYWORDS as MUBAWAB_SALE_KEYWORDS
from .scrapers.expat import _RENT_PATH_KEYWORDS, _SALE_PATH_KEYWORDS

AREA_BOUNDS = (1, 1_000_000)
BEDROOMS_BOUNDS = (0, 20)

# The only column names this script ever writes to (see the `changes.append`
# calls below) - `field` is always one of these today, but it's interpolated
# into an f-string UPDATE below, so pin it to an explicit allowlist rather
# than trusting that invariant to hold forever.
_UPDATABLE_FIELDS = {"listing_type", "area", "bedrooms"}

_KEYWORD_SETS = {
    "tayara": (TAYARA_RENT_KEYWORDS, TAYARA_SALE_KEYWORDS),
    "mubawab": (MUBAWAB_RENT_KEYWORDS, MUBAWAB_SALE_KEYWORDS),
}


def _score_listing_type(source, title, description, url, property_type):
    """Recompute listing_type from an explicit signal only.

    Returns None when there is no reliable signal left to correct from (in
    which case the existing DB value is left untouched, since a fallback
    default is a guess, not a correction) -- except for land ads, where
    "sale" is now the deliberate default (see the extractor fixes) rather
    than an arbitrary crawl-phase guess.
    """
    text = f"{title or ''} {description or ''} {url or ''}".lower()

    if source in _KEYWORD_SETS:
        rent_kw, sale_kw = _KEYWORD_SETS[source]
        rent_score = sum(1 for kw in rent_kw if kw in text)
        sale_score = sum(1 for kw in sale_kw if kw in text)
        if rent_score > sale_score:
            return "rent"
        if sale_score > rent_score:
            return "sale"
        url_lower = (url or "").lower()
        if "a-louer" in text or "louer" in url_lower:
            return "rent"
        if "a-vendre" in text or "vendre" in url_lower:
            return "sale"
    elif source == "expat":
        url_lower = (url or "").lower()
        for kw in _SALE_PATH_KEYWORDS:
            if kw in url_lower:
                return "sale"
        for kw in _RENT_PATH_KEYWORDS:
            if kw in url_lower:
                return "rent"
        if any(kw in text for kw in ["vente", "a vendre", "vendre"]):
            return "sale"
        if any(kw in text for kw in ["location", "a louer", "louer"]):
            return "rent"

    if property_type == "land":
        return "sale"
    return None


def _bounded(value, bounds):
    if value is None:
        return None
    low, high = bounds
    return value if low <= value <= high else None


def run(apply_changes=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source, title, description, url, property_type, listing_type, area, bedrooms
        FROM properties
        """
    )
    rows = cur.fetchall()
    columns = [d[0] for d in cur.description]

    changes = []  # (id, field, old, new)

    for row in rows:
        r = dict(zip(columns, row))
        pid, source = r["id"], r["source"]

        new_listing_type = _score_listing_type(
            source, r["title"], r["description"], r["url"], r["property_type"]
        )
        if new_listing_type is not None and new_listing_type != r["listing_type"]:
            changes.append((pid, "listing_type", r["listing_type"], new_listing_type))

        # Area/bedrooms re-derivation only for Tayara, whose original values
        # came from free-text parsing we can safely redo from the stored
        # title/description. Mubawab/Expat area & bedrooms came from
        # structured page elements we no longer have, so those are only
        # bound-checked (clearly-corrupt values nulled out), never re-derived.
        if source == "tayara":
            new_area = _bounded(tayara_parse_area(f"{r['title']} {r['description']}"), AREA_BOUNDS)
            if new_area != r["area"]:
                changes.append((pid, "area", r["area"], new_area))

            if r["property_type"] == "house":
                new_bedrooms = _bounded(
                    tayara_parse_rooms(r["description"], r["title"]), BEDROOMS_BOUNDS
                )
                if new_bedrooms != r["bedrooms"]:
                    changes.append((pid, "bedrooms", r["bedrooms"], new_bedrooms))
        else:
            bounded_area = _bounded(r["area"], AREA_BOUNDS)
            if bounded_area != r["area"]:
                changes.append((pid, "area", r["area"], bounded_area))
            bounded_bedrooms = _bounded(r["bedrooms"], BEDROOMS_BOUNDS)
            if bounded_bedrooms != r["bedrooms"]:
                changes.append((pid, "bedrooms", r["bedrooms"], bounded_bedrooms))

    by_field = {}
    for pid, field, old, new in changes:
        by_field.setdefault(field, []).append((pid, old, new))

    print(f"Scanned {len(rows)} rows. Proposed corrections: {len(changes)}")
    for field, items in by_field.items():
        print(f"  {field}: {len(items)} rows")
        for pid, old, new in items[:10]:
            print(f"    id={pid}: {old!r} -> {new!r}")
        if len(items) > 10:
            print(f"    ... and {len(items) - 10} more")

    if not apply_changes:
        print("\nDry run only -- no rows were changed. Re-run with --apply to write these corrections.")
        cur.close()
        conn.close()
        return

    if changes:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = f"logs/extraction_backfill_{timestamp}.csv"
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "field", "old_value", "new_value"])
            writer.writerows(changes)
        print(f"Audit log written to {log_path}")

        for field, items in by_field.items():
            if field not in _UPDATABLE_FIELDS:
                raise ValueError(f"refusing to interpolate unrecognized column name: {field!r}")
            for pid, _old, new in items:
                cur.execute(f"UPDATE properties SET {field} = %s WHERE id = %s", (new, pid))
        conn.commit()
        print(f"Applied {len(changes)} corrections.")
    else:
        print("Nothing to apply.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run(apply_changes="--apply" in sys.argv)
