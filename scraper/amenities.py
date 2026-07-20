"""Shared, negation-aware amenity extraction (garage / furnished / terrace / pool).

Single source of truth used by every scraper (tayara/mubawab/expat) and by the
extraction backfill, so a listing is labelled the same way no matter where it
comes from - the three scrapers previously each carried their own slightly
different keyword lists, which meant the same text could yield different
amenities depending on the source.

Accuracy over a plain substring match: `extract_amenities` understands
*negation*. A naive `"meublé" in text` test labels "appartement NON meublé"
(unfurnished - very common in rentals) as furnished=True, the exact opposite of
reality; likewise "sans garage", "pas de piscine", "sans balcon". Here a
keyword preceded by a negation cue (or an amenity-specific absence phrase like
"vide" for furnishing) is counted as a *confirmed-absent* signal instead.

Three-valued result per amenity:
    True  - at least one genuine positive mention
    False - only negated / absence mentions (explicitly stated to NOT have it)
    None  - not mentioned at all (unknown - callers decide how to treat it)

The backfill keeps None as "no signal, don't touch the stored value"; the live
scrapers collapse None to False, preserving their existing "advertised => has
it, otherwise assume not" convention while gaining the negation fix.
"""

import re

# Unified keyword lists (superset of what the individual scrapers used).
AMENITY_KEYWORDS = {
    "garage": ("garage", "parking couvert", "parking souterrain"),
    "furnished": ("meublé", "meublee", "meublée", "meublés", "furnished"),
    "terrace": ("terrasse", "terrace", "balcon", "balkon", "balkony"),
    "pool": ("piscine", "pool", "swimming pool"),
}

# Amenity-specific phrases that assert ABSENCE on their own (they don't contain
# the positive keyword, so the generic negation window can't catch them).
NEGATIVE_KEYWORDS = {
    "furnished": ("vide", "dégarni", "degarni", "غير مفروش"),
}

# A negation cue *immediately* before an amenity keyword flips it to absent.
# It must abut the keyword (only whitespace/punctuation between) so that a cue
# belonging to an earlier amenity doesn't leak onto a later one: in
# "sans garage, meublée" the "sans" negates garage only, not the furnishing.
# Anchored to the end of the text preceding the keyword ($).
_CUE_BEFORE_RE = re.compile(
    r"(?:\bsans|\bnon|\bpas\s+de|\bpas\s+d'|\baucune|\baucun|\bdépourvu\s+de|\bdepourvu\s+de)"
    r"[\s,]*$"
)
_ARABIC_NEGATION = "بدون"  # "without" - Arabic has no Latin word boundary


def _is_negated(text: str, keyword_start: int) -> bool:
    before = text[:keyword_start].rstrip(" ,")
    if before.endswith(_ARABIC_NEGATION):
        return True
    return bool(_CUE_BEFORE_RE.search(text[:keyword_start]))


def extract_amenities(text):
    """Map free text to {amenity: True | False | None}. See module docstring."""
    text = (text or "").lower()
    result = {}
    for amenity, keywords in AMENITY_KEYWORDS.items():
        positives = negatives = 0
        for keyword in keywords:
            for match in re.finditer(re.escape(keyword), text):
                if _is_negated(text, match.start()):
                    negatives += 1
                else:
                    positives += 1
        for negative in NEGATIVE_KEYWORDS.get(amenity, ()):
            if negative in text:
                negatives += 1

        if positives:
            result[amenity] = True
        elif negatives:
            result[amenity] = False
        else:
            result[amenity] = None
    return result


def extract_amenities_present(text):
    """Live-scraper convention: positive mention => True, otherwise False.

    Collapses the three-valued result to a plain bool (negated and unmentioned
    both become False), matching how the scrapers have always stored amenities
    while still fixing the negation false-positives.
    """
    return {amenity: (value is True) for amenity, value in extract_amenities(text).items()}
