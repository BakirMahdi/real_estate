"""Land-specific signal extracted from listing text (Module 6 feature engineering).

A land plot's price is driven almost entirely by attributes that live only in
the free-text title/description - land use (agricultural vs residential vs
touristic...), legal title, servicing (utilities on site), beachfront, road
access - none of which are structured columns. Without them the price model
sees a 300 m2 titled beachfront building plot and a 300 m2 untitled
agricultural strip as identical, which is the main reason land is by far the
least accurate segment (median APE ~48% vs ~18% for apartments).

This module turns those cues into numeric 0/1 flags. They're only meaningful
for land, so `extract_land_features` returns NaN (unknown) for every other
property type - a NaN numeric column is simply ignored by
HistGradientBoostingRegressor, so the flags never perturb apartment/house
predictions. Kept deliberately parallel to `amenities.py`: one shared,
tested extractor rather than logic scattered across callers.
"""

import re
import unicodedata

# Each land flag -> regex over accent-normalized, lowercased text. Coverage of
# each individual flag across land listings is modest (5-30%), but together
# they let the model separate the order-of-magnitude price/m2 gap between, say,
# agricultural land and a titled residential building plot.
_PATTERNS = {
    "land_agricole": r"agricole|\bferme\b|olivier|verger",
    "land_industriel": r"industriel",
    "land_touristique": r"touristique",
    "land_residentiel": r"residentiel|habitation",
    "land_titled": r"titre\s+bleu|titre\s+foncier|titre\s+individuel|\btf\b|titre\s+de\s+propriete",
    "land_serviced": r"viabilis|\bsteg\b|sonede|raccorde",
    "land_beachfront": r"vue\s+mer|bord\s+de\s+mer|\bsur\s+mer|face\s+.{0,6}mer|\bplage\b",
    "land_fenced": r"clotur",
    "land_lotissement": r"lotissement",
    "land_road_access": r"\bacces\b|goudron|\broute\b|\bpiste\b",
}
_COMPILED = {name: re.compile(pattern) for name, pattern in _PATTERNS.items()}

# "constructible" is three-valued: explicitly buildable, explicitly not, or
# unmentioned - and the negative form must win, so it's handled separately from
# the simple presence flags above.
_CONSTRUCTIBLE = re.compile(r"constructible")
_NON_CONSTRUCTIBLE = re.compile(r"non\s+constructible|inconstructible")

# The order the model's ColumnTransformer will see these in; keep stable.
LAND_FEATURE_NAMES = list(_PATTERNS.keys()) + ["land_constructible"]


def _normalize(text) -> str:
    """Lowercase and strip accents so "Agricole"/"agricole" match one pattern."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.lower().split())


def extract_land_features(property_type, title=None, description=None, address=None) -> dict:
    """Land-use/legal/servicing flags for one listing, keyed by LAND_FEATURE_NAMES.

    Returns 1.0/0.0 for land rows and NaN for every other property type (the
    flags are meaningless for a built home and left unknown so the model
    ignores them). `land_constructible` is 0.0 when the text says
    "non constructible", 1.0 when it says "constructible", else 0.0.
    """
    if property_type != "land":
        return {name: float("nan") for name in LAND_FEATURE_NAMES}

    text = _normalize(f"{title or ''} {description or ''} {address or ''}")
    features = {name: (1.0 if regex.search(text) else 0.0) for name, regex in _COMPILED.items()}
    features["land_constructible"] = (
        0.0 if _NON_CONSTRUCTIBLE.search(text) else (1.0 if _CONSTRUCTIBLE.search(text) else 0.0)
    )
    return features
