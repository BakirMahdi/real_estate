"""Serve price estimates and investment scores from the trained model.

The joblib artifact produced by train_price_model.py is loaded lazily on
first request and cached for the process lifetime (retrain + restart to
pick up a new model).
"""

import os
import threading

import joblib
import numpy as np

from .features import to_feature_frame
from .prepare_training_data import MIN_SALE_PRICE

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
                _artifact = joblib.load(MODEL_PATH)
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
    """Theoretical market price (TND) for one property row from the DB."""
    artifact = _load_artifact()
    X = to_feature_frame([property_row])
    pred_log = artifact["pipeline"].predict(X)[0]
    return float(np.exp(pred_log))


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
