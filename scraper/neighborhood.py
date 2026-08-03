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
    "Mutuelleville": ["mutuelleville", "mutuelle ville"],
    "Montplaisir": ["montplaisir"],
    "Centre Urbain Nord": ["centre urbain nord", "centre urbain"],
    "Tunis Centre": ["tunis ville", "tunis centre"],
    "Lafayette": ["centre ville lafayette", "lafayette", "la fayette"],
    "Le Belvedere": ["tunis belvedere", "belvedere"],
    "Ettahrir": ["ettahrir superieur", "ettahrir", "el tahrir"],
    "El Agba": ["el agba", "agba"],
    "Alain Savary": ["alain savary"],
    "Cite Olympique": ["cite olympique"],
    "Cite Des Jardins": ["cite des jardins", "cite jardins", "cite jardin"],
    "Monfleury": ["monfleury", "montfleury"],
    "Khaznadar": ["khaznadar"],
    "Kheireddine Pacha": ["kheireddine pacha", "kheireddine"],
    "Sidi Bechir": ["sidi el bechir", "sidi bechir"],
    "Ibn Sina": ["ibn sina"],
    "Bellevue": ["bellevue"],
    "Sejoumi": ["sejoumi", "sijoumi"],
    "Sidi Daoud": ["sidi daoud"],
    "El Omrane Superieur": ["el omrane superieur", "omrane superieur"],
    "El Omrane": ["el omrane"],
    "Cite El Khadra": ["cite el khadra", "cité el khadra", "el khadra"],
    "Le Bardo": ["le bardo", "bardo"],
    "Ariana Ville": ["ariana ville", "ariana centre"],
    "Raoued": ["raoued"],
    "Borj Louzir": ["borj louzir"],
    "Riadh El Andalous": [
        "riadh el andalous", "riadh andalous", "riadh el andalus", "riadh al andalous",
    ],
    "Chotrana": ["chotrana"],
    "Cite El Ghazela": ["cite el ghazela", "el ghazela", "ghazela"],
    "Medina Jedida": ["medina jedida"],
    "Cite Ennkhilet": ["cite ennkhilet", "cite el nakhilet", "ennkhilet", "nakhilet"],
    "Ariana Essoughra": ["ariana essoughra", "ariana soughra", "petite ariana"],
    "Nouvelle Ariana": ["nouvelle ariana"],
    "Cite Hedi Nouira": ["cite hedi nouira"],
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
    "Neapolis": ["neapolis"],
    "Cite El Wafa": ["cite el wafa"],
    "Sidi El Mahrsi": ["sidi el mahrsi", "sidi mahrsi"],
    "Dar Chaabane": ["dar chaabane", "dar chaaban"],
    "El Maamoura": ["el maamoura", "maamoura"],
    "Kelibia": ["kelibia"],
    "Soliman": ["soliman"],
    # --- Sousse / Monastir sahel ---
    "Sahloul": ["sahloul"],
    "Khezama": ["khezama", "khzema"],
    "Port El Kantaoui": ["port el kantaoui", "kantaoui"],
    "Hammam Sousse": ["hammam sousse"],
    "Chott Meriem": ["chott meriem", "chott mariem", "chatt meriem", "chatt mariem"],
    "Skanes": ["skanes"],
    "Kantaoui": ["kantaoui"],
    "Sousse Medina": ["sousse medina", "medina sousse"],
    "Sousse Riadh": ["sousse riadh"],
    "Sousse Jaouhara": ["sousse jaouhara", "sousse jawhara"],
    "Sousse Corniche": ["sousse corniche", "corniche sousse"],
    "Sidi Abdelhamid": ["sousse sidi abdelhamid", "sidi abdelhamid"],
    "Zaouiet Sousse": ["zaouiet sousse", "zaouit sousse"],
    "Bouhsina": ["bouhssina", "bouhsina"],
    # --- Sfax ---
    "Sakiet Ezzit": ["sakiet ezzit"],
    "Sakiet Eddaier": ["sakiet eddaier"],
    "Sfax Ville": ["sfax ville"],
    # Sfax addresses are given as the arterial road ("Route de Teniour km 8"),
    # not a named quarter, and the road is what locates a parcel there - each
    # one runs out of the city into progressively cheaper land. Sfax was the
    # worst-scoring governorate (47.8% APE) and most of its rows had nothing
    # finer than the governorate before these.
    "Route Manzel Chaker": ["route manzel chaker", "route menzel chaker"],
    "Route Teniour": ["route teniour", "route taniour"],
    "Route Lafrane": ["route lafrane", "route el afrane", "route afrane"],
    "Route Matar": ["route matar"],
    "Route Saltnia": ["route saltnia", "route saltania"],
    "Route Sokra": ["route sokra", "route soukra"],
    "Route Mharza": ["route mharza"],
    "Route Gabes": ["route de gabes", "route gabes"],
    "Route Tunis": ["route de tunis", "route tunis"],
    "Route Mahdia": ["route mehdia", "route mahdia", "route de mahdia"],
    "Route Aeroport": ["route de l aeroport", "route aeroport"],
    "Avenue Teboulbi": ["avenue teboulbi", "teboulbi"],
    # --- Bizerte ---
    "Bizerte Corniche": ["bizerte le corniche", "bizerte corniche"],
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
_add_numbered("Charguia", ["charguia", "chargia"], 2)

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
