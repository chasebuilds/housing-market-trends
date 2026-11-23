"""Time-adjustment (market appreciation) rate with a 95% confidence band.

Two independent estimators, both reported as an annual percent change:

1. Paired resales: for properties that sold twice, regress ln(price2 / price1) on the
   months between the two closings, through the origin. Slope = monthly log change.
2. Hedonic time regression: regress ln(price) on ln(sq ft), age, bedrooms and
   months, over the sales in a trailing window. Coefficient on months = monthly log change.

Annual rate = exp(12 * slope) - 1. The band uses a t interval on the slope.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from .metrics import ALL, BAND_LABELS, band_of, months_between

DAYS_PER_MONTH = 30.4375
WINDOW_MONTHS = 12
MIN_PAIRS = 12
MIN_SALES = 40
MAX_PAIR_GAP_MONTHS = 36


@dataclass(frozen=True)
class Estimate:
    n: int
    annual: float  # fractional, 0.05 = +5% a year
    lo: float
    hi: float


def _to_estimate(slope: float, se: float, df: int, n: int) -> Estimate:
    t = float(stats.t.ppf(0.975, df))
    return Estimate(
        n=n,
        annual=float(np.expm1(12 * slope)),
        lo=float(np.expm1(12 * (slope - t * se))),
        hi=float(np.expm1(12 * (slope + t * se))),
    )


def paired_resale_rate(months_apart: np.ndarray, log_ratio: np.ndarray) -> Estimate | None:
    """Through-origin slope of log price ratio on months between sales."""
    x = np.asarray(months_apart, dtype=float)
    y = np.asarray(log_ratio, dtype=float)
    n = len(x)
    if n < MIN_PAIRS:
        return None
    sxx = float(np.sum(x * x))
    slope = float(np.sum(x * y) / sxx)
    resid = y - slope * x
    se = float(np.sqrt(np.sum(resid**2) / (n - 1) / sxx))
    return _to_estimate(slope, se, n - 1, n)


def hedonic_time_rate(sales: pd.DataFrame, end: pd.Timestamp) -> Estimate | None:
    """OLS of ln(price) on ln(sqft), age, beds and months-before-end; slope on months."""
    n = len(sales)
    if n < MIN_SALES:
        return None
    t = (sales["close_date"] - end).dt.days.to_numpy() / DAYS_PER_MONTH
    cols = [np.ones(n), np.log(sales["sqft"].to_numpy(dtype=float))]
    if sales["year_built"].notna().all():  # age and bedrooms are used only when present
        cols.append((sales["close_date"].dt.year - sales["year_built"]).to_numpy(dtype=float))
    if sales["beds"].notna().all():
        cols.append(sales["beds"].to_numpy(dtype=float))
    X = np.column_stack([*cols, t])
    y = np.log(sales["sale_price"].to_numpy(dtype=float))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    df = n - X.shape[1]
    s2 = float(resid @ resid / df)
    cov = s2 * np.linalg.inv(X.T @ X)
    return _to_estimate(float(beta[-1]), float(np.sqrt(cov[-1, -1])), df, n)


def resale_pairs(listings: pd.DataFrame) -> pd.DataFrame:
    """Consecutive closed sales of the same property: second close date, gap, log ratio, band."""
    s = listings.dropna(subset=["close_date", "sale_price"]).sort_values(
        ["property_id", "close_date"]
    )
    g = s.groupby("property_id")
    out = pd.DataFrame(
        {
            "market": s["market"],
            "close_date": s["close_date"],
            "prev_close": g["close_date"].shift(),
            "prev_price": g["sale_price"].shift(),
            "price": s["sale_price"],
        }
    ).dropna()
    out["months_apart"] = (out["close_date"] - out["prev_close"]).dt.days / DAYS_PER_MONTH
    out["log_ratio"] = np.log(out["price"] / out["prev_price"])
    out["band"] = band_of(out["prev_price"])  # band by the first sale price
    return out[(out["months_apart"] > 0) & (out["months_apart"] <= MAX_PAIR_GAP_MONTHS)]


def time_adjustment_series(listings: pd.DataFrame, first: str, last: str) -> pd.DataFrame:
    """Trailing-12-month estimates for every market, band and month, both methods."""
    sold = listings.dropna(subset=["close_date", "sale_price"]).copy()
    sold["band"] = band_of(sold["sale_price"])
    pairs = resale_pairs(listings)
    rows = []
    for market in listings["market"].unique():
        sm = sold[sold["market"] == market]
        pm = pairs[pairs["market"] == market]
        for month in months_between(first, last):
            p = pd.Period(month, freq="M")
            end = p.end_time.normalize()
            begin = (p - (WINDOW_MONTHS - 1)).start_time
            sw = sm[(sm["close_date"] >= begin) & (sm["close_date"] <= end)]
            pw = pm[(pm["close_date"] >= begin) & (pm["close_date"] <= end)]
            for band in [ALL, *BAND_LABELS]:
                s_b = sw if band == ALL else sw[sw["band"] == band]
                p_b = pw if band == ALL else pw[pw["band"] == band]
                for method, est in (
                    ("hedonic", hedonic_time_rate(s_b, end)),
                    (
                        "paired",
                        paired_resale_rate(
                            p_b["months_apart"].to_numpy(), p_b["log_ratio"].to_numpy()
                        ),
                    ),
                ):
                    if est is None:
                        continue
                    rows.append(
                        {
                            "market": market,
                            "band": band,
                            "month": month,
                            "method": method,
                            "n": est.n,
                            "annual": est.annual,
                            "lo": est.lo,
                            "hi": est.hi,
                        }
                    )
    return pd.DataFrame(
        rows, columns=["market", "band", "month", "method", "n", "annual", "lo", "hi"]
    )


def adjustment_factor(annual_rate: float, months: float) -> float:
    """Fractional change that moves a price across `months` at an annual rate.

    Compounds: (1 + annual) ** (months / 12) - 1. Negative months move a price backwards.
    """
    return float((1 + annual_rate) ** (months / 12) - 1)


def months_between_labels(sale_month: str, effective_month: str) -> int:
    """Whole months from the comparable's sale month to the effective-date month."""
    return (pd.Period(effective_month, freq="M") - pd.Period(sale_month, freq="M")).n


def adjust_price(price: float, annual: float, lo: float, hi: float, months: float) -> dict:
    """Time-adjusted price and the range implied by the rate's 95% band."""
    f, f_lo, f_hi = (adjustment_factor(r, months) for r in (annual, lo, hi))
    return {
        "months": months,
        "factor": f,
        "factor_lo": f_lo,
        "factor_hi": f_hi,
        "adjusted": price * (1 + f),
        "adjusted_lo": price * (1 + f_lo),
        "adjusted_hi": price * (1 + f_hi),
    }
