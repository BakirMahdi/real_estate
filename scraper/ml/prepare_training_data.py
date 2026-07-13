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
"""

from ..db import get_conn

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
    a placeholder/non-positive price or area). No group statistics are
    involved, so this is safe to apply before any train/test split.

    Returns a new frame; `df` is not mutated.
    """
    df = df.dropna(subset=["price", "area", "governorate"]).copy()
    df = df[df["area"] > 0]

    is_sale = df["listing_type"] == "sale"
    df = df[
        (is_sale & (df["price"] > MIN_SALE_PRICE))
        | (~is_sale & (df["price"] > MIN_RENT_PRICE))
    ]
    return df.reset_index(drop=True)


def compute_outlier_bounds(
    df: pd.DataFrame, iqr_multiplier: float = 1.5, min_group_size: int = MIN_OUTLIER_GROUP_SIZE
) -> pd.DataFrame:
    """Per (listing_type, property_type) Tukey fence on log(price/area).

    Call this on the training split only: computing the fence from a dataset
    that includes rows which will later be evaluated on (the test split)
    leaks those rows' own values into the threshold that decides whether
    they count as outliers. Groups smaller than min_group_size get an
    unbounded (-inf, inf) fence - i.e. no filtering - since a handful of
    rows can't give a trustworthy quantile.

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
    too_small = bounds["n"] < min_group_size
    bounds.loc[too_small, "lower"] = -np.inf
    bounds.loc[too_small, "upper"] = np.inf
    return bounds[["lower", "upper"]]


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
    bounds = compute_outlier_bounds(df, iqr_multiplier)
    return apply_outlier_bounds(df, bounds)


def prepare_training_data() -> pd.DataFrame:
    return clean_for_training(load_raw_properties())


if __name__ == "__main__":
    data = prepare_training_data()
    print(f"{len(data)} rows loaded, columns: {list(data.columns)}")
    print(data.groupby(["listing_type", "property_type"]).size())
