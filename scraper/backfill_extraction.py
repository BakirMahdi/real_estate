"""One-off backfill: re-run the hardened extraction logic (area, bedrooms,
listing_type, amenities) against every already-scraped row and correct any that
were parsed wrong by the bugs fixed in scraper/scrapers/{tayara,mubawab,expat}.py
(the Arabic-surface-in-title miss, the "mois +230 caution" -> 230-bedroom
false match, the land-ad rent/sale default fallback) and by the shared
negation-aware amenity extractor (which stops "non meublé" being read as
furnished=True and unifies the per-source keyword lists).

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

from .amenities import extract_amenities
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

AMENITY_FIELDS = ("garage", "furnished", "terrace", "pool")

# The only column names this script ever writes to (see the `changes.append`
# calls below) - `field` is always one of these today, but it's interpolated
# into an f-string UPDATE below, so pin it to an explicit allowlist rather
# than trusting that invariant to hold forever.
_UPDATABLE_FIELDS = {"listing_type", "area", "bedrooms", *AMENITY_FIELDS}

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
        SELECT id, source, title, description, url, property_type, listing_type,
               area, bedrooms, garage, furnished, terrace, pool
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

            # Re-derive bedrooms for every non-land type, mirroring the live
            # Tayara scraper (scrapers/tayara.py: `if property_type != "land"`).
            # The old gate here only re-derived houses, which is why apartments
            # and studios - the bulk of the catalogue - kept a NULL room count
            # even when their title/description says "S+2" / "3 pièces".
            if r["property_type"] != "land":
                new_bedrooms = _bounded(
                    tayara_parse_rooms(r["description"], r["title"]), BEDROOMS_BOUNDS
                )
                if new_bedrooms != r["bedrooms"]:
                    changes.append((pid, "bedrooms", r["bedrooms"], new_bedrooms))
        else:
            bounded_area = _bounded(r["area"], AREA_BOUNDS)
            if bounded_area != r["area"]:
                changes.append((pid, "area", r["area"], bounded_area))

            # Mubawab/Expat bedrooms came from structured page chips we no
            # longer have, so an existing value is only bound-checked (a
            # clearly-corrupt one gets nulled), never re-derived. But a large
            # share of non-land rows never carried a chip value at all (NULL);
            # for those we can safely fill from the stored free text with the
            # same room parser - filling a NULL cannot clobber a good value.
            bounded_bedrooms = _bounded(r["bedrooms"], BEDROOMS_BOUNDS)
            if r["bedrooms"] is not None and bounded_bedrooms != r["bedrooms"]:
                changes.append((pid, "bedrooms", r["bedrooms"], bounded_bedrooms))
            elif r["bedrooms"] is None and r["property_type"] != "land":
                parsed = _bounded(tayara_parse_rooms(r["description"], r["title"]), BEDROOMS_BOUNDS)
                if parsed is not None:
                    changes.append((pid, "bedrooms", r["bedrooms"], parsed))

        # Amenities (garage/furnished/terrace/pool). Land has none, so skip it.
        # The shared negation-aware extractor returns True (positive mention),
        # False (explicitly negated - "non meublé", "sans garage"), or None (no
        # signal). We only ever act on an explicit True/False and never write a
        # None over a stored value, matching this script's "correct only from a
        # real signal, never guess" rule.
        if r["property_type"] != "land":
            derived = extract_amenities(f"{r['title']} {r['description']}")
            for field in AMENITY_FIELDS:
                new_val = derived[field]
                if new_val is None:
                    continue
                if source == "tayara":
                    # Tayara amenities always came from this same free text, so
                    # re-derive and overwrite - this is what fixes the old
                    # negation false-positives (e.g. furnished=True on "non meublé").
                    if new_val != r[field]:
                        changes.append((pid, field, r[field], new_val))
                elif r[field] is None:
                    # Mubawab/Expat amenities partly came from structured chips we
                    # no longer have; don't clobber an existing value, only fill
                    # the NULLs where the text now gives an explicit signal.
                    changes.append((pid, field, r[field], new_val))

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
