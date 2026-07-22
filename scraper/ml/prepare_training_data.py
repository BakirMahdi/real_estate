"""Build a cleaned training dataset for the price-estimation model.

The raw `properties` table is left untouched (it's still the source of
truth for the live site), but it isn't safe to train on directly: ~40% of
sale listings carry a placeholder price (0 or 1, "price on request"), and a
long tail of listings have obviously wrong prices (e.g. a 154m2 lot listed
at 111111114000000 - Tunisian sites mix currency between dinars and
millimes and some scrapes captured garbage). A fixed absolute price
threshold doesn't generalize across property types and governorates, so
outliers are instead filtered by price-per-m2 using a Tukey fence
(median +/- k*IQR, computed on the log of price-per-m2 to account for the
right-skew of real-estate prices) per (listing_type, property_type) group,
so the bound adapts to each group's own spread instead of a fixed cutoff.

Beyond placeholder/aberrant prices, three further data problems are handled
here (added 2026-07-22, each worth real APE on held-out data):
- rent rows priced per night/week (vacation lets) are a wrong *target* for a
  monthly-rent model, ~11% of clean rent rows - dropped in basic_filters
  via rental_period.detect_rental_period;
- reposts/cross-posts of the same property (~15% of filtered rows) leak
  across the train/test split and double-weight those properties - collapsed
  by drop_duplicate_listings;
- x1000 unit mixups (dinars vs millimes, thousands typed as units) are
  *repaired* by repair_price_magnitude when the corrected price lands back
  inside the group's fence, instead of discarding the row.
"""

from ..db import get_conn
from ..rental_period import detect_rental_period

import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "id",
    "source",
    "property_type",
    "listing_type",
    "price",
    "area",
    "governorate",
    "city",
    # address/title/description feed the derived `neighborhood` feature (see
    # ml/features.to_feature_frame); they're not model inputs themselves.
    "address",
    "title",
    "description",
    "bedrooms",
    "garage",
    "furnished",
    "terrace",
    "pool",
    "subcategory",
]

# Below this, a sale price is a placeholder ("price on request"), not a real
# minimum purchase price. Rent placeholders are just 0/1 since low-but-real
# monthly rents (e.g. 100 TND) are common.
MIN_SALE_PRICE = 1000
MIN_RENT_PRICE = 1

# A (listing_type, property_type) group with fewer rows than this doesn't have
# enough data for its own quantiles to be trustworthy (a handful of rows can
# put q1/q3 anywhere) - such groups are left unfiltered rather than risking a
# noisy/degenerate fence that keeps real outliers or drops legitimate rows.
MIN_OUTLIER_GROUP_SIZE = 20


def load_raw_properties() -> pd.DataFrame:
    """Latest scraped snapshot of each ad (dedup by source+ad_id), all columns needed for training."""
    conn = get_conn()
    try:
        query = f"""
            SELECT DISTINCT ON (source, ad_id) {", ".join(FEATURE_COLUMNS)}
            FROM properties
            ORDER BY source, ad_id, id DESC
        """
        return pd.read_sql(query, conn)
    finally:
        conn.close()


def basic_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows that can't teach the model anything (missing required fields,
    a placeholder/non-positive price or area), plus rent listings priced per
    night/week (vacation lets): the model predicts *monthly* rent, and a
    nightly price on a rent row is a wrong target, not an outlier a price
    fence can be trusted to catch. No group statistics are involved, so this
    is safe to apply before any train/test split.

    Returns a new frame; `df` is not mutated.
    """
    df = df.dropna(subset=["price", "area", "governorate"]).copy()
    df = df[df["area"] > 0]

    is_sale = df["listing_type"] == "sale"
    df = df[
        (is_sale & (df["price"] > MIN_SALE_PRICE))
        | (~is_sale & (df["price"] > MIN_RENT_PRICE))
    ]

    if {"title", "description"}.issubset(df.columns):
        is_rent = df["listing_type"] != "sale"
        short_term = pd.Series(False, index=df.index)
        short_term[is_rent] = [
            detect_rental_period(title, description) is not None
            for title, description in zip(
                df.loc[is_rent, "title"], df.loc[is_rent, "description"]
            )
        ]
        df = df[~short_term]

    return df.reset_index(drop=True)


def drop_duplicate_listings(df: pd.DataFrame) -> pd.DataFrame:
    """Drop repost/cross-post duplicates, keeping the most descriptive copy.

    The same physical property routinely appears several times: reposted on
    the same site under a fresh ad_id, or published on both Tayara and
    Mubawab. Duplicates double-weight those properties and — worse — leak
    across a train/test split (the model is graded on a row it effectively
    saw), inflating reported metrics. Rows are considered the same property
    when listing_type, property_type, governorate, bedrooms, rounded area and
    rounded price all coincide; among duplicates the row with the longest
    description wins (most text for the derived features), then the newest id.
    """
    key = ["listing_type", "property_type", "governorate", "_bedrooms", "_area", "_price"]
    tmp = df.copy()
    tmp["_bedrooms"] = tmp["bedrooms"].fillna(-1) if "bedrooms" in tmp.columns else -1
    tmp["_area"] = tmp["area"].round()
    tmp["_price"] = tmp["price"].round()
    tmp["_desc_len"] = (
        tmp["description"].fillna("").str.len() if "description" in tmp.columns else 0
    )
    tmp = tmp.sort_values(["_desc_len", "id"], ascending=False)
    keep = tmp.drop_duplicates(subset=key).index
    return df.loc[df.index.isin(keep)].reset_index(drop=True)


def compute_outlier_bounds(
    df: pd.DataFrame, iqr_multiplier: float = 1.5, min_group_size: int = MIN_OUTLIER_GROUP_SIZE
) -> pd.DataFrame:
    """Per (listing_type, property_type) Tukey fence on log(price/area).

    Call this on the training split only: computing the fence from a dataset
    that includes rows which will later be evaluated on (the test split)
    leaks those rows' own values into the threshold that decides whether
    they count as outliers. Groups smaller than min_group_size (whose own
    quantiles would be untrustworthy) fall back to the fence of their whole
    listing_type — wider than a per-type fence, but still catches the
    orders-of-magnitude garbage that an unbounded fence used to let through
    (e.g. sale/office with 9 rows).

    Returns a (listing_type, property_type)-indexed DataFrame with "lower"/
    "upper" columns, meant to be passed to apply_outlier_bounds().
    """
    tmp = df.copy()
    tmp["log_price_per_area"] = np.log(tmp["price"] / tmp["area"])
    grouped = tmp.groupby(["listing_type", "property_type"])["log_price_per_area"]
    bounds = grouped.agg(q1=lambda x: x.quantile(0.25), q3=lambda x: x.quantile(0.75), n="count")
    iqr = bounds["q3"] - bounds["q1"]
    bounds["lower"] = bounds["q1"] - iqr_multiplier * iqr
    bounds["upper"] = bounds["q3"] + iqr_multiplier * iqr

    lt_grouped = tmp.groupby("listing_type")["log_price_per_area"]
    lt_bounds = lt_grouped.agg(q1=lambda x: x.quantile(0.25), q3=lambda x: x.quantile(0.75))
    lt_iqr = lt_bounds["q3"] - lt_bounds["q1"]
    lt_bounds["lower"] = lt_bounds["q1"] - iqr_multiplier * lt_iqr
    lt_bounds["upper"] = lt_bounds["q3"] + iqr_multiplier * lt_iqr

    too_small = bounds["n"] < min_group_size
    small_lt = bounds.index.get_level_values("listing_type")[too_small]
    bounds.loc[too_small, "lower"] = lt_bounds["lower"].reindex(small_lt).to_numpy()
    bounds.loc[too_small, "upper"] = lt_bounds["upper"].reindex(small_lt).to_numpy()
    return bounds[["lower", "upper"]]


def repair_price_magnitude(df: pd.DataFrame, bounds: pd.DataFrame, factor: float = 1000.0) -> pd.DataFrame:
    """Correct x1000 price-unit mixups instead of discarding the rows.

    Tunisian listings mix dinars and millimes (1 TND = 1000 millimes), and
    some sellers type thousands-of-dinars as plain dinars. Both show up as a
    price exactly ~3 orders of magnitude outside the group's fence. When
    dividing (price too high) or multiplying (too low) by `factor` lands the
    row back inside its group's fence, the price is corrected and the row
    kept for training; rows still outside are left for apply_outlier_bounds
    to drop as before. Uses precomputed bounds (fit on the training fold), so
    it is safe to apply to both folds.

    Returns a new frame; `df` is not mutated.
    """
    tmp = df.copy()
    tmp["_log_ppm2"] = np.log(tmp["price"] / tmp["area"])
    joined = tmp.join(bounds, on=["listing_type", "property_type"])
    lower = joined["lower"].fillna(-np.inf)
    upper = joined["upper"].fillna(np.inf)
    log_factor = np.log(factor)

    too_high = (joined["_log_ppm2"] > upper) & (joined["_log_ppm2"] - log_factor).between(lower, upper)
    too_low = (joined["_log_ppm2"] < lower) & (joined["_log_ppm2"] + log_factor).between(lower, upper)

    out = df.copy()
    out.loc[too_high.to_numpy(), "price"] = out.loc[too_high.to_numpy(), "price"] / factor
    out.loc[too_low.to_numpy(), "price"] = out.loc[too_low.to_numpy(), "price"] * factor
    return out


def apply_outlier_bounds(df: pd.DataFrame, bounds: pd.DataFrame) -> pd.DataFrame:
    """Drop rows whose log(price/area) falls outside their group's precomputed
    bounds (from compute_outlier_bounds). A group with no entry in `bounds`
    (e.g. present in the test split but never seen in train) is left
    unfiltered rather than dropped outright.
    """
    tmp = df.copy()
    tmp["log_price_per_area"] = np.log(tmp["price"] / tmp["area"])
    joined = tmp.join(bounds, on=["listing_type", "property_type"])
    keep = joined["log_price_per_area"].between(
        joined["lower"].fillna(-np.inf), joined["upper"].fillna(np.inf)
    )
    return df[keep.to_numpy()].reset_index(drop=True)


def clean_for_training(df: pd.DataFrame, iqr_multiplier: float = 1.5) -> pd.DataFrame:
    """One-shot cleaning (filter + outlier removal, bounds derived from `df`
    itself) for callers that don't need a train/test split, e.g. ad-hoc data
    exploration via this module's __main__. train_price_model.py's train()
    does NOT use this - it splits first and derives outlier bounds from the
    training fold only; see compute_outlier_bounds's docstring for why.
    """
    df = basic_filters(df)
    df = drop_duplicate_listings(df)
    bounds = compute_outlier_bounds(df, iqr_multiplier)
    df = repair_price_magnitude(df, bounds)
    return apply_outlier_bounds(df, bounds)


def prepare_training_data() -> pd.DataFrame:
    return clean_for_training(load_raw_properties())


if __name__ == "__main__":
    data = prepare_training_data()
    print(f"{len(data)} rows loaded, columns: {list(data.columns)}")
    print(data.groupby(["listing_type", "property_type"]).size())
