import numpy as np
import pandas as pd
import pytest
from scipy import stats

import housing_market_trends.timeadj as ta
from housing_market_trends.timeadj import (
    DAYS_PER_MONTH,
    hedonic_time_rate,
    paired_resale_rate,
    resale_pairs,
)


def test_paired_exact_growth_has_zero_band():
    x = np.arange(6, 18, dtype=float)  # 12 pairs
    est = paired_resale_rate(x, 0.01 * x)  # exactly 1% log growth a month
    assert est is not None and est.n == 12
    assert est.annual == pytest.approx(np.expm1(0.12))
    assert est.hi - est.lo == pytest.approx(0, abs=1e-9)


def test_paired_too_few_pairs_returns_none():
    assert paired_resale_rate(np.array([1.0, 2.0]), np.array([0.01, 0.02])) is None


def test_paired_slope_and_error_by_hand(monkeypatch):
    # x = 1,2,3  y = .01,.03,.02: sum(xy)=.13, sum(x^2)=14 -> slope .13/14
    # residuals .000714, .011429, -.007857, SSE .00019286, se = sqrt(SSE/2/14) = .002624
    monkeypatch.setattr(ta, "MIN_PAIRS", 3)
    est = ta.paired_resale_rate(np.array([1.0, 2.0, 3.0]), np.array([0.01, 0.03, 0.02]))
    assert est is not None
    slope, se = 0.13 / 14, 0.002624
    t = stats.t.ppf(0.975, 2)
    assert est.annual == pytest.approx(np.expm1(12 * slope), rel=1e-9)
    assert est.lo == pytest.approx(np.expm1(12 * (slope - t * se)), rel=2e-3)
    assert est.hi == pytest.approx(np.expm1(12 * (slope + t * se)), rel=2e-3)


def make_sales(n: int, monthly_log: float) -> tuple[pd.DataFrame, pd.Timestamp]:
    rng = np.random.default_rng(1)
    end = pd.Timestamp("2025-06-30")
    days = rng.integers(0, 360, n)
    close = end - pd.to_timedelta(days, unit="D")
    sqft = rng.uniform(900, 3000, n)
    yb = rng.integers(1950, 2020, n)
    beds = rng.integers(2, 6, n)
    age = close.year - yb
    t = -days / DAYS_PER_MONTH
    ln_p = 11 + 0.8 * np.log(sqft) - 0.002 * age + 0.02 * beds + monthly_log * t
    df = pd.DataFrame(
        {
            "close_date": close,
            "sqft": sqft,
            "year_built": yb,
            "beds": beds,
            "sale_price": np.exp(ln_p),
        }
    )
    return df, end


def test_hedonic_recovers_noise_free_trend():
    df, end = make_sales(80, 0.005)  # +0.5% a month in log terms
    est = hedonic_time_rate(df, end)
    assert est is not None and est.n == 80
    assert est.annual == pytest.approx(np.expm1(0.06), abs=1e-9)


def test_hedonic_needs_enough_sales():
    df, end = make_sales(39, 0.005)
    assert hedonic_time_rate(df, end) is None


def test_hedonic_flat_market_band_contains_zero_with_noise():
    df, end = make_sales(200, 0.0)
    df["sale_price"] *= np.exp(np.random.default_rng(2).normal(0, 0.06, len(df)))
    est = hedonic_time_rate(df, end)
    assert est is not None and est.lo < 0 < est.hi


def test_resale_pairs_by_hand():
    d = pd.DataFrame(
        {
            "property_id": [1, 1, 1, 2, 2],
            "market": "A",
            "close_date": pd.to_datetime(
                ["2021-01-01", "2022-01-01", "2026-06-01", "2021-03-01", "2021-03-01"]
            ),
            "sale_price": [100_000.0, 110_000.0, 150_000.0, 200_000.0, 210_000.0],
        }
    )
    p = resale_pairs(d)
    # property 1: first pair 365 days, 10% up. The 2022 -> 2026 pair is 4.4 years, dropped (>36 mo).
    # property 2: zero-day gap dropped.
    assert len(p) == 1
    r = p.iloc[0]
    assert r["months_apart"] == pytest.approx(365 / DAYS_PER_MONTH)
    assert r["log_ratio"] == pytest.approx(np.log(1.1))
    assert r["band"] == "Under $150k"
