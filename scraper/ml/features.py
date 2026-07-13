"""Feature definition shared by model training and serving.

Both the training script and the API estimator must build feature frames the
same way — a mismatch would silently skew predictions — so the single source
of truth for which columns the model sees, and their dtypes, lives here.
"""

import pandas as pd

# Order matters: the trained pipeline addresses columns positionally after
# the ColumnTransformer, with categoricals first.
CATEGORICAL_FEATURES = ["listing_type", "property_type", "governorate", "city", "subcategory"]
NUMERIC_FEATURES = ["area", "bedrooms", "garage", "furnished", "terrace", "pool"]
ALL_FEATURES = CATEGORICAL_FEATURES + NUMERIC_FEATURES

TARGET = "price"


def to_feature_frame(records) -> pd.DataFrame:
    """Normalize raw property dicts/rows into the frame the model expects.

    Booleans arrive from Postgres as True/False/None; cast to float so
    missing values become NaN, which HistGradientBoostingRegressor handles
    natively (no imputation needed).
    """
    df = pd.DataFrame(records)
    for col in ALL_FEATURES:
        if col not in df.columns:
            df[col] = None
    df = df[ALL_FEATURES].copy()

    for col in ["garage", "furnished", "terrace", "pool", "bedrooms", "area"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in CATEGORICAL_FEATURES:
        df[col] = df[col].astype("object")

    return df
