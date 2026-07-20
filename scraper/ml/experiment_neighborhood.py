"""Does a neighborhood feature lower SALE APE? Measure before productionising.

Adds one categorical feature - the canonical neighborhood from neighborhood.py,
resolved from address/city/title/description - on top of the shipped recipe
(abs-error loss, current features) and compares APE on the same clean test fold.

Analysis only - no DB or artifact changes.

    docker exec realestate-backend python -m scraper.ml.experiment_neighborhood
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from ..db import get_conn
from ..neighborhood import resolve_neighborhood
from .features import CATEGORICAL_FEATURES, NUMERIC_FEATURES, TARGET
from .prepare_training_data import basic_filters, compute_outlier_bounds, apply_outlier_bounds
from .train_price_model import evaluate


def load_with_text():
    conn = get_conn()
    try:
        cols = "id, source, property_type, listing_type, price, area, governorate, city, " \
               "address, title, description, bedrooms, garage, furnished, terrace, pool, subcategory"
        return pd.read_sql(
            f"SELECT DISTINCT ON (source, ad_id) {cols} FROM properties "
            f"ORDER BY source, ad_id, id DESC",
            conn,
        )
    finally:
        conn.close()


def make_X(df, categoricals, numeric):
    X = pd.DataFrame(index=df.index)
    for c in categoricals:
        X[c] = df[c].astype("object")
    for c in numeric:
        X[c] = pd.to_numeric(df[c], errors="coerce")
    return X[categoricals + numeric]


def make_pipeline(categoricals, **hgb):
    encode = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
                                encoded_missing_value=-1), categoricals)],
        remainder="passthrough",
    )
    regressor = HistGradientBoostingRegressor(
        categorical_features=list(range(len(categoricals))),
        loss="absolute_error", random_state=42, **hgb,
    )
    return Pipeline([("encode", encode), ("regress", regressor)])


def run():
    df = basic_filters(load_with_text())
    df["neighborhood"] = [
        resolve_neighborhood(r.city, r.address, r.title, r.description)
        for r in df.itertuples(index=False)
    ]

    cov_all = df["neighborhood"].notna().mean() * 100
    sale_tunis = df[(df.listing_type == "sale") & (df.governorate == "Tunis")]
    cov_tunis = sale_tunis["neighborhood"].notna().mean() * 100
    print(f"Neighborhood coverage: {cov_all:.1f}% overall, "
          f"{cov_tunis:.1f}% of Tunis sale listings ({len(sale_tunis):,} rows).")
    print("Top resolved neighborhoods:")
    print(df["neighborhood"].value_counts().head(12).to_string())

    train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_df)
    train_df = apply_outlier_bounds(train_df, bounds)
    test_df = apply_outlier_bounds(test_df, bounds)
    y_tr, y_te, lt = np.log(train_df[TARGET]), np.log(test_df[TARGET]), test_df["listing_type"]
    print(f"\nTrain {len(train_df):,} | clean test fold {len(test_df):,}\n")

    base_cats = list(CATEGORICAL_FEATURES)
    configs = [
        ("shipped recipe (no neighborhood)", base_cats),
        ("+ neighborhood feature", base_cats + ["neighborhood"]),
    ]
    results = []
    for name, cats in configs:
        pipe = make_pipeline(cats).fit(make_X(train_df, cats, NUMERIC_FEATURES), y_tr)
        m = evaluate(pipe, make_X(test_df, cats, NUMERIC_FEATURES), y_te, lt)
        m["config"] = name
        results.append(m)
        print(f"  {name:<34} rent_APE={m['rent_median_ape_pct']:>5}%  "
              f"sale_APE={m['sale_median_ape_pct']:>5}%  r2={m['r2_log']}")

    b, n = results
    print("\n  Change from adding neighborhood (lower APE = better):")
    for key, label in (("rent_median_ape_pct", "rent APE"), ("sale_median_ape_pct", "sale APE")):
        print(f"    {label:<10}{b[key]:>7}%  ->{n[key]:>7}%   ({n[key] - b[key]:+.1f} pts)")


if __name__ == "__main__":
    run()
