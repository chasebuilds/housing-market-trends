"""Monthly market metrics by market and price band.

Definitions (all by calendar month):
- closed: sales with close_date in the month. Price, price per sq ft, sale-to-list
  ratio and days on market are taken from those closed sales.
- days on market: pending_date minus list_date (listing to contract), median.
- sale-to-list ratio: median of sale_price / list_price.
- active: listed on or before month end and not yet under contract or withdrawn.
- pending: under contract at month end and not yet closed.
- absorption rate: closed / active at month end (share of inventory sold per month).
- months of inventory: active at month end / closed in the month.
Closed sales are banded by sale price, active and pending listings by list price.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BAND_EDGES = [0, 150_000, 250_000, 400_000, np.inf]
BAND_LABELS = ["Under $150k", "$150k-$250k", "$250k-$400k", "$400k+"]
ALL = "All prices"

METRIC_COLUMNS = [
    "closed",
    "median_price",
    "mean_price",
    "median_ppsf",
    "sale_to_list",
    "median_dom",
    "active",
    "pending",
    "absorption_rate",
    "months_of_inventory",
]


def band_of(price: pd.Series) -> pd.Series:
    """Price band label for each price (left-closed: 150,000 is in '$150k-$250k')."""
    return pd.cut(price, bins=BAND_EDGES, labels=BAND_LABELS, right=False).astype("object")


def month_label(ts: pd.Timestamp) -> str:
    return f"{ts.year:04d}-{ts.month:02d}"


def months_between(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def _cell(
    d: pd.DataFrame,
    month: str,
    band: str | None,
) -> dict[str, float | int | None]:
    p = pd.Period(month, freq="M")
    start, end = p.start_time, p.end_time.normalize()
    sold = d[(d["close_date"] >= start) & (d["close_date"] <= end)]
    if band is not None:
        sold = sold[band_of(sold["sale_price"]) == band]
    n = len(sold)

    listed = d["list_date"] <= end
    off_pend = d["pending_date"].isna() | (d["pending_date"] > end)
    off_wd = d["withdrawn_date"].isna() | (d["withdrawn_date"] > end)
    act = d[listed & off_pend & off_wd]
    pend = d[(d["pending_date"] <= end) & (d["close_date"].isna() | (d["close_date"] > end))]
    if band is not None:
        act = act[band_of(act["list_price"]) == band]
        pend = pend[band_of(pend["list_price"]) == band]
    n_act, n_pend = len(act), len(pend)

    def stat(f: str, s: pd.Series) -> float | None:
        return None if n == 0 else float(getattr(s, f)())

    out: dict[str, float | int | None] = {
        "closed": n,
        "median_price": stat("median", sold["sale_price"]),
        "mean_price": stat("mean", sold["sale_price"]),
        "median_ppsf": stat("median", sold["sale_price"] / sold["sqft"]),
        "sale_to_list": stat("median", sold["sale_price"] / sold["list_price"]),
        "median_dom": stat("median", (sold["pending_date"] - sold["list_date"]).dt.days),
        "active": n_act,
        "pending": n_pend,
        "absorption_rate": (n / n_act) if n_act else None,
        "months_of_inventory": (n_act / n) if n else None,
    }
    return out


def monthly_metrics(listings: pd.DataFrame, first: str, last: str) -> pd.DataFrame:
    """Metrics for every market, price band and 'All prices', for months first..last."""
    rows = []
    for market, d in listings.groupby("market", sort=False):
        for month in months_between(first, last):
            for band in [None, *BAND_LABELS]:
                rows.append(
                    {
                        "market": market,
                        "band": ALL if band is None else band,
                        "month": month,
                        **_cell(d, month, band),
                    }
                )
    return pd.DataFrame(rows)
