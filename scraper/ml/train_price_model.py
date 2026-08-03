"""Train the theoretical price-estimation model and save it as a joblib artifact.

Run inside the backend container (needs DB access):

    docker exec realestate-backend python -m scraper.ml.train_price_model

Four gradient-boosted regressors are trained and stored together, keyed by
listing type and by whether the surface is known:

  (rent|sale, with_area)  target log(price / m2), prediction x area
  (rent|sale, no_area)    target log(price), area excluded from the features

*Why per-m2*: price is very close to `area x unit_price`, and area spans five
orders of magnitude (a 60 m2 studio to a 690,000 m2 farm). A tree predicting
log(price) has to rebuild that multiplication out of piecewise-constant
splits and cannot extrapolate past the areas it saw; predicting the unit
price instead hands it the exact multiplier and leaves the model to learn
only the part that is actually hard.

*Why a no-area model*: 35% of live listings have no usable surface at all,
and a per-m2 model simply cannot score them. The fallback is fit with the
area column removed, on every row — including the ~5,200 that genuinely have
no surface, which `basic_filters(require_area=False)` now keeps. Training it
only on area-having rows (with the column hidden) made it a model that had
never seen the kind of listing it serves; including them cut its median APE
from 36% to 26% on rent and 39% to 32% on sale.

*Why the listing text*: the hand-written land_*/bldg_* flags only cover
attributes someone thought to enumerate. TF-IDF over the prose (digits
stripped, so the model can't read the asking price back out — see
features.clean_listing_text) was the largest single model gain: sale 31% ->
28%, land 43% -> 40%.

*Why split rent from sale*: one model with listing_type as a feature has to
spend its first splits separating two price regimes three orders of
magnitude apart, and shares leaf structure between them; separate models let
each fit its own regime.

The artifact lands in MODEL_DIR (a docker volume, so it survives container
rebuilds) together with its evaluation metrics.
"""

import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

from .features import (
    ALL_FEATURES,
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    TEXT_FEATURE,
    to_feature_frame,
)
from .prepare_training_data import (
    apply_outlier_bounds,
    apply_price_bounds,
    basic_filters,
    compute_outlier_bounds,
    compute_price_bounds,
    drop_duplicate_listings,
    load_raw_properties,
    repair_price_magnitude,
)

MODEL_DIR = os.getenv("MODEL_DIR", "models")
MODEL_PATH = os.path.join(MODEL_DIR, "price_model.joblib")

# Feature list for the fallback model. Only `area` is removed, so the
# categorical block (and therefore the positional indices the pipeline
# addresses) is identical to the primary model's.
NO_AREA_FEATURES = [f for f in ALL_FEATURES if f != "area"]

# A segment with fewer rows than this can't support its own model; it is left
# out of the artifact rather than shipping one fit on a handful of rows.
MIN_SEGMENT_ROWS = 50

LISTING_SEGMENTS = ("rent", "sale")


# TF-IDF over the price-free listing prose, reduced to a handful of dense
# components the tree can split on. Word 1-2 grams at 3,000 terms / 24
# components measured best; more terms, more components, char n-grams and a
# word+char union were all tried and were no better (some worse).
TFIDF_PARAMS = dict(max_features=3000, ngram_range=(1, 2), min_df=5, sublinear_tf=True)
TEXT_COMPONENTS = 24

# Each variant averages this many regressors (identical except for their seed)
# in log space. Worth ~0.3 pts of sale APE, but the real prize is stability:
# it roughly halves the run-to-run spread (sale +/-1.2 -> +/-0.6), which
# matters because this retrains unattended after every scrape.
ENSEMBLE_SIZE = 3


def _text_branch(texts):
    """TF-IDF -> SVD for the `text` column.

    The vectorizer is fit once up front purely to size the SVD: TruncatedSVD
    requires n_components < vocabulary size, and a small segment with sparse
    descriptions could otherwise have fewer terms than components and raise.
    """
    probe = TfidfVectorizer(**TFIDF_PARAMS)
    probe.fit(texts)
    n_components = int(min(TEXT_COMPONENTS, max(1, len(probe.vocabulary_) - 1)))
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(**TFIDF_PARAMS)),
            ("svd", TruncatedSVD(n_components=n_components, random_state=42)),
        ]
    )


def _area_monotonic_constraint(transformer, features, n_columns):
    """Constrain the per-m2 target to never rise with area, or None if `area`
    isn't a feature (the fallback model).

    Left unconstrained, the model learns the bulk discount correctly up to
    ~5,000 m2 (912 -> 165 TND/m2) and then *reverses*, climbing back to ~978
    TND/m2 by 240,000 m2 — there are too few parcels that large for the top
    histogram bin to mean anything, so it fits noise. Multiplied back by a
    six-figure area that produced estimates like 794M TND for a 3.5M TND farm,
    which in turn hands investment_score a "100 = excellent deal" on the very
    listings it should be flagging. A bulk discount (unit price non-increasing
    in size) is a safe economic prior and fixes it at the source: mean sale
    APE 108% -> 85%, worst-case 24,400% -> 8,000%, at a cost of ~0.2 pts of
    median APE, which is inside re-split noise.
    """
    if "area" not in features:
        return None
    # The text block's width depends on the fitted vocabulary, so the numeric
    # columns' positions can't be assumed — read them off the fitted
    # transformer instead of counting features by hand.
    numeric = [f for f in features if f in NUMERIC_FEATURES]
    constraint = np.zeros(n_columns, dtype=int)
    remainder_start = transformer.output_indices_["remainder"].start
    constraint[remainder_start + numeric.index("area")] = -1
    return constraint


def build_transformer(features) -> ColumnTransformer:
    """Categoricals -> ordinal codes, `text` -> TF-IDF/SVD, numerics untouched."""
    steps = [
        (
            "cat",
            OrdinalEncoder(
                handle_unknown="use_encoded_value",
                unknown_value=-1,
                encoded_missing_value=-1,
            ),
            CATEGORICAL_FEATURES,
        )
    ]
    if TEXT_FEATURE in features:
        # A bare string (not a list) so the vectorizer receives a 1-D Series.
        steps.append(("txt", "passthrough", TEXT_FEATURE))
    return ColumnTransformer(steps, remainder="passthrough")


def build_regressor(**overrides) -> HistGradientBoostingRegressor:
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
    params = dict(
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
    params.update(overrides)
    return HistGradientBoostingRegressor(**params)


def fit_variant(X, y, features, seed_offset=0) -> dict:
    """Fit one model variant: shared transformer + an ensemble of regressors.

    The transformer is fit once and reused, so the ensemble members differ
    only in the boosting seed — that is what makes averaging them a variance
    reduction rather than a different model each time.
    """
    Xs = X[features]
    transformer = build_transformer(features)
    if TEXT_FEATURE in features:
        transformer.set_params(txt=_text_branch(Xs[TEXT_FEATURE]))
    encoded = transformer.fit_transform(Xs)
    constraint = _area_monotonic_constraint(transformer, features, encoded.shape[1])
    regressors = [
        build_regressor(random_state=42 + i * 101 + seed_offset, monotonic_cst=constraint).fit(
            encoded, y
        )
        for i in range(ENSEMBLE_SIZE)
    ]
    return {"transformer": transformer, "regressors": regressors, "features": features}


def predict_log(variant, X) -> np.ndarray:
    """Mean log-space prediction of a variant's ensemble."""
    encoded = variant["transformer"].transform(X[variant["features"]])
    return np.mean([r.predict(encoded) for r in variant["regressors"]], axis=0)


def build_pipeline(features) -> Pipeline:
    """A single unfitted transformer+regressor Pipeline over `features`.

    The production models are fit through fit_variant (shared transformer, an
    ensemble of regressors, monotonic constraint sized from the fitted text
    block), so nothing here uses this. It exists for the ablation scripts in
    this package, which each fit one plain pipeline to isolate one lever.
    """
    return Pipeline(
        [("encode", build_transformer(features)), ("regress", build_regressor())]
    )


def segment_of(df) -> np.ndarray:
    """"sale" vs "rent" per row, matching basic_filters' own convention that
    anything not explicitly "sale" is a rental."""
    return np.where(np.asarray(df["listing_type"]) == "sale", "sale", "rent")


def usable_area(df):
    """(area values, mask of rows whose area can be divided/multiplied by).

    A non-finite or non-positive area is unusable for a per-m2 model, so those
    rows are routed to the no-area fallback instead.
    """
    area = pd.to_numeric(df["area"], errors="coerce").to_numpy(dtype="float64")
    return area, np.isfinite(area) & (area > 0)


def fit_models(train_df) -> dict:
    """Fit the four models. Returns {listing_type: {variant: {...}}}.

    The two variants train on deliberately different populations:

    - `with_area` on rows that have a surface, since it needs one to form its
      price-per-m2 target at all;
    - `no_area` on *every* row, area-having and area-less alike. It used to be
      fit on area-having rows with the column hidden, which meant it had
      trained on none of the listings it actually serves; giving it the ~5,200
      genuinely area-less rows cut its median APE from 36% to 26% on rent and
      39% to 32% on sale, measured on the population it really scores.
    """
    X = to_feature_frame(train_df)
    area, has_area = usable_area(train_df)
    price = pd.to_numeric(train_df[TARGET], errors="coerce").to_numpy(dtype="float64")
    segments = segment_of(train_df)

    models = {}
    for listing_type in LISTING_SEGMENTS:
        in_segment = segments == listing_type
        area_rows = np.flatnonzero(in_segment & has_area)
        all_rows = np.flatnonzero(in_segment)
        if len(area_rows) < MIN_SEGMENT_ROWS:
            continue
        variants = {}
        variants["with_area"] = fit_variant(
            X.iloc[area_rows], np.log(price[area_rows] / area[area_rows]), ALL_FEATURES
        )
        variants["with_area"].update(target="log_price_per_m2", n_train=len(area_rows))
        variants["no_area"] = fit_variant(
            X.iloc[all_rows], np.log(price[all_rows]), NO_AREA_FEATURES
        )
        variants["no_area"].update(target="log_price", n_train=len(all_rows))
        models[listing_type] = variants
    return models


def predict_prices(models, df, force_variant=None) -> np.ndarray:
    """Predicted price in TND per row; NaN where no model covers the row.

    Routes each row to the per-m2 model when its area is usable and to the
    fallback otherwise. `force_variant` pins every row to one variant, which
    is what lets evaluate() measure the fallback path on rows that do have an
    area (the only rows with a known ground truth).
    """
    X = to_feature_frame(df)
    area, has_area = usable_area(df)
    segments = segment_of(df)

    prices = np.full(len(X), np.nan)
    for listing_type, variants in models.items():
        in_segment = segments == listing_type
        if force_variant is not None:
            routes = [(force_variant, in_segment)]
        else:
            routes = [
                ("with_area", in_segment & has_area),
                ("no_area", in_segment & ~has_area),
            ]
        for variant, mask in routes:
            rows = np.flatnonzero(mask)
            if not len(rows):
                continue
            model = variants[variant]
            predicted_log = predict_log(model, X.iloc[rows])
            scale = area[rows] if model["target"] == "log_price_per_m2" else 1.0
            prices[rows] = np.exp(predicted_log) * scale
    return prices


def _segment_metrics(prefix, predicted, actual, metrics) -> None:
    abs_err = np.abs(predicted - actual)
    ape = abs_err / actual
    metrics[f"{prefix}_mae_tnd"] = round(float(mean_absolute_error(actual, predicted)), 1)
    metrics[f"{prefix}_median_ape_pct"] = round(float(np.median(ape)) * 100, 1)
    # Plain-language "accuracy" for a price model: a typical miss in dinars
    # and how often an estimate lands close to the real price. Easier to
    # read than APE / R^2, but derived from the same test predictions.
    metrics[f"{prefix}_median_error_tnd"] = round(float(np.median(abs_err)))
    metrics[f"{prefix}_within_20pct"] = round(float(np.mean(ape <= 0.20)) * 100, 1)
    metrics[f"{prefix}_within_30pct"] = round(float(np.mean(ape <= 0.30)) * 100, 1)


def evaluate(models, test_df) -> dict:
    """Metrics split by the path that actually serves each row.

    The headline `{rent,sale}_*` keys cover listings that state a surface —
    the with_area path, ~65% of the catalogue. The `*_no_area_*` keys cover
    listings that genuinely have none, scored by the fallback.

    That population split matters: an earlier version measured the fallback
    on area-having rows with the column hidden, which flattered it badly
    (28%/42% reported against 36%/39% on the real population). A listing with
    no stated surface is not the same kind of listing as one that has a
    surface we chose to ignore — it is typically a thinner, less professional
    ad — so only rows that are really missing an area can measure that path.
    """
    actual = pd.to_numeric(test_df[TARGET], errors="coerce").to_numpy(dtype="float64")
    segments = segment_of(test_df)
    _, has_area = usable_area(test_df)
    predicted = predict_prices(models, test_df)

    scored = np.isfinite(predicted) & np.isfinite(actual) & (actual > 0)
    metrics = {
        "r2_log": round(float(r2_score(np.log(actual[scored]), np.log(predicted[scored]))), 4),
        "n_test": int((scored & has_area).sum()),
        "n_test_no_area": int((scored & ~has_area).sum()),
    }
    # Absolute errors are only meaningful per listing type (rents are in
    # hundreds of TND, sales in hundreds of thousands).
    for listing_type in LISTING_SEGMENTS:
        in_segment = scored & (segments == listing_type)
        headline = in_segment & has_area
        if headline.any():
            _segment_metrics(listing_type, predicted[headline], actual[headline], metrics)
        fallback = in_segment & ~has_area
        if fallback.any():
            _segment_metrics(
                f"{listing_type}_no_area", predicted[fallback], actual[fallback], metrics
            )
    return metrics


def evaluate_single_model(pipeline, X_test, y_test_log, listing_types) -> dict:
    """Metrics for one pipeline predicting log(price) directly.

    The production models are per-segment and predict log(price/m2), so
    evaluate() takes the whole artifact instead. The ablation scripts in this
    package each fit a single log(price) pipeline of their own to isolate one
    lever, and this is the evaluator that shape needs.
    """
    predicted = np.exp(pipeline.predict(X_test))
    actual = np.exp(np.asarray(y_test_log))
    metrics = {
        "r2_log": round(r2_score(y_test_log, pipeline.predict(X_test)), 4),
        "n_test": int(len(y_test_log)),
    }
    listing_types = pd.Series(listing_types).to_numpy()
    for listing_type in sorted(set(listing_types)):
        mask = listing_types == listing_type
        _segment_metrics(listing_type, predicted[mask], actual[mask], metrics)
    return metrics


def format_metrics_summary(metrics: dict) -> str:
    """Plain-language recap of the stored metrics for the terminal.

    The raw metrics dict keeps the technical keys (R^2, APE, MAE) that the
    API and the experiment scripts read; this only reshapes them into
    something a non-specialist can skim after a training run.
    """
    labels = {"rent": "RENT (location)", "sale": "SALE (vente)"}
    lines = [
        f"How good is the model?  (checked against {metrics['n_test']:,} real "
        "listings it was never trained on,",
        f"plus {metrics.get('n_test_no_area', 0):,} more that state no surface, "
        "scored separately below)",
    ]
    for listing_type in LISTING_SEGMENTS:
        if f"{listing_type}_median_ape_pct" not in metrics:
            continue
        lines += [
            "",
            f"  {labels.get(listing_type, listing_type.upper())}",
            f"    Typical estimate is off by {metrics[f'{listing_type}_median_ape_pct']:.0f}%"
            f"  (about {metrics[f'{listing_type}_median_error_tnd']:,.0f} TND)",
            f"    {metrics[f'{listing_type}_within_20pct']:.0f}% of estimates land within "
            "20% of the real price",
            f"    {metrics[f'{listing_type}_within_30pct']:.0f}% land within 30%",
        ]
        fallback_ape = metrics.get(f"{listing_type}_no_area_median_ape_pct")
        if fallback_ape is not None:
            within = metrics.get(f"{listing_type}_no_area_within_20pct", 0)
            lines.append(
                f"    listings with no stated surface: off by {fallback_ape:.0f}%"
                f" ({within:.0f}% within 20%)"
            )

    stability = []
    for listing_type in LISTING_SEGMENTS:
        mean = metrics.get(f"{listing_type}_median_ape_pct_cv_mean")
        std = metrics.get(f"{listing_type}_median_ape_pct_cv_std")
        if mean is not None:
            stability.append(f"{listing_type} {mean:.0f}% (+/-{std:.0f})")
    if stability:
        lines += [
            "",
            "  Across 5 different random train/test splits, the typical miss was:",
            f"    {'   '.join(stability)}",
            "  (the +/- is re-split noise - a change smaller than it isn't a real change)",
        ]
    return "\n".join(lines)


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

    Rows with no surface can't be judged by a price-per-m2 fence, so they get
    an absolute-price fence instead (compute_price_bounds). Both fences are
    derived from the *area-having* training rows, whose prices the sharper
    fence has already vouched for.
    """
    train_df, test_df = train_test_split(filtered, test_size=0.2, random_state=seed)
    train_has_area = train_df["area"].notna().to_numpy()
    test_has_area = test_df["area"].notna().to_numpy()

    bounds = compute_outlier_bounds(train_df[train_has_area])
    train_area = apply_outlier_bounds(
        repair_price_magnitude(train_df[train_has_area], bounds), bounds
    )
    test_area = apply_outlier_bounds(test_df[test_has_area], bounds)

    price_bounds = compute_price_bounds(train_df[train_has_area])
    train_rest = apply_price_bounds(train_df[~train_has_area], price_bounds)
    test_rest = apply_price_bounds(test_df[~test_has_area], price_bounds)

    return (
        pd.concat([train_area, train_rest], ignore_index=True),
        pd.concat([test_area, test_rest], ignore_index=True),
    )


def _fit_eval(filtered, seed):
    train_df, test_df = _clean_split(filtered, seed)
    models = fit_models(train_df)
    return models, train_df, evaluate(models, test_df)


# Extra random splits evaluated alongside the main seed-42 one, so the stored
# metrics carry a stability estimate: a single 80/20 split moves median APE by
# a couple of points on re-split noise alone, and without the spread a real
# regression is indistinguishable from an unlucky split.
STABILITY_SEEDS = (0, 1, 2, 3)


def train() -> dict:
    # Dedup before splitting: reposts/cross-posts of the same property landing
    # on both sides of the split would let the model score on rows it saw.
    # require_area=False keeps the area-less rows the fallback model trains on
    # and is graded against; _clean_split fences the two populations apart.
    filtered = drop_duplicate_listings(
        basic_filters(load_raw_properties(), require_area=False)
    )

    models, train_df, metrics = _fit_eval(filtered, 42)

    spread = {listing_type: [] for listing_type in LISTING_SEGMENTS}
    for seed in STABILITY_SEEDS:
        _, _, seed_metrics = _fit_eval(filtered, seed)
        for listing_type in spread:
            spread[listing_type].append(seed_metrics.get(f"{listing_type}_median_ape_pct"))
    for listing_type, values in spread.items():
        key = f"{listing_type}_median_ape_pct"
        if key not in metrics:
            continue
        values = [v for v in values if v is not None] + [metrics[key]]
        metrics[f"{key}_cv_mean"] = round(float(np.mean(values)), 1)
        metrics[f"{key}_cv_std"] = round(float(np.std(values)), 1)

    # The shipped models are exactly these 80%-trained pipelines (no refit on
    # the full dataset), so `metrics` is a direct measurement of the served
    # models' accuracy on data they never saw, not a proxy for differently-fit
    # production models.
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(
        {
            "models": models,
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
    print(f"Model saved to {MODEL_PATH}\n")
    print(format_metrics_summary(metrics))
