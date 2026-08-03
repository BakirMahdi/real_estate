"""Serve price estimates and investment scores from the trained model.

The joblib artifact produced by train_price_model.py is loaded lazily on
first request and cached for the process lifetime (retrain + restart to
pick up a new model).
"""

import os
import threading

import joblib
import numpy as np
import pandas as pd

from .features import ALL_FEATURES, to_feature_frame
from .prepare_training_data import MIN_SALE_PRICE
from .train_price_model import predict_log

MODEL_DIR = os.getenv("MODEL_DIR", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "price_model.joblib")

# A property priced this far under the model estimate scores 100 (over → 0).
# 30% roughly matches the spread of negotiation margins + model error on the
# test set; beyond that the "deal" is more likely a data problem than a steal.
FULL_SCORE_GAP = 0.30

_lock = threading.Lock()
_artifact = None


class ModelNotTrained(Exception):
    """Raised when no trained model artifact exists yet."""


class ModelSchemaMismatch(Exception):
    """Raised when the loaded artifact was trained on a different feature set.

    The pipeline's ColumnTransformer addresses columns positionally (see
    features.py), so a code change to CATEGORICAL_FEATURES/NUMERIC_FEATURES
    since the artifact was trained wouldn't error out - it would silently
    feed columns into the wrong slots and produce a confidently wrong
    prediction. Caught by the /estimate route (see M2) and degraded to a 503
    like any other estimation failure, rather than serving a bad number.
    """


def _load_artifact():
    global _artifact
    if _artifact is None:
        with _lock:
            if _artifact is None:
                if not os.path.exists(MODEL_PATH):
                    raise ModelNotTrained(
                        f"No model artifact at {MODEL_PATH}; run "
                        "`python -m scraper.ml.train_price_model` first."
                    )
                artifact = joblib.load(MODEL_PATH)
                if artifact.get("features") != ALL_FEATURES:
                    raise ModelSchemaMismatch(
                        f"Model at {MODEL_PATH} was trained on {artifact.get('features')!r}, "
                        f"but the code now expects {ALL_FEATURES!r}. Retrain with "
                        "`python -m scraper.ml.train_price_model`."
                    )
                # MODEL_DIR is a host volume, so an artifact predating the
                # per-segment layout (a single "pipeline" on log(price))
                # survives a rebuild and would otherwise KeyError deep in
                # estimate_price. Same feature list, different structure —
                # so this is checked separately from the schema guard above.
                if "models" not in artifact:
                    raise ModelSchemaMismatch(
                        f"Model at {MODEL_PATH} predates the per-segment model layout. "
                        "Retrain with `python -m scraper.ml.train_price_model`."
                    )
                _artifact = artifact
    return _artifact


def reload_artifact():
    """Drop the cached model so the next estimate reloads the latest artifact.

    Called after an automatic retrain (see main.py) so the API serves the new
    model immediately, without a backend restart.
    """
    global _artifact
    with _lock:
        _artifact = None


def estimate_price(property_row: dict) -> float:
    """Theoretical market price (TND) for one property row from the DB.

    The artifact holds one model per (listing type, surface known?) — see
    train_price_model's docstring. Routing here must match the routing used
    to fit them, so this mirrors train_price_model.segment_of/usable_area
    rather than re-deciding what counts as a usable area.
    """
    artifact = _load_artifact()
    listing_type = "sale" if property_row.get("listing_type") == "sale" else "rent"
    variants = artifact["models"].get(listing_type)
    if variants is None:
        raise ModelNotTrained(
            f"Model at {MODEL_PATH} has no {listing_type} model; retrain with "
            "`python -m scraper.ml.train_price_model`."
        )

    area = pd.to_numeric(property_row.get("area"), errors="coerce")
    has_area = bool(np.isfinite(area) and area > 0)
    model = variants["with_area" if has_area else "no_area"]

    X = to_feature_frame([property_row])
    estimated = float(np.exp(predict_log(model, X)[0]))
    if model["target"] == "log_price_per_m2":
        estimated *= float(area)
    return estimated


def investment_score(asking_price, estimated_price: float, listing_type: str):
    """0-100 score of how good a deal the asking price is vs. the estimate.

    50 = priced at the model's estimate; 100 = asking >= 30% below estimate;
    0 = asking >= 30% above. None when the score would be meaningless: rent
    listings (buying decision only) or placeholder asking prices.
    """
    if listing_type != "sale":
        return None
    if asking_price is None or asking_price <= MIN_SALE_PRICE:
        return None
    gap = (estimated_price - asking_price) / estimated_price
    return int(round(50 + 50 * max(-1.0, min(1.0, gap / FULL_SCORE_GAP))))


def estimate_property(property_row: dict) -> dict:
    """Full estimate payload for the API: price, score, and model metadata."""
    artifact = _load_artifact()
    estimated = estimate_price(property_row)
    score = investment_score(
        property_row.get("price"), estimated, property_row.get("listing_type")
    )
    return {
        "estimated_price": round(estimated),
        "investment_score": score,
        "model_trained_at": artifact["trained_at"],
        "model_metrics": artifact["metrics"],
    }
