"""End-to-end pipeline: listings -> metrics, time adjustment, summaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import synth
from .metrics import ALL, BAND_LABELS, month_label, monthly_metrics
from .summary import summarize
from .timeadj import WINDOW_MONTHS, time_adjustment_series

FIRST_MONTH = "2021-01"
LAST_MONTH = "2025-12"
ADJ_COLUMNS = ["market", "band", "month", "method", "n", "annual", "lo", "hi"]


@dataclass
class Result:
    listings: pd.DataFrame
    metrics: pd.DataFrame
    adjustment: pd.DataFrame
    summaries: list[dict]
    first: str = FIRST_MONTH
    last: str = LAST_MONTH
    synthetic: bool = True


def truth_table(first: str = FIRST_MONTH, last: str = LAST_MONTH) -> pd.DataFrame:
    """Planted trailing-12-month annual change per market and month (synthetic truth).

    Sales close about one month after contract, so the window ending at month e covers
    contract months e-12 .. e-1. Truth = exp(12 * mean planted monthly log growth) - 1.
    """
    rows = []
    months = [str(p) for p in pd.period_range(first, last, freq="M")]
    for spec in synth.MARKETS:
        for i, m in enumerate(months):
            g = synth.planted_log_growth(spec, range(i - WINDOW_MONTHS, i))
            rows.append({"market": spec.name, "month": m, "truth": float(np.expm1(12 * g.mean()))})
    return pd.DataFrame(rows)


def data_months(listings: pd.DataFrame) -> tuple[str, str]:
    """First and last month with a closed sale."""
    closed = listings["close_date"].dropna()
    if closed.empty:
        raise ValueError("no closed sales in the data")
    return month_label(closed.min()), month_label(closed.max())


def analyze(
    listings: pd.DataFrame,
    first: str | None = None,
    last: str | None = None,
    synthetic: bool = False,
) -> Result:
    """Metrics, trailing-12-month time adjustment and summaries for any listings frame."""
    if first is None or last is None:
        d_first, d_last = data_months(listings)
        first, last = first or d_first, last or d_last
    metrics = monthly_metrics(listings, first, last)
    first_adj = str(pd.Period(first, freq="M") + WINDOW_MONTHS - 1)
    if pd.Period(first_adj, freq="M") > pd.Period(last, freq="M"):
        adj = pd.DataFrame(columns=ADJ_COLUMNS)  # under 12 months of history
    else:
        adj = time_adjustment_series(listings, first_adj, last)
    months = sorted(adj["month"].unique())
    summaries = [
        summarize(metrics, adj, m, b, mo)
        for m in listings["market"].unique()
        for b in [ALL, *BAND_LABELS]
        for mo in months
    ]
    return Result(listings, metrics, adj, summaries, first, last, synthetic)


def run(seed: int = 42) -> Result:
    return analyze(synth.generate(seed=seed), FIRST_MONTH, LAST_MONTH, synthetic=True)
