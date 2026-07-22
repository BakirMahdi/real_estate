"""Train the theoretical price-estimation model and save it as a joblib artifact.

Run inside the backend container (needs DB access):

    docker exec realestate-backend python -m scraper.ml.train_price_model

The model is a gradient-boosted regressor on log(price): prices span 5
orders of magnitude across rent/sale and governorates, so a log target
keeps the loss from being dominated by expensive listings and makes errors
multiplicative (a 10% miss on a 100k house counts the same as on a 1M
villa). One model covers both rent and sale, with listing_type as a
feature. The artifact lands in MODEL_DIR (a docker volume, so it survives
container rebuilds) together with its evaluation metrics.
"""

import os
from datetime import datetime, timezone

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .features import ALL_FEATURES, CATEGORICAL_FEATURES, TARGET, to_feature_frame
from .prepare_training_data import (
    apply_outlier_bounds,
    basic_filters,
    compute_outlier_bounds,
    drop_duplicate_listings,
    load_raw_properties,
    repair_price_magnitude,
)

MODEL_DIR = os.getenv("MODEL_DIR", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "price_model.joblib")


def build_pipeline() -> Pipeline:
    encode_categoricals = ColumnTransformer(
        [
            (
                "cat",
                OrdinalEncoder(
                    handle_unknown="use_encoded_value",
                    unknown_value=-1,
                    encoded_missing_value=-1,
                ),
                CATEGORICAL_FEATURES,
            )
        ],
        remainder="passthrough",
    )
    # After the transformer the categorical columns come first, so their
    # positional indices are 0..len(CATEGORICAL_FEATURES)-1.
    #
    # absolute_error (not the default squared error) because the model is
    # graded on median APE, a median-absolute metric: minimising |log-error|
    # optimises that directly, whereas squared error chases the mean and is
    # dragged around by the heavy-tailed price noise in the listings. In an
    # ablation on a fixed test fold this cut rent APE ~3 pts and sale ~2 pts
    # over squared error, helping both listing types.
    #
    # The remaining hyperparameters come from a 16-config grid (3-fold CV on
    # the training fold, 2026-07-22), confirmed across 5 random splits against
    # the sklearn defaults: rent median APE 21.3 vs 22.0 (better on 4/5
    # seeds), sale unchanged, lower variance on both. Early stopping replaces
    # the fixed default of 100 iterations, so the iteration count keeps
    # adapting as the dataset grows.
    regressor = HistGradientBoostingRegressor(
        categorical_features=list(range(len(CATEGORICAL_FEATURES))),
        loss="absolute_error",
        learning_rate=0.05,
        max_leaf_nodes=31,
        min_samples_leaf=5,
        l2_regularization=1.0,
        max_iter=1000,
        early_stopping=True,
        validation_fraction=0.15,
        n_iter_no_change=30,
        random_state=42,
    )
    return Pipeline([("encode", encode_categoricals), ("regress", regressor)])


def evaluate(pipeline, X_test, y_test_log, listing_types) -> dict:
    pred_log = pipeline.predict(X_test)
    pred = np.exp(pred_log)
    actual = np.exp(y_test_log)

    metrics = {
        "r2_log": round(r2_score(y_test_log, pred_log), 4),
        "n_test": int(len(y_test_log)),
    }
    # Absolute errors are only meaningful per listing type (rents are in
    # hundreds of TND, sales in hundreds of thousands).
    for lt in sorted(listing_types.unique()):
        mask = (listing_types == lt).to_numpy()
        ape = np.abs(pred[mask] - actual[mask]) / actual[mask]
        metrics[f"{lt}_mae_tnd"] = round(float(mean_absolute_error(actual[mask], pred[mask])), 1)
        metrics[f"{lt}_median_ape_pct"] = round(float(np.median(ape)) * 100, 1)
    return metrics


def _clean_split(filtered, seed):
    """Split, then clean each fold with statistics fit on the training fold only.

    Split before deriving the outlier fence: computing it from a dataset
    that includes rows destined for the test split would leak those rows'
    own values into the threshold that later decides whether they count as
    outliers, biasing the reported test metrics. The fence is fit on the
    training fold only, then applied to both folds unchanged.

    The x1000 unit repair is applied to the TRAINING fold only (recovers
    ~4% more rows; measured neutral on held-out APE). The test fold keeps
    only real observed prices — a repaired price is a plausible guess, and
    grading the model against guessed targets (some of them huge) skews the
    metrics, dominating the TND MAE in particular.
    """
    train_df, test_df = train_test_split(filtered, test_size=0.2, random_state=seed)
    bounds = compute_outlier_bounds(train_df)
    train_df = repair_price_magnitude(train_df, bounds)
    train_df = apply_outlier_bounds(train_df, bounds)
    test_df = apply_outlier_bounds(test_df, bounds)
    return train_df, test_df


def _fit_eval(filtered, seed):
    train_df, test_df = _clean_split(filtered, seed)
    X_train, y_train = to_feature_frame(train_df), np.log(train_df[TARGET])
    X_test, y_test = to_feature_frame(test_df), np.log(test_df[TARGET])
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)
    metrics = evaluate(pipeline, X_test, y_test, test_df["listing_type"])
    return pipeline, train_df, metrics


# Extra random splits evaluated alongside the main seed-42 one, so the stored
# metrics carry a stability estimate: a single 80/20 split moves median APE by
# a couple of points on re-split noise alone, and without the spread a real
# regression is indistinguishable from an unlucky split.
STABILITY_SEEDS = (0, 1, 2, 3)


def train() -> dict:
    # Dedup before splitting: reposts/cross-posts of the same property landing
    # on both sides of the split would let the model score on rows it saw.
    filtered = drop_duplicate_listings(basic_filters(load_raw_properties()))

    pipeline, train_df, metrics = _fit_eval(filtered, 42)

    spread = {"rent": [], "sale": []}
    for seed in STABILITY_SEEDS:
        _, _, seed_metrics = _fit_eval(filtered, seed)
        for lt in spread:
            spread[lt].append(seed_metrics.get(f"{lt}_median_ape_pct"))
    for lt, values in spread.items():
        values = [v for v in values if v is not None] + [metrics[f"{lt}_median_ape_pct"]]
        metrics[f"{lt}_median_ape_pct_cv_mean"] = round(float(np.mean(values)), 1)
        metrics[f"{lt}_median_ape_pct_cv_std"] = round(float(np.std(values)), 1)

    # The shipped model is exactly this 80%-trained pipeline (no refit on the
    # full dataset), so `metrics` is a direct measurement of the served
    # model's accuracy on data it never saw, not a proxy for a differently-fit
    # production model.
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "features": ALL_FEATURES,
            "metrics": metrics,
            "n_training_rows": int(len(train_df)),
            "trained_at": datetime.now(timezone.utc).isoformat(),
        },
        MODEL_PATH,
    )
    return metrics


if __name__ == "__main__":
    metrics = train()
    print(f"Model saved to {MODEL_PATH}")
    for key, value in metrics.items():
        print(f"  {key}: {value}")
