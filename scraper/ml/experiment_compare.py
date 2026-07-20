"""Definitive before/after comparison of the APE-lowering work, as an ablation.

Earlier experiments were run on different data snapshots (before vs after each
backfill), so their numbers aren't strictly comparable. This script trains every
stage on the SAME data and grades them on the SAME clean test fold, adding one
lever at a time, so each stage's contribution is isolated cleanly:

  M0  original recipe   - squared loss, and WITHOUT the bedrooms/amenities
                          features (those columns were ~83-88% null before the
                          backfills, so the original model had no usable signal
                          from them) => proxy for where we started.
  M1  + bedrooms        - add the bedrooms feature (now backfilled to ~40%).
  M2  + amenities       - add garage/furnished/terrace/pool (now backfilled).
  M3  + abs-error loss  - switch HGB to absolute_error  => the full recommended
                          model. This is the only remaining not-yet-shipped change.

Analysis only - does not touch the DB or the served price_model.joblib.

    docker exec realestate-backend python -m scraper.ml.experiment_compare
"""

import numpy as np
from sklearn.model_selection import train_test_split

from .prepare_training_data import compute_outlier_bounds
from .train_price_model import evaluate
from .experiment_improve_ape import BASE_NUMERIC, apply_fence, load_base, make_X, make_pipeline


def run() -> None:
    base = load_base()
    with_area = base[base["area"].notna() & (base["area"] > 0)].reset_index(drop=True)

    train_wa, test_wa = train_test_split(with_area, test_size=0.2, random_state=42)
    bounds = compute_outlier_bounds(train_wa)
    train = apply_fence(train_wa, bounds)
    test = apply_fence(test_wa, bounds)

    y_tr, y_te, lt_te = np.log(train["price"]), np.log(test["price"]), test["listing_type"]
    print(f"Train {len(train):,}  |  clean test fold {len(test):,}  (identical for every stage)\n")

    stages = [
        ("M0 original (no bedrooms/amenities)", ["area"], {}),
        ("M1 + bedrooms backfill", ["area", "bedrooms"], {}),
        ("M2 + amenities backfill", BASE_NUMERIC, {}),
        ("M3 + absolute-error loss  [recommended]", BASE_NUMERIC, {"loss": "absolute_error"}),
    ]

    results = []
    for name, numeric, hgb in stages:
        pipe = make_pipeline(numeric, **hgb).fit(make_X(train, numeric), y_tr)
        m = evaluate(pipe, make_X(test, numeric), y_te, lt_te)
        m["config"] = name
        results.append(m)
        print(f"  trained: {name}")

    print("\n===== APE COMPARISON (same clean test fold, lower APE = better) =====")
    print(f"  {'stage':<42}{'r2_log':>8}{'rent_APE%':>11}{'sale_APE%':>11}")
    prev = None
    for m in results:
        rent, sale = m["rent_median_ape_pct"], m["sale_median_ape_pct"]
        drent = f"({rent - prev[0]:+.1f})" if prev else ""
        dsale = f"({sale - prev[1]:+.1f})" if prev else ""
        print(f"  {m['config']:<42}{m['r2_log']:>8}{rent:>8}{drent:>7}{sale:>8}{dsale:>7}")
        prev = (rent, sale)

    m0, m3 = results[0], results[-1]
    print("\n  Net change, original -> full recommended model:")
    for key, label in (("rent_median_ape_pct", "rent APE"), ("sale_median_ape_pct", "sale APE")):
        print(f"    {label:<10}{m0[key]:>7}%  ->{m3[key]:>7}%   ({m3[key] - m0[key]:+.1f} pts)")
    print("\nNote: M0-M2 are the deployed recipe (squared loss); only M3 (abs-error)")
    print("is not yet shipped to production train_price_model.py.")


if __name__ == "__main__":
    run()
