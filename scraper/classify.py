"""Canonical property_type reconciliation shared by the scrapers and the backfill.

Each scraper produces two category signals of differing reliability:

  - property_type: reliable for detecting LAND (title-first, robust against ads
    that merely mention building on a plot), but the two big sources (mubawab,
    tayara) collapse every non-land property into "house".
  - subcategory: the fine-grained category (apartment / house / studio / office
    / land). Reliable for non-land — tayara reads it straight from the ad's
    metadata, mubawab from keywords — but its land detection over-triggers
    (a terrain ad that says "villa" can be flipped to house).

canonical_property_type() combines them so property_type finally reflects the
real category consistently across every source: trust property_type for the
land decision, and the fine subcategory for everything else.
"""

FINE_TYPES = ("apartment", "house", "studio", "office", "land")

# Categories more specific than a plain "house": if either field carries one of
# these, it's the real category (an apartment collapsed into "house" is still an
# apartment).
_SPECIFIC = ("apartment", "office", "studio")


def canonical_property_type(property_type, subcategory) -> str:
    """Reconcile a (property_type, subcategory) pair into one fine-grained type.

    Returns one of FINE_TYPES. Used both live (scrapers, on each parsed ad) and
    for the historical backfill (on existing rows), so the same rule governs old
    and new data.
    """
    pt = (property_type or "").strip().lower()
    sub = (subcategory or "").strip().lower()

    # Land is decided by property_type's robust title-first detector; the
    # subcategory land signal is deliberately not trusted here (it over-fires).
    if pt == "land":
        return "land"

    # Non-land: prefer a specific category from either field (subcategory first,
    # since it is the fine-grained one), otherwise fall back to house.
    for value in (sub, pt):
        if value in _SPECIFIC:
            return value
    return "house"
