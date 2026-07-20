"""Experiment: how far can we push the price model's APE down?

Runs a chain of configurations, each adding ONE lever on top of the previous,
and evaluates every one of them on the *same* clean held-out test fold so the
median-APE numbers are directly comparable and each lever's contribution is
isolated:

  C0  baseline        - exactly the production recipe (current features, default
                        HGB, outliers dropped). This is the "after the bedrooms
                        backfill" reference point.
  C1  + location prior- adds one numeric feature: a smoothed log(price/m2) for
                        the row's (listing_type, property_type, city), learned
                        from the TRAIN fold only (comps-style location signal).
  C2  + keep no-area  - stops discarding the ~25% of listings with no area; they
                        join the training set (HGB handles the NaN area) instead
                        of being thrown away.
  C3  + tuned HGB     - a stronger gradient-boosting configuration.

Honesty of the location feature: it is fit on the training fold only and each
group's mean is smoothed toward a coarser prior, so a test listing is encoded
purely from other (training) listings - it never sees its own price. The test
fold is identical and clean (real area, outliers removed) for every config.

Analysis only: does not touch the DB or the served price_model.joblib artifact.

    docker exec realestate-backend python -m scraper.ml.experiment_improve_ape
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .features import CATEGORICAL_FEATURES
from .train_price_model import evaluate
from .prepare_training_data import (
    MIN_SALE_PRICE,
    MIN_RENT_PRICE,
    compute_outlier_bounds,
    load_raw_properties,
)

BASE_NUMERIC = ["area", "bedrooms", "garage", "furnished", "terrace", "pool"]
LOC_FEATURE = "loc_log_ppm2"


# --------------------------------------------------------------------------- #
# Data loading (a basic_filters variant that KEEPS missing-area rows so config
# C2 can decide to use them, rather than dropping them up front).
# --------------------------------------------------------------------------- #
def load_base() -> pd.DataFrame:
    df = load_raw_properties()
    df = df.dropna(subset=["price", "governorate"]).copy()
    is_sale = df["listing_type"] == "sale"
    df = df[
        (is_sale & (df["price"] > MIN_SALE_PRICE))
        | (~is_sale & (df["price"] > MIN_RENT_PRICE))
    ]
    # Drop only a non-positive area (0 with a real price is garbage); a missing
    # area is "unknown", which we keep so C2 can feed it to the NaN-aware model.
    df = df[df["area"].isna() | (df["area"] > 0)]
    return df.reset_index(drop=True)


def apply_fence(df: pd.DataFrame, bounds: pd.DataFrame) -> pd.DataFrame:
    """Keep rows inside their group's Tukey fence on log(price/area). Rows with
    no area (NaN log) fall outside `between` and are dropped here - fencing is
    only meaningful where area exists."""
    tmp = df.copy()
    tmp["log_ppm2"] = np.log(tmp["price"] / tmp["area"])
    joined = tmp.join(bounds, on=["listing_type", "property_type"])
    keep = joined["log_ppm2"].between(
        joined["lower"].fillna(-np.inf), joined["upper"].fillna(np.inf)
    )
    return df[keep.to_numpy()].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Location prior: smoothed target encoding of log(price/area) by location,
# learned on the training fold only.
# --------------------------------------------------------------------------- #
def build_location_prior(train_df: pd.DataFrame, smoothing: float = 15.0):
    t = train_df[["listing_type", "property_type", "governorate", "city", "price", "area"]].copy()
    t = t[t["area"].notna() & (t["area"] > 0)]
    t["y"] = np.log(t["price"] / t["area"])

    prior = t.groupby(["listing_type", "property_type"])["y"].mean().rename("prior").reset_index()
    global_mean = float(t["y"].mean())

    def smoothed(keys):
        g = t.groupby(keys)["y"].agg(mean="mean", size="size").reset_index()
        g = g.merge(prior, on=["listing_type", "property_type"], how="left")
        g["enc"] = (g["size"] * g["mean"] + smoothing * g["prior"]) / (g["size"] + smoothing)
        return g

    city_enc = smoothed(["listing_type", "property_type", "city"])[
        ["listing_type", "property_type", "city", "enc"]
    ].rename(columns={"enc": "city_enc"})
    gov_enc = smoothed(["listing_type", "property_type", "governorate"])[
        ["listing_type", "property_type", "governorate", "enc"]
    ].rename(columns={"enc": "gov_enc"})

    def transform(df: pd.DataFrame) -> np.ndarray:
        d = df[["listing_type", "property_type", "governorate", "city"]].copy()
        d = d.merge(city_enc, on=["listing_type", "property_type", "city"], how="left")
        d = d.merge(gov_enc, on=["listing_type", "property_type", "governorate"], how="left")
        d = d.merge(prior, on=["listing_type", "property_type"], how="left")
        return (
            d["city_enc"].fillna(d["gov_enc"]).fillna(d["prior"]).fillna(global_mean).to_numpy()
        )

    return transform


# --------------------------------------------------------------------------- #
# Feature frame + pipeline builders (generic over the feature list, unlike the
# production ones which hard-code ALL_FEATURES).
# --------------------------------------------------------------------------- #
def make_X(df: pd.DataFrame, numeric, loc_transform=None) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in CATEGORICAL_FEATURES:
        X[c] = df[c].astype("object")
    for c in BASE_NUMERIC:
        if c in numeric:
            X[c] = pd.to_numeric(df[c], errors="coerce")
    if LOC_FEATURE in numeric:
        X[LOC_FEATURE] = loc_transform(df)
    return X[CATEGORICAL_FEATURES + numeric]


def make_pipeline(numeric, **hgb) -> Pipeline:
    encode = ColumnTransformer(
        [(
            "cat",
            OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1),
            CATEGORICAL_FEATURES,
        )],
        remainder="passthrough",
    )
    regressor = HistGradientBoostingRegressor(
        categorical_features=list(range(len(CATEGORICAL_FEATURES))),
        random_state=42,
        **hgb,
    )
    return Pipeline([("encode", encode), ("regress", regressor)])


TUNED = dict(
    learning_rate=0.05,
    max_iter=700,
    max_leaf_nodes=63,
    min_samples_leaf=25,
    l2_regularization=1.0,
    early_stopping=True,
    validation_fraction=0.1,
    n_iter_no_change=25,
)


def run() -> None:
    base = load_base()
    with_area = base[base["area"].notna() & (base["area"] > 0)].reset_index(drop=True)
    no_area = base[base["area"].isna()].reset_index(drop=True)
    print(
        f"Loaded {len(base):,} filtered rows: {len(with_area):,} with area, "
        f"{len(no_area):,} without area.  "
        f"bedrooms present on {base['bedrooms'].notna().mean() * 100:.1f}% of rows "
        f"(was ~11% before the backfill)."
    )

    # One split, reused by every config. The fence + clean test fold are built
    # once so all configs are graded on the identical held-out rows.
    train_wa, test_wa = train_test_split(with_area, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_wa)
    train_inliers = apply_fence(train_wa, bounds)
    test_clean = apply_fence(test_wa, bounds)
    print(
        f"Train (with area, inliers): {len(train_inliers):,}   "
        f"Clean test fold (fixed for all configs): {len(test_clean):,}"
    )

    loc = build_location_prior(train_inliers)
    y_test = np.log(test_clean["price"])
    lt_test = test_clean["listing_type"]

    results = []

    def measure(name, train_df, numeric, hgb):
        X_tr, y_tr = make_X(train_df, numeric, loc), np.log(train_df["price"])
        pipe = make_pipeline(numeric, **hgb)
        pipe.fit(X_tr, y_tr)
        m = evaluate(pipe, make_X(test_clean, numeric, loc), y_test, lt_test)
        m["config"] = name
        m["n_train"] = int(len(train_df))
        results.append(m)
        print(f"  done: {name:<34} rent_APE={m['rent_median_ape_pct']:>5}%  sale_APE={m['sale_median_ape_pct']:>5}%")

    print("\nTraining configs (each adds one lever on top of the previous):")
    measure("C0 baseline (current recipe)", train_inliers, list(BASE_NUMERIC), {})
    measure("C1 + location prior", train_inliers, BASE_NUMERIC + [LOC_FEATURE], {})
    train_plus = pd.concat([train_inliers, no_area], ignore_index=True)
    measure("C2 + keep no-area rows", train_plus, BASE_NUMERIC + [LOC_FEATURE], {})
    measure("C3 + tuned HGB", train_plus, BASE_NUMERIC + [LOC_FEATURE], TUNED)

    # ---- comparison table -----------------------------------------------------
    print("\n===== RESULTS (all on the same clean test fold) =====")
    print(f"  {'config':<34}{'n_train':>9}{'r2_log':>9}{'rent_APE%':>11}{'sale_APE%':>11}")
    for m in results:
        print(
            f"  {m['config']:<34}{m['n_train']:>9}{m['r2_log']:>9}"
            f"{m['rent_median_ape_pct']:>11}{m['sale_median_ape_pct']:>11}"
        )

    c0, cN = results[0], results[-1]
    print("\n  Net change vs C0 baseline (lower APE = better):")
    for key in ("rent_median_ape_pct", "sale_median_ape_pct"):
        print(f"    {key:<24}{c0[key]:>7}  ->{cN[key]:>7}   ({cN[key] - c0[key]:+.1f} pts)")
    print(
        "\n  Reference: BEFORE the bedrooms backfill the baseline was "
        "rent_APE=34.7%, sale_APE=38.6%."
    )
    print("\nAnalysis only - DB and served price_model.joblib were not modified.")


if __name__ == "__main__":
    run()
