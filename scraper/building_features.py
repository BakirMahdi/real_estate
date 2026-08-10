"""Built-property signal extracted from listing text (Module 6 feature engineering).

The land_* flags (land_features.py) proved that the free-text title/description
carries price signal no structured column has. The same is true for built
properties: "haut standing", "vue mer", "sans ascenseur", "récemment rénové" or
the floor number move Tunisian asking prices materially, and none of them are
DB columns. This module turns those cues into numeric features, deliberately
parallel to land_features.py: one shared extractor over accent-normalized text.

The flags are only meaningful for built properties, so `extract_building_features`
returns NaN (unknown) for land — a NaN numeric column is simply ignored by
HistGradientBoostingRegressor, so the flags never perturb land predictions.

`bldg_ascenseur` and `bldg_climatisation` are negation-aware (reusing the
amenities.py cue check): "sans ascenseur" — a strong *negative* price signal in
walk-ups — must count as 0, not 1.
"""

import re
import unicodedata

from .amenities import _is_negated

# Simple presence flags: name -> regex over accent-normalized lowercased text.
_PATTERNS = {
    "bldg_neuf": r"\bneufs?\b|\bneuves?\b|nouvelle\s+construction|construction\s+recente|jamais\s+habite",
    "bldg_renove": r"\brenov",  # rénové / rénovation / rénovée
    "bldg_haut_standing": r"haute?\s+standing|grand\s+standing|\bluxe\b|luxueu|\bprestige\b",
    "bldg_vue_mer": r"vue\s+.{0,20}\bmer\b|bord\s+de\s+mer|front\s+de\s+mer|face\s+.{0,6}\bmer\b|pieds?\s+dans\s+l.eau",
    "bldg_chauffage": r"chauffage",  # chauffage central — matches neither chauffe-eau nor climatisation
}
# Negation-aware flags: "sans ascenseur" / "pas de clim" flip to confirmed-absent (0).
_NEGATABLE_PATTERNS = {
    "bldg_ascenseur": r"ascenseur",
    "bldg_climatisation": r"climatis|\bclim\b|climatiseurs?",
}
_COMPILED = {name: re.compile(p) for name, p in _PATTERNS.items()}
_NEGATABLE_COMPILED = {name: re.compile(p) for name, p in _NEGATABLE_PATTERNS.items()}

# Floor number ("2ème étage" -> 2, "rez-de-chaussée" -> 0). Only extracted for
# apartments/studios/offices: for a house "2 étages" means a two-STOREY villa,
# not which floor it sits on, so houses get NaN. `etage\b` deliberately fails
# to match the plural "étages" (building height, not a floor).
_FLOOR_DIGIT = re.compile(r"(\d{1,2})\s*(?:er|ere|eme|e)?\s*etage\b|\betage\s+(\d{1,2})\b")
_FLOOR_WORDS = {
    "premier": 1, "deuxieme": 2, "troisieme": 3, "quatrieme": 4, "cinquieme": 5,
}
_FLOOR_WORD = re.compile(r"\b(" + "|".join(_FLOOR_WORDS) + r")\s+etage\b")
_FLOOR_RDC = re.compile(r"\brdc\b|rez[\s-]*de[\s-]*chauss")
_MAX_FLOOR = 30  # above this it's a typo/garbage, not a floor

_FLOOR_TYPES = {"apartment", "studio", "office"}

# The order the model's ColumnTransformer will see these in; keep stable.
BUILDING_FEATURE_NAMES = (
    list(_PATTERNS.keys()) + list(_NEGATABLE_PATTERNS.keys()) + ["bldg_etage"]
)

_NAN = float("nan")


def _normalize(text) -> str:
    """Lowercase and strip accents so "Rénové"/"renove" match one pattern."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.lower().split())


def _extract_floor(text):
    for match in _FLOOR_DIGIT.finditer(text):
        floor = int(match.group(1) or match.group(2))
        if floor <= _MAX_FLOOR:
            return float(floor)
    word = _FLOOR_WORD.search(text)
    if word:
        return float(_FLOOR_WORDS[word.group(1)])
    if _FLOOR_RDC.search(text):
        return 0.0
    return _NAN


def extract_building_features(property_type, title=None, description=None) -> dict:
    """Built-property flags for one listing, keyed by BUILDING_FEATURE_NAMES.

    1.0/0.0 flags (plus a numeric `bldg_etage`) for apartment/house/studio/
    office rows; every value NaN for land (the flags are meaningless there and
    left unknown so the model ignores them).
    """
    if property_type == "land" or not property_type:
        return {name: _NAN for name in BUILDING_FEATURE_NAMES}

    text = _normalize(f"{title or ''} {description or ''}")
    features = {name: (1.0 if regex.search(text) else 0.0) for name, regex in _COMPILED.items()}
    for name, regex in _NEGATABLE_COMPILED.items():
        value = 0.0
        for match in regex.finditer(text):
            if not _is_negated(text, match.start()):
                value = 1.0
                break
        features[name] = value
    features["bldg_etage"] = _extract_floor(text) if property_type in _FLOOR_TYPES else _NAN
    return features
