"""Resolve a listing's location to one of Tunisia's 24 governorates.

This is a Python port of the frontend resolver (frontend/src/lib/format.ts).
Tunisia has a closed set of 24 governorates, so any location string can be
mapped deterministically: we look for a governorate name first, then fall back
to a delegation/town lookup for listings that only mention a neighborhood.
"""

import unicodedata

# Canonical governorate + accent-stripped, lowercase aliases (word/phrase match).
GOVERNORATES = [
    ("Tunis", ["tunis"]),
    ("Ariana", ["ariana", "aryanah", "aryana"]),
    ("Ben Arous", ["ben arous", "bin arous", "ben arus"]),
    ("Manouba", ["manouba", "mannouba", "la manouba", "manubah"]),
    ("Nabeul", ["nabeul", "nabul"]),
    ("Zaghouan", ["zaghouan", "zaghwan"]),
    ("Bizerte", ["bizerte", "bizerta"]),
    ("Béja", ["beja"]),
    ("Jendouba", ["jendouba", "jandouba"]),
    ("Le Kef", ["le kef", "kef"]),
    ("Siliana", ["siliana"]),
    ("Sousse", ["sousse", "sousa", "soussa"]),
    ("Monastir", ["monastir"]),
    ("Mahdia", ["mahdia"]),
    ("Sfax", ["sfax"]),
    ("Kairouan", ["kairouan", "kairaouan", "kairwan", "qayrawan"]),
    ("Kasserine", ["kasserine", "kasserin"]),
    ("Sidi Bouzid", ["sidi bouzid", "sidi bou zid"]),
    ("Gabès", ["gabes", "qabis"]),
    ("Médenine", ["medenine", "mednine"]),
    ("Tataouine", ["tataouine", "tatouine"]),
    ("Gafsa", ["gafsa"]),
    ("Tozeur", ["tozeur"]),
    ("Kébili", ["kebili", "qibili"]),
]

# Delegation / town -> governorate. Covers the Grand Tunis neighborhoods and
# the common coastal/urban towns where a listing names only the locality.
DELEGATIONS = {
    # Tunis
    "le bardo": "Tunis", "bardo": "Tunis", "la goulette": "Tunis", "goulette": "Tunis",
    "carthage": "Tunis", "le kram": "Tunis", "kram": "Tunis", "la marsa": "Tunis", "marsa": "Tunis",
    "sidi bou said": "Tunis", "el menzah": "Tunis", "menzah": "Tunis", "el manar": "Tunis",
    "manar": "Tunis", "les berges du lac": "Tunis", "berges du lac": "Tunis", "lac 1": "Tunis",
    "lac 2": "Tunis", "lac": "Tunis", "la medina": "Tunis", "el omrane": "Tunis",
    "cite el khadra": "Tunis", "el khadra": "Tunis", "el ouardia": "Tunis", "el kabaria": "Tunis",
    "kabaria": "Tunis", "sijoumi": "Tunis", "sidi hassine": "Tunis", "djebel jelloud": "Tunis",
    "ezzouhour": "Tunis", "el hrairia": "Tunis", "hrairia": "Tunis", "sidi el bechir": "Tunis",
    "mutuelleville": "Tunis", "montfleury": "Tunis", "bab bhar": "Tunis", "bab souika": "Tunis",
    # Ariana
    "ariana ville": "Ariana", "la soukra": "Ariana", "soukra": "Ariana", "raoued": "Ariana",
    "ettadhamen": "Ariana", "cite ettadhamen": "Ariana", "mnihla": "Ariana",
    "kalaat el andalous": "Ariana", "sidi thabet": "Ariana", "ennasr": "Ariana", "nasr": "Ariana",
    "borj louzir": "Ariana", "riadh el andalous": "Ariana", "chotrana": "Ariana",
    # Ben Arous
    "ben arous ville": "Ben Arous", "hammam lif": "Ben Arous", "hammam chatt": "Ben Arous",
    "bou mhel": "Ben Arous", "boumhel": "Ben Arous", "bou mhel el bassatine": "Ben Arous",
    "ezzahra": "Ben Arous", "rades": "Ben Arous", "megrine": "Ben Arous", "el mourouj": "Ben Arous",
    "mourouj": "Ben Arous", "mohamedia": "Ben Arous", "el mohamedia": "Ben Arous",
    "fouchana": "Ben Arous", "mornag": "Ben Arous", "nouvelle medina": "Ben Arous",
    # Manouba
    "manouba ville": "Manouba", "den den": "Manouba", "denden": "Manouba",
    "douar hicher": "Manouba", "oued ellil": "Manouba", "mornaguia": "Manouba",
    "borj el amri": "Manouba", "jedaida": "Manouba", "el jedaida": "Manouba",
    "tebourba": "Manouba", "el batan": "Manouba",
    # Nabeul
    "hammamet": "Nabeul", "yasmine hammamet": "Nabeul", "kelibia": "Nabeul", "korba": "Nabeul",
    "dar chaabane": "Nabeul", "beni khiar": "Nabeul", "menzel temime": "Nabeul",
    "soliman": "Nabeul", "korbous": "Nabeul", "el haouaria": "Nabeul", "haouaria": "Nabeul",
    "grombalia": "Nabeul", "bou argoub": "Nabeul", "takelsa": "Nabeul", "menzel bouzelfa": "Nabeul",
    "beni khalled": "Nabeul",
    # Zaghouan
    "zaghouan ville": "Zaghouan", "zriba": "Zaghouan", "el fahs": "Zaghouan", "en nadhour": "Zaghouan",
    "bir mchergua": "Zaghouan",
    # Sousse
    "hammam sousse": "Sousse", "kalaa kebira": "Sousse", "kalaa seghira": "Sousse",
    "akouda": "Sousse", "msaken": "Sousse", "port el kantaoui": "Sousse", "kantaoui": "Sousse",
    "hergla": "Sousse", "enfidha": "Sousse", "enfida": "Sousse", "sidi bou ali": "Sousse",
    "bouficha": "Sousse", "sahloul": "Sousse", "khezama": "Sousse",
    # Monastir
    "skanes": "Monastir", "sahline": "Monastir", "ksar hellal": "Monastir", "moknine": "Monastir",
    "jemmal": "Monastir", "bekalta": "Monastir", "teboulba": "Monastir", "sayada": "Monastir",
    "bembla": "Monastir",
    # Mahdia
    "ksour essef": "Mahdia", "el jem": "Mahdia", "chebba": "Mahdia", "souassi": "Mahdia",
    "melloulech": "Mahdia", "sidi alouane": "Mahdia",
    # Sfax
    "sakiet ezzit": "Sfax", "sakiet eddaier": "Sfax", "thyna": "Sfax", "chihia": "Sfax",
    "gremda": "Sfax", "sfax ville": "Sfax", "kerkennah": "Sfax", "agareb": "Sfax",
    "jebeniana": "Sfax", "el hencha": "Sfax", "mahres": "Sfax",
    # Bizerte
    "menzel bourguiba": "Bizerte", "menzel jemil": "Bizerte", "ras jebel": "Bizerte",
    "mateur": "Bizerte", "sejnane": "Bizerte", "tinja": "Bizerte", "el alia": "Bizerte",
    "ghar el melh": "Bizerte", "zarzouna": "Bizerte",
    # Béja
    "medjez el bab": "Béja", "testour": "Béja", "nefza": "Béja", "teboursouk": "Béja",
    "goubellat": "Béja", "amdoun": "Béja", "thibar": "Béja",
    # Jendouba
    "tabarka": "Jendouba", "ain draham": "Jendouba", "fernana": "Jendouba", "bou salem": "Jendouba",
    "ghardimaou": "Jendouba", "oued meliz": "Jendouba",
    # Le Kef
    "dahmani": "Le Kef", "tajerouine": "Le Kef", "nebeur": "Le Kef", "sakiet sidi youssef": "Le Kef",
    "kalaat senan": "Le Kef", "jerissa": "Le Kef",
    # Siliana
    "bou arada": "Siliana", "gaafour": "Siliana", "el krib": "Siliana", "makthar": "Siliana",
    "rouhia": "Siliana", "kesra": "Siliana", "bargou": "Siliana",
    # Kairouan
    "sbikha": "Kairouan", "haffouz": "Kairouan", "hajeb el ayoun": "Kairouan", "nasrallah": "Kairouan",
    "chebika": "Kairouan", "oueslatia": "Kairouan", "bou hajla": "Kairouan",
    # Kasserine
    "sbeitla": "Kasserine", "feriana": "Kasserine", "thala": "Kasserine", "foussana": "Kasserine",
    "sbiba": "Kasserine", "haidra": "Kasserine",
    # Sidi Bouzid
    "regueb": "Sidi Bouzid", "meknassy": "Sidi Bouzid", "bir el hafey": "Sidi Bouzid",
    "sidi ali ben aoun": "Sidi Bouzid", "jelma": "Sidi Bouzid", "menzel bouzaiene": "Sidi Bouzid",
    # Gabès
    "el hamma": "Gabès", "mareth": "Gabès", "matmata": "Gabès", "ghannouch": "Gabès", "metouia": "Gabès",
    # Médenine
    "djerba": "Médenine", "houmt souk": "Médenine", "midoun": "Médenine", "ajim": "Médenine",
    "zarzis": "Médenine", "ben gardane": "Médenine", "beni khedache": "Médenine",
    # Tataouine
    "ghomrassen": "Tataouine", "remada": "Tataouine", "bir lahmar": "Tataouine", "dhehiba": "Tataouine",
    # Gafsa
    "metlaoui": "Gafsa", "redeyef": "Gafsa", "moulares": "Gafsa", "el ksar": "Gafsa",
    "el guettar": "Gafsa", "sened": "Gafsa", "mdhilla": "Gafsa",
    # Tozeur
    "nefta": "Tozeur", "degache": "Tozeur", "hazoua": "Tozeur", "tameghza": "Tozeur",
    # Kébili
    "douz": "Kébili", "souk lahad": "Kébili", "faouar": "Kébili",
    # --- Additional towns & spelling variants seen in the data ---
    "hammam el ghezaz": "Nabeul", "hammam ghezaz": "Nabeul", "hammam ghezeze": "Nabeul",
    "el maamoura": "Nabeul", "maamoura": "Nabeul", "tantana": "Nabeul", "tazarka": "Nabeul",
    "barraket essahel": "Nabeul", "barraket sahel": "Nabeul", "bir bouregba": "Nabeul",
    "el mida": "Nabeul", "somaa": "Nabeul", "el mrezga": "Nabeul", "mrezga": "Nabeul",
    "chott meriem": "Sousse", "chott mariem": "Sousse", "chatt meriem": "Sousse",
    "chat mariem": "Sousse", "kalaa sghira": "Sousse", "messadine": "Sousse",
    "kondar": "Sousse", "sidi el heni": "Sousse", "m saken": "Sousse",
    "mohammedia": "Ben Arous", "naassen": "Ben Arous", "borj cedria": "Ben Arous",
    "el ain": "Sfax", "menzel chaker": "Sfax", "ghraiba": "Sfax", "esskhira": "Sfax",
    "skhira": "Sfax", "sidi mansour": "Sfax",
    "utique": "Bizerte", "raf raf": "Bizerte", "metline": "Bizerte", "cap zebib": "Bizerte",
    "cap angela": "Bizerte",
    "salakta": "Mahdia", "rejiche": "Mahdia",
    "jebel el oust": "Zaghouan", "jebel oust": "Zaghouan", "mcherga": "Zaghouan",
    "saouef": "Zaghouan",
    "el battan": "Manouba",
    "kalaat landalous": "Ariana", "aouina": "Tunis", "gammarth": "Tunis",
    "ain zaghouane": "Tunis", "ain zaghouan": "Tunis", "la pecherie": "Tunis",
    "ksibet el mediouni": "Monastir", "ouerdanine": "Monastir", "beni hassen": "Monastir",
    "maknassy": "Sidi Bouzid", "mezzouna": "Sidi Bouzid",
    "mellita": "Médenine",
    "el ksour": "Le Kef", "sers": "Le Kef",
    "rohia": "Siliana", "el aroussa": "Siliana",
    # --- Sub-divided city delegations the sources emit verbatim ---
    # Tayara/Mubawab label big cities by their administrative sub-delegation
    # ("Bizerte Nord", "Sousse Riadh", "Gabès Sud"). Without these the whole
    # string failed to match and resolve_delegation fell back to the
    # governorate, i.e. the row lost every location signal finer than the
    # governorate it already had. These were the highest-volume misses.
    "bizerte nord": "Bizerte", "bizerte sud": "Bizerte", "bizerte ville": "Bizerte",
    "bizerte centre ville": "Bizerte", "bizerte centre": "Bizerte",
    "sousse riadh": "Sousse", "sousse jaouhara": "Sousse", "sousse jawhara": "Sousse",
    "sousse medina": "Sousse", "medina sousse": "Sousse", "sousse ville": "Sousse",
    "sidi abdelhamid": "Sousse", "zaouiet sousse": "Sousse", "zaouit sousse": "Sousse",
    "sfax sud": "Sfax", "sfax ouest": "Sfax", "sfax medina": "Sfax", "sfax nord": "Sfax",
    "el hajeb": "Sfax", "merkez kamoun": "Sfax", "merkez chaabouni": "Sfax",
    "oued chaabouni": "Sfax",
    "gabes ville": "Gabès", "gabes sud": "Gabès", "gabes nord": "Gabès",
    "gabes medina": "Gabès",
    "kairouan ville": "Kairouan", "kairouan nord": "Kairouan", "kairouan sud": "Kairouan",
    "mansourah": "Kairouan",
    "gafsa sud": "Gafsa", "gafsa nord": "Gafsa",
    "mahdia ville": "Mahdia", "monastir ville": "Monastir",
    "medina monastir": "Monastir", "zaouit ksibat thrayett": "Monastir",
    "ksibet thrayett": "Monastir",
    "beja nord": "Béja", "beja sud": "Béja",
    "le kef ouest": "Le Kef", "le kef est": "Le Kef",
    "kasserine nord": "Kasserine", "kasserine sud": "Kasserine",
    # Spelling variants of towns already listed above, as the sources write them.
    "djedeida": "Manouba", "kalaat andalous": "Ariana",
    "hammam chott": "Ben Arous", "ez zeriba": "Zaghouan",
    "tezdaine": "Médenine",
}


def _normalize(text):
    """Lowercase, strip accents, and reduce punctuation to single spaces."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    cleaned = "".join(c if (c.isalnum() and ord(c) < 128) else " " for c in text)
    return " ".join(cleaned.split())


def resolve_governorate(city, address):
    """Return the governorate for a listing, falling back to the raw city and
    finally 'Tunisie' when nothing can be matched."""
    norm = _normalize(f"{address or ''} {city or ''}")
    if norm:
        padded = f" {norm} "
        for canonical, aliases in GOVERNORATES:
            for alias in aliases:
                if f" {alias} " in padded:
                    return canonical
        for key, gov in DELEGATIONS.items():
            if f" {key} " in padded:
                return gov
    city = (city or "").strip()
    return city if city else "Tunisie"


# Delegation keys matched longest-first so the most specific town wins (e.g.
# "hammam sousse" before "sousse"), same "most-specific" rule as the
# neighborhood gazetteer.
_DELEGATIONS_BY_LEN = sorted(DELEGATIONS.keys(), key=len, reverse=True)


def resolve_delegation(city, address):
    """Town/delegation-level location, one step finer than governorate.

    Used as a price-model feature: the urban `neighborhood` gazetteer only
    covers Grand-Tunis areas, so for the rural towns where most land sits the
    model otherwise has nothing between `city` (noisy free text) and
    `governorate` (too coarse - it explains almost none of land's price/m2
    spread). Returns the matched delegation, else the governorate name, else
    None (unmatched rows are left blank rather than echoing the raw city,
    which is already a separate feature).
    """
    norm = _normalize(f"{address or ''} {city or ''}")
    if norm:
        padded = f" {norm} "
        for key in _DELEGATIONS_BY_LEN:
            if f" {key} " in padded:
                return key
        for canonical, aliases in GOVERNORATES:
            for alias in aliases:
                if f" {alias} " in padded:
                    return canonical
    return None
