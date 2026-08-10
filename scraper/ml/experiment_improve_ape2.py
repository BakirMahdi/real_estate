"""Experiment round 2: modeling-side levers to push median APE below the floor.

Builds on round 1's finding (bedrooms backfill + a location price/m2 prior).
Every config here keeps those and is graded on the SAME clean test fold, so the
numbers are comparable to experiment_improve_ape.py's C1. No-area rows and
hyperparameter tuning are intentionally excluded (they didn't help in round 1).

Configs
-------
  B  baseline            predict log(price), squared loss  (== round-1 C1)
  P  price-per-m2 target  predict log(price/area); reconstruct price = ppm2 * area
  A  absolute-error loss  predict log(price) but optimise |error| (matches the
                          median-APE metric directly instead of a squared proxy)
  PA price/m2 + abs-error the two above combined
  S  separate models      one model for rent, one for sale (no shared listing_type)

Analysis only - does not touch the DB or the served price_model.joblib.

    docker exec realestate-backend python -m scraper.ml.experiment_improve_ape2
"""

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

from .prepare_training_data import compute_outlier_bounds
from .experiment_improve_ape import (
    BASE_NUMERIC,
    LOC_FEATURE,
    apply_fence,
    build_location_prior,
    load_base,
    make_pipeline,
    make_X,
)

NUMERIC = BASE_NUMERIC + [LOC_FEATURE]


def ape_metrics(pred_price, actual_price, listing_types) -> dict:
    pred_price = np.asarray(pred_price, dtype=float)
    actual_price = np.asarray(actual_price, dtype=float)
    m = {"r2_log": round(float(r2_score(np.log(actual_price), np.log(pred_price))), 4)}
    for lt in sorted(pd.unique(listing_types)):
        mask = (np.asarray(listing_types) == lt)
        ape = np.abs(pred_price[mask] - actual_price[mask]) / actual_price[mask]
        m[f"{lt}_median_ape_pct"] = round(float(np.median(ape)) * 100, 1)
    return m


def run() -> None:
    base = load_base()
    with_area = base[base["area"].notna() & (base["area"] > 0)].reset_index(drop=True)

    train_wa, test_wa = train_test_split(with_area, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_wa)
    train = apply_fence(train_wa, bounds)
    test = apply_fence(test_wa, bounds)
    loc = build_location_prior(train)

    X_tr, X_te = make_X(train, NUMERIC, loc), make_X(test, NUMERIC, loc)
    area_tr, area_te = train["area"].to_numpy(), test["area"].to_numpy()
    price_tr, price_te = train["price"].to_numpy(), test["price"].to_numpy()
    lt_te = test["listing_type"]

    print(f"Train {len(train):,}  |  clean test fold {len(test):,}\n")
    results = []

    def record(name, pred_price):
        m = ape_metrics(pred_price, price_te, lt_te)
        m["config"] = name
        results.append(m)
        print(f"  done: {name:<26} rent_APE={m['rent_median_ape_pct']:>5}%  sale_APE={m['sale_median_ape_pct']:>5}%  r2={m['r2_log']}")

    # Production-schema frames (current ALL_FEATURES == BASE_NUMERIC, no loc prior),
    # to check whether the abs-error win survives without the experimental feature.
    Xp_tr, Xp_te = make_X(train, BASE_NUMERIC, loc), make_X(test, BASE_NUMERIC, loc)

    # B - baseline: log(price), squared loss
    p = make_pipeline(NUMERIC).fit(X_tr, np.log(price_tr))
    record("B baseline (log price)", np.exp(p.predict(X_te)))

    # A0 - abs-error loss on the PRODUCTION feature set only (no location prior),
    # i.e. exactly what a one-line loss change to train_price_model.py would give.
    p = make_pipeline(BASE_NUMERIC, loss="absolute_error").fit(Xp_tr, np.log(price_tr))
    record("A0 abs-error, prod features", np.exp(p.predict(Xp_te)))

    # P - target is log(price / area); reconstruct price = ppm2 * area
    p = make_pipeline(NUMERIC).fit(X_tr, np.log(price_tr / area_tr))
    record("P price-per-m2 target", np.exp(p.predict(X_te)) * area_te)

    # A - log(price) with absolute-error loss
    p = make_pipeline(NUMERIC, loss="absolute_error").fit(X_tr, np.log(price_tr))
    record("A absolute-error loss", np.exp(p.predict(X_te)))

    # PA - price/m2 target AND absolute-error loss
    p = make_pipeline(NUMERIC, loss="absolute_error").fit(X_tr, np.log(price_tr / area_tr))
    record("PA price/m2 + abs-error", np.exp(p.predict(X_te)) * area_te)

    # S - separate rent and sale models (log price, squared loss)
    pred = np.empty(len(test), dtype=float)
    for lt in ("rent", "sale"):
        tr_mask = (train["listing_type"] == lt).to_numpy()
        te_mask = (test["listing_type"] == lt).to_numpy()
        sub = make_pipeline(NUMERIC).fit(X_tr[tr_mask], np.log(price_tr[tr_mask]))
        pred[te_mask] = np.exp(sub.predict(X_te[te_mask]))
    record("S separate rent/sale", pred)

    print("\n===== RESULTS (same clean test fold, lower APE = better) =====")
    print(f"  {'config':<26}{'r2_log':>9}{'rent_APE%':>11}{'sale_APE%':>11}")
    for m in results:
        print(f"  {m['config']:<26}{m['r2_log']:>9}{m['rent_median_ape_pct']:>11}{m['sale_median_ape_pct']:>11}")

    b = results[0]
    print("\n  Best per metric:")
    for key in ("rent_median_ape_pct", "sale_median_ape_pct"):
        best = min(results, key=lambda m: m[key])
        print(f"    {key:<24} best = {best[key]}%  ({best['config']})   vs baseline {b[key]}%")
    print("\nAnalysis only - DB and served price_model.joblib were not modified.")


if __name__ == "__main__":
    run()
