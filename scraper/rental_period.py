"""Detect short-term (nightly/weekly) rental pricing from listing text.

Tunisian sites file vacation rentals priced "par nuit" / "par jour" /
"par semaine" under the same rent category as ordinary monthly leases, with
the short-term amount in the price field. A 60 m2 apartment at 150 TND *per
night* and one at 900 TND *per month* differ ~5x in price-per-m2, so mixing
them smears the rent price distribution badly enough that the training
outlier fence for rent/apartment degenerates (it flagged 0 of ~1500 rows).
The price model predicts monthly rent, so these rows are excluded from
training (see prepare_training_data.basic_filters).

Kept deliberately parallel to amenities.py / land_features.py: one shared
extractor, accent-normalized text, precision over recall — an ambiguous
mention ("location vacances" with no explicit period) is NOT treated as
short-term, since seasonal lets are often still priced monthly.
"""

import re
import unicodedata

# Patterns run over accent-normalized, lowercased text. Ordered most-specific
# first; the first period detected wins (a listing quoting both nightly and
# weekly rates is short-term either way).
_NIGHTLY = re.compile(
    r"\bpar\s+nuit"                     # "500 dt par nuit"
    r"|\bnuitees?\b"                     # "la nuitée" — unambiguous
    r"|\d[\s.,]*(?:dt|tnd|dinars?)?\s*(?:/|la\s+)nuit\b"  # "150dt la nuit", "150/nuit"
    r"|\bpar\s+jour\b"
    r"|/\s*jour\b"                       # "80/jour"
    r"|\bjournaliere?\b"                 # "location journalière"
    r"|\bpar\s+week\s*-?\s*end\b"
)
_WEEKLY = re.compile(
    r"\bpar\s+semaine\b"
    r"|/\s*semaine\b"
    r"|\bhebdomadaire"
    r"|\d[\s.,]*(?:dt|tnd|dinars?)?\s*(?:/|la\s+)semaine\b"  # "800 la semaine"
)


def _normalize(text) -> str:
    """Lowercase and strip accents so "Nuitée"/"nuitee" match one pattern."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.lower().split())


def detect_rental_period(title=None, description=None):
    """Return "nightly" or "weekly" when the text prices the let short-term,
    else None (no explicit period — assumed monthly, the sites' default).

    Only meaningful for rent listings; callers should not bother for sales.
    """
    text = _normalize(f"{title or ''} {description or ''}")
    if not text:
        return None
    if _NIGHTLY.search(text):
        return "nightly"
    if _WEEKLY.search(text):
        return "weekly"
    return None
