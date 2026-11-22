"""End-to-end pipeline: synthetic listings -> metrics, time adjustment, summaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import synth
from .metrics import ALL, BAND_LABELS, monthly_metrics
from .summary import summarize
from .timeadj import WINDOW_MONTHS, time_adjustment_series

FIRST_MONTH = "2021-01"
LAST_MONTH = "2025-12"


@dataclass
class Result:
    listings: pd.DataFrame
    metrics: pd.DataFrame
    adjustment: pd.DataFrame
    summaries: list[dict]


def truth_table(first: str = FIRST_MONTH, last: str = LAST_MONTH) -> pd.DataFrame:
    """Planted trailing-12-month annual change per market and month (synthetic truth).

    Sales close about one month after contract, so the window ending at month e covers
    contract months e-12 .. e-1. Truth = exp(12 * mean planted monthly log growth) - 1.
    """
    rows = []
    months = [str(p) for p in pd.period_range(first, last, freq="M")]
    for spec in synth.MARKETS:
        for i, m in enumerate(months):
            k = i  # month index, 0 = first month of the series (2021-01)
            g = synth.planted_log_growth(spec, range(k - WINDOW_MONTHS, k))
            rows.append({"market": spec.name, "month": m, "truth": float(np.expm1(12 * g.mean()))})
    return pd.DataFrame(rows)


def run(seed: int = 42) -> Result:
    listings = synth.generate(seed=seed)
    metrics = monthly_metrics(listings, FIRST_MONTH, LAST_MONTH)
    first_adj = str(pd.Period(FIRST_MONTH, freq="M") + WINDOW_MONTHS - 1)
    adj = time_adjustment_series(listings, first_adj, LAST_MONTH)
    summaries = [
        summarize(metrics, adj, m, b, mo)
        for m in listings["market"].unique()
        for b in [ALL, *BAND_LABELS]
        for mo in sorted(adj["month"].unique())
    ]
    return Result(listings, metrics, adj, summaries)
