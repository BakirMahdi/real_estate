"""Feature definition shared by model training and serving.

Both the training script and the API estimator must build feature frames the
same way — a mismatch would silently skew predictions — so the single source
of truth for which columns the model sees, and their dtypes, lives here.
"""

import pandas as pd

from ..neighborhood import resolve_neighborhood
from ..governorate import resolve_delegation
from ..land_features import LAND_FEATURE_NAMES, extract_land_features
from ..building_features import BUILDING_FEATURE_NAMES, extract_building_features

# Order matters: the trained pipeline addresses columns positionally after
# the ColumnTransformer, with categoricals first.
# `neighborhood` and `delegation` are derived (see to_feature_frame), not
# stored columns - together they give the model finer location than city:
# `neighborhood` for Grand-Tunis micro-areas, `delegation` for the rural towns
# (mostly land) the neighborhood gazetteer doesn't cover.
CATEGORICAL_FEATURES = ["listing_type", "property_type", "governorate", "city", "subcategory", "neighborhood", "delegation"]
# The land_* flags are derived land-use/legal/servicing signal (NaN for
# non-land, so ignored there); they carry the attributes that otherwise make
# land the least predictable segment. See land_features.py. The bldg_* flags
# are the built-property mirror (standing, vue mer, ascenseur, floor…), NaN
# for land. See building_features.py.
NUMERIC_FEATURES = (
    ["area", "bedrooms", "garage", "furnished", "terrace", "pool"]
    + LAND_FEATURE_NAMES
    + BUILDING_FEATURE_NAMES
)
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

# Source columns to_feature_frame reads to derive `neighborhood` / `delegation`
# / the land_* flags. Callers that want these features (training load + the
# serving row) must supply the text/location columns; both already do.
NEIGHBORHOOD_SOURCE_COLUMNS = ["city", "address", "title", "description"]
DERIVED_SOURCE_COLUMNS = ["city", "address", "title", "description", "property_type"]

TARGET = "price"


def to_feature_frame(records) -> pd.DataFrame:
    """Normalize raw property dicts/rows into the frame the model expects.

    Booleans arrive from Postgres as True/False/None; cast to float so
    missing values become NaN, which HistGradientBoostingRegressor handles
    natively (no imputation needed).
    """
    df = pd.DataFrame(records)

    # Derive the location/land features from the source text, identically for
    # training and serving (both pass the source columns). Always recompute
    # rather than trusting a pre-supplied value, so the two paths can never
    # diverge.
    for col in DERIVED_SOURCE_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df["neighborhood"] = [
        resolve_neighborhood(city, address, title, description)
        for city, address, title, description in zip(
            df["city"], df["address"], df["title"], df["description"]
        )
    ]
    df["delegation"] = [
        resolve_delegation(city, address) for city, address in zip(df["city"], df["address"])
    ]
    land = pd.DataFrame(
        [
            extract_land_features(property_type, title, description, address)
            for property_type, title, description, address in zip(
                df["property_type"], df["title"], df["description"], df["address"]
            )
        ],
        index=df.index,
    )
    for name in LAND_FEATURE_NAMES:
        df[name] = land[name].to_numpy()
    building = pd.DataFrame(
        [
            extract_building_features(property_type, title, description)
            for property_type, title, description in zip(
                df["property_type"], df["title"], df["description"]
            )
        ],
        index=df.index,
    )
    for name in BUILDING_FEATURE_NAMES:
        df[name] = building[name].to_numpy()

    for col in ALL_FEATURES:
        if col not in df.columns:
            df[col] = None
    df = df[ALL_FEATURES].copy()

    for col in (
        ["garage", "furnished", "terrace", "pool", "bedrooms", "area"]
        + LAND_FEATURE_NAMES
        + BUILDING_FEATURE_NAMES
    ):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].astype("object")

    return df
