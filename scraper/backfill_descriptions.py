"""One-off backfill: re-fetch the detail page for every already-scraped
Tayara/Mubawab row whose stored description was cut off mid-sentence (ending
in "..."/"…"). This happened because the enrichment step used to trust any
listing-card description over 300 characters as "complete", even though both
sites truncate their card previews with a trailing ellipsis regardless of
length -- fixed going forward in scraper/scrapers/{tayara,mubawab}.py, but
already-stored rows need their real description re-fetched to benefit.

Unlike backfill_extraction.py, this makes live HTTP requests (one detail-page
fetch per affected ad), so it's slower and network-dependent.

Run inside the backend container:
    docker compose exec backend python -m scraper.backfill_descriptions            # dry run, prints a report
    docker compose exec backend python -m scraper.backfill_descriptions --apply    # writes the corrections
"""

import csv
import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .db import get_conn
from .scrapers.tayara import scrape_detail_page as tayara_scrape_detail_page
from .scrapers.mubawab import scrape_detail_page as mubawab_scrape_detail_page

DETAIL_WORKERS = int(os.getenv("SCRAPER_DETAIL_WORKERS", "10"))


def _is_truncated(description):
    return str(description or "").rstrip().endswith(("...", "…"))


def _refetch(row):
    pid, source, url, ad_id, old_description = row
    try:
        if source == "tayara":
            _images, new_description = tayara_scrape_detail_page(url)
        else:
            _images, new_description = mubawab_scrape_detail_page(url, ad_id)
    except Exception as e:
        print(f"  id={pid}: fetch failed ({e})")
        return None

    if new_description and len(new_description) > len(old_description):
        return (pid, old_description, new_description)
    return None


def run(apply_changes=False):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, source, url, ad_id, description
        FROM properties
        WHERE source IN ('tayara', 'mubawab')
          AND (description LIKE '%...' OR description LIKE '%…')
        """
    )
    rows = cur.fetchall()
    print(f"Found {len(rows)} rows with a truncated description. Re-fetching detail pages...")

    changes = []
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {executor.submit(_refetch, row): row[0] for row in rows}
        done = 0
        for future in as_completed(futures):
            result = future.result()
            if result:
                changes.append(result)
            done += 1
            if done % 200 == 0:
                print(f"  ...{done}/{len(rows)} processed, {len(changes)} improved so far")

    still_truncated = sum(1 for _pid, _old, new in changes if _is_truncated(new))
    print(f"\nRe-fetched {len(rows)} rows. {len(changes)} got a longer description.")
    if still_truncated:
        print(f"  ({still_truncated} of those are still truncated even after re-fetch -- the site's own detail page text ends that way.)")

    for pid, old, new in changes[:10]:
        print(f"  id={pid}: {len(old)} chars -> {len(new)} chars")
    if len(changes) > 10:
        print(f"  ... and {len(changes) - 10} more")

    if not apply_changes:
        print("\nDry run only -- no rows were changed. Re-run with --apply to write these corrections.")
        cur.close()
        conn.close()
        return

    if changes:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = f"logs/description_backfill_{timestamp}.csv"
        with open(log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "old_description", "new_description"])
            writer.writerows(changes)
        print(f"Audit log written to {log_path}")

        for pid, _old, new in changes:
            cur.execute("UPDATE properties SET description = %s WHERE id = %s", (new, pid))
        conn.commit()
        print(f"Applied {len(changes)} corrections.")
    else:
        print("Nothing to apply.")

    cur.close()
    conn.close()


if __name__ == "__main__":
    run(apply_changes="--apply" in sys.argv)
