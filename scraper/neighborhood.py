"""Resolve a listing to a canonical Tunisian neighborhood (micro-location).

`governorate.py` collapses a location to one of 24 governorates; this goes the
other way and keeps the *fine* locality, because for sale prices the premium is
driven by the neighborhood, not the governorate (in Grand Tunis, Les Berges du
Lac 2 vs El Omrane is a 2-3x price/m2 gap, yet both carry city="Tunis").

The neighborhood is rarely in a clean column: for Mubawab it's usually in
`address` ("Les Berges Du Lac 2, Tunis"), for Tayara sometimes in `city`, and
often only in the free-text title ("... a vendre au Lac 2"). So we match a
gazetteer of known localities across address+city first, then the title/
description, and canonicalise the many spellings ("berges du lac 2", "lac 2",
"les berges du lac 2") to a single label so the model doesn't see them as
distinct sparse categories.

Returns None when nothing matches (unknown) - the caller/model treats that as
its own bucket rather than a guess.
"""

import unicodedata

# canonical label -> list of normalized aliases (accent-stripped, lowercase).
# Matched as whole space-padded tokens, most specific (longest) alias first, so
# "lac 2" wins over a generic "lac" and "el menzah 9" over "el menzah".
_GAZETTEER = {
    # --- Grand Tunis: high-value coastal/northern belt ---
    "Gammarth": ["gammarth"],
    "La Marsa": ["la marsa", "marsa"],
    "Carthage": ["carthage"],
    "Sidi Bou Said": ["sidi bou said", "sidi bousaid"],
    "Le Kram": ["le kram", "kram"],
    "La Goulette": ["la goulette", "goulette"],
    "Jardins de Carthage": ["jardins de carthage", "jardin de carthage", "les jardins de carthage"],
    "El Aouina": ["el aouina", "l aouina", "aouina"],
    "Ain Zaghouan": ["ain zaghouan", "ain zaghouane"],
    "La Soukra": ["la soukra", "soukra"],
    # --- Grand Tunis: residential ---
    "Mutuelleville": ["mutuelleville"],
    "Montplaisir": ["montplaisir"],
    "El Omrane Superieur": ["el omrane superieur", "omrane superieur"],
    "El Omrane": ["el omrane"],
    "Cite El Khadra": ["cite el khadra", "cité el khadra", "el khadra"],
    "Le Bardo": ["le bardo", "bardo"],
    "Ariana Ville": ["ariana ville"],
    "Raoued": ["raoued"],
    "Borj Louzir": ["borj louzir"],
    "Riadh El Andalous": ["riadh el andalous", "riadh andalous", "riadh el andalus"],
    "Chotrana": ["chotrana"],
    # --- Grand Tunis south (Ben Arous) ---
    "Ezzahra": ["ezzahra", "ez zahra"],
    "Rades": ["rades"],
    "Megrine": ["megrine"],
    "Hammam Lif": ["hammam lif"],
    "Boumhel": ["boumhel", "bou mhel"],
    "Mornag": ["mornag", "mornaguia"],
    "Fouchana": ["fouchana"],
    "Borj Cedria": ["borj cedria", "borj cédria"],
    # --- Cap Bon (Nabeul) ---
    "Yasmine Hammamet": ["yasmine hammamet"],
    "Hammamet": ["hammamet"],
    "Nabeul Ville": ["nabeul ville"],
    "Dar Chaabane": ["dar chaabane", "dar chaaban"],
    "El Maamoura": ["el maamoura", "maamoura"],
    "Kelibia": ["kelibia"],
    "Soliman": ["soliman"],
    # --- Sousse / Monastir sahel ---
    "Sahloul": ["sahloul"],
    "Khezama": ["khezama"],
    "Port El Kantaoui": ["port el kantaoui", "kantaoui"],
    "Hammam Sousse": ["hammam sousse"],
    "Chott Meriem": ["chott meriem", "chott mariem", "chatt meriem"],
    "Skanes": ["skanes"],
    "Kantaoui": ["kantaoui"],
    # --- Sfax ---
    "Sakiet Ezzit": ["sakiet ezzit"],
    "Sakiet Eddaier": ["sakiet eddaier"],
    "Sfax Ville": ["sfax ville"],
    # --- Djerba / south ---
    "Houmt Souk": ["houmt souk"],
    "Midoun": ["midoun"],
    "Zarzis": ["zarzis"],
}


def _add_numbered(base_canon, aliases, count):
    """Numbered sub-areas (El Menzah 1..9, El Manar 1..3) - each number is a real
    price tier, so keep them distinct, plus a generic bucket for the un-numbered."""
    _GAZETTEER[base_canon] = list(aliases)
    for i in range(1, count + 1):
        _GAZETTEER[f"{base_canon} {i}"] = [f"{a} {i}" for a in aliases]


_add_numbered("El Menzah", ["el menzah", "el manzah", "menzah"], 9)
_add_numbered("El Manar", ["el manar", "manar"], 3)
_add_numbered("Ennasr", ["ennasr", "el nasr", "cite ennasr"], 2)
_add_numbered("El Mourouj", ["el mourouj", "mourouj"], 6)
_add_numbered("Les Berges du Lac", ["berges du lac", "les berges du lac"], 2)

# Flattened (alias, canonical) pairs, longest alias first so the most specific
# locality wins when several are substrings of one another.
_ALIAS_INDEX = sorted(
    ((alias, canonical) for canonical, aliases in _GAZETTEER.items() for alias in aliases),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _normalize(text):
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    cleaned = "".join(c if (c.isalnum() and ord(c) < 128) else " " for c in text)
    return " ".join(cleaned.split())


def _match(norm):
    if not norm:
        return None
    padded = f" {norm} "
    for alias, canonical in _ALIAS_INDEX:
        if f" {alias} " in padded:
            return canonical
    return None


def resolve_neighborhood(city, address, title=None, description=None):
    """Canonical neighborhood label, or None. Structured fields (address, city)
    are tried before the noisier free text."""
    structured = _match(_normalize(f"{address or ''} {city or ''}"))
    if structured:
        return structured
    return _match(_normalize(f"{title or ''} {description or ''}"))
