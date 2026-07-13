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
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .features import ALL_FEATURES, CATEGORICAL_FEATURES, TARGET, to_feature_frame
from .prepare_training_data import basic_filters, compute_outlier_bounds, apply_outlier_bounds, load_raw_properties

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
    regressor = HistGradientBoostingRegressor(
        categorical_features=list(range(len(CATEGORICAL_FEATURES))),
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


def train() -> dict:
    filtered = basic_filters(load_raw_properties())

    # Split before deriving the outlier fence: computing it from a dataset
    # that includes rows destined for the test split would leak those rows'
    # own values into the threshold that later decides whether they count as
    # outliers, biasing the reported test metrics. The fence is fit on the
    # training fold only, then applied to both folds unchanged.
    train_df, test_df = train_test_split(filtered, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_df)
    train_df = apply_outlier_bounds(train_df, bounds)
    test_df = apply_outlier_bounds(test_df, bounds)

    X_train, y_train = to_feature_frame(train_df), np.log(train_df[TARGET])
    X_test, y_test = to_feature_frame(test_df), np.log(test_df[TARGET])

    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)
    metrics = evaluate(pipeline, X_test, y_test, test_df["listing_type"])

    # Note: `metrics` describes this 80%-trained holdout model, not the
    # 100%-refit pipeline saved below - standard practice (you can't evaluate
    # a model on data it was also fit on), but it means the numbers served by
    # /estimate are a slightly conservative proxy for the shipped model's
    # actual accuracy, not a direct measurement of it.
    #
    # Refit on all cleaned rows before saving: the held-out split exists only
    # to measure generalization, and the shipped model shouldn't waste 20% of
    # the data. There's no held-out set left to leak into at this point, so
    # the outlier fence is recomputed from the full (train+test) cleaned data
    # for this final fit.
    all_df = pd.concat([train_df, test_df], ignore_index=True)
    X_all, y_all = to_feature_frame(all_df), np.log(all_df[TARGET])
    pipeline = build_pipeline()
    pipeline.fit(X_all, y_all)

    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipeline,
            "features": ALL_FEATURES,
            "metrics": metrics,
            "n_training_rows": int(len(all_df)),
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
