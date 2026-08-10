"""Experiment: does correcting price outliers by estimation beat dropping them?

Runs the whole train -> correct -> retrain loop and prints the results of each
stage, so you can watch the effect of outlier correction rather than only
seeing a final number.

    docker exec realestate-backend python -m scraper.ml.train_with_outlier_correction

Stages
------
1. **Baseline** - the production recipe: fit the Tukey fence on the training
   fold, DROP the rows outside it, train, and evaluate on the clean test fold.
2. **Correct**  - instead of throwing the flagged training-fold outliers away,
   ask the baseline model to predict a plausible price for each and overwrite
   the aberrant price with that estimate (self-training / pseudo-labelling).
3. **Retrain**  - train a fresh model on the clean rows + the corrected rows and
   evaluate it on the *same* clean test fold, then print the delta vs stage 1.

Why the test fold is identical and clean in both stages: the corrected prices
are the model's own guesses, not ground truth, so they must never enter the
test set - otherwise we'd be grading the model against its own predictions. The
held-out rows keep their real prices (outliers dropped) in both runs, which
makes stage 1 vs stage 3 an apples-to-apples comparison of generalisation.

This is an analysis only: it does NOT touch the database and does NOT overwrite
the served models/price_model.joblib artifact.
"""

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from .features import ALL_FEATURES, TARGET, to_feature_frame
from .prepare_training_data import (
    basic_filters,
    compute_outlier_bounds,
    load_raw_properties,
)
from .train_price_model import build_pipeline, evaluate_single_model as evaluate


def split_inliers_outliers(df: pd.DataFrame, bounds: pd.DataFrame):
    """Partition `df` into (inliers, outliers) using precomputed group bounds.

    Mirrors apply_outlier_bounds' keep-mask but also hands back the rows that
    fall outside the fence, which is what we want to correct rather than drop.
    A row whose group has no fence entry is treated as an inlier.
    """
    tmp = df.copy()
    tmp["log_ppm2"] = np.log(tmp["price"] / tmp["area"])
    joined = tmp.join(bounds, on=["listing_type", "property_type"])
    keep = joined["log_ppm2"].between(
        joined["lower"].fillna(-np.inf), joined["upper"].fillna(np.inf)
    )
    keep = keep.to_numpy()
    inliers = df[keep].reset_index(drop=True)
    outliers = df[~keep].reset_index(drop=True)
    return inliers, outliers


def print_metrics(title: str, metrics: dict) -> None:
    print(f"\n===== {title} =====")
    for key, value in metrics.items():
        print(f"  {key}: {value}")


def print_comparison(baseline: dict, corrected: dict) -> None:
    """Side-by-side of every metric the two runs share.

    Lower is better for MAE / median-APE; higher is better for r2. The arrow
    points to whichever run wins each metric so improvements are obvious.
    """
    print("\n===== STEP 3 vs STEP 1 (same clean test fold) =====")
    print(f"  {'metric':<26}{'baseline':>14}{'corrected':>14}{'change':>14}  better")
    for key in baseline:
        if key not in corrected:
            continue
        b, c = baseline[key], corrected[key]
        if not isinstance(b, (int, float)) or key == "n_test":
            print(f"  {key:<26}{b:>14}{c:>14}")
            continue
        delta = c - b
        higher_is_better = key.startswith("r2")
        improved = (delta > 0) if higher_is_better else (delta < 0)
        same = abs(delta) < 1e-9
        better = "=" if same else ("corrected" if improved else "baseline")
        print(f"  {key:<26}{b:>14}{c:>14}{delta:>+14.4f}  {better}")


def run() -> None:
    filtered = basic_filters(load_raw_properties())
    print(f"Loaded {len(filtered):,} rows after basic filters (missing/placeholder prices removed).")

    # Same split + fence-on-train-only protocol as production, so the baseline
    # numbers here match what train_price_model.py would report.
    train_df, test_df = train_test_split(filtered, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_df)

    train_inliers, train_outliers = split_inliers_outliers(train_df, bounds)
    test_inliers, _ = split_inliers_outliers(test_df, bounds)  # test outliers are always dropped

    X_test = to_feature_frame(test_inliers)
    y_test = np.log(test_inliers[TARGET])

    # ---- STEP 1: baseline, outliers dropped -----------------------------------
    baseline = build_pipeline(ALL_FEATURES)
    baseline.fit(to_feature_frame(train_inliers), np.log(train_inliers[TARGET]))
    baseline_metrics = evaluate(baseline, X_test, y_test, test_inliers["listing_type"])

    print(
        f"\nTrain fold: {len(train_df):,} rows -> {len(train_inliers):,} inliers kept, "
        f"{len(train_outliers):,} flagged as outliers.  "
        f"Clean test fold: {len(test_inliers):,} rows."
    )
    print_metrics("STEP 1: baseline (outliers DROPPED)", baseline_metrics)

    # ---- STEP 2: correct the flagged outliers by estimation -------------------
    if train_outliers.empty:
        print("\nNo outliers flagged in the training fold; nothing to correct. Stopping.")
        return

    corrected = train_outliers.copy()
    corrected["price_before"] = corrected["price"].to_numpy()
    corrected["price"] = np.exp(baseline.predict(to_feature_frame(corrected)))

    print(f"\n===== STEP 2: correcting {len(corrected):,} outliers by estimation =====")
    summary = (
        corrected.assign(ratio=corrected["price"] / corrected["price_before"])
        .groupby("listing_type")
        .agg(
            n=("price", "size"),
            median_before=("price_before", "median"),
            median_after=("price", "median"),
            median_ratio=("ratio", "median"),
        )
        .round(2)
    )
    print("  Per-listing-type effect of the correction (price before vs estimated):")
    print(summary.to_string())

    sample = corrected.sort_values("area").head(8)[
        ["source", "listing_type", "property_type", "governorate", "area", "price_before", "price"]
    ].copy()
    sample["price"] = sample["price"].round(0)
    print("\n  Sample corrected rows (smallest areas first - often the worst aberrations):")
    with pd.option_context("display.float_format", lambda v: f"{v:,.0f}", "display.width", 160):
        print(sample.to_string(index=False))

    # ---- STEP 3: retrain on inliers + corrected outliers ----------------------
    augmented = pd.concat([train_inliers, corrected[train_inliers.columns]], ignore_index=True)
    retrained = build_pipeline(ALL_FEATURES)
    retrained.fit(to_feature_frame(augmented), np.log(augmented[TARGET]))
    corrected_metrics = evaluate(retrained, X_test, y_test, test_inliers["listing_type"])

    print(
        f"\nRetrain fold: {len(train_inliers):,} inliers + {len(corrected):,} corrected "
        f"= {len(augmented):,} rows.  Evaluated on the same {len(test_inliers):,} clean test rows."
    )
    print_metrics("STEP 3: retrained (outliers CORRECTED, not dropped)", corrected_metrics)
    print_comparison(baseline_metrics, corrected_metrics)

    print(
        "\nNote: this was an experiment - the DB and the served "
        "models/price_model.joblib artifact were not modified."
    )


if __name__ == "__main__":
    run()
