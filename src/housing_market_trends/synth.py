"""Seeded synthetic MLS-style listing history with planted price trends.

Every market has a known annual appreciation path (the "planted truth").
Sale prices follow a hedonic model plus the planted index, so an estimator
can be scored against the truth. All markets and listings are invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

LEAD_MONTHS = 6  # pending months generated before the first reported month
TAIL_MONTHS = 6  # pending months generated after the as-of date (listings still active)
BETA_SQFT = 0.85
AGE_EFFECT = -0.003  # log points per year of age
BED_EFFECT = 0.02  # log points per bedroom above 3
SALE_NOISE = 0.06  # sd of log sale price around the model value
QUALITY_SD = 0.12  # persistent per-property quality (same property, same quality)
RESALE_SHARE = 0.22
WITHDRAWN_SHARE = 0.15  # share of all listings that never sell
ASOF_YEAR_REF = 2025


@dataclass(frozen=True)
class MarketSpec:
    name: str
    base_price: float  # model value of a 1,700 sq ft, 3 bed, 2025-built home at index 0
    pendings_per_month: int
    # (start_month_inclusive, end_month_exclusive, annual price change)
    phases: tuple[tuple[int, int, float], ...]
    story: str = field(default="")


MARKETS: tuple[MarketSpec, ...] = (
    MarketSpec("Maple Ridge", 235_000, 55, ((0, 60, 0.08),), "steady +8% a year"),
    MarketSpec("Stonebrook", 165_000, 45, ((0, 60, 0.0),), "flat, 0% a year"),
    MarketSpec(
        "Pine Hollow",
        300_000,
        60,
        ((0, 30, 0.10), (30, 60, -0.06)),
        "boom at +10% for 30 months, then -6% a year",
    ),
    MarketSpec("Lakeshore Bend", 420_000, 40, ((0, 60, -0.05),), "steady -5% a year"),
)


def annual_rate(spec: MarketSpec, k: int) -> float:
    """Planted annual price change in force during month index k (may be <0 or >=months)."""
    for lo, hi, r in spec.phases:
        if lo <= k < hi:
            return r
    return spec.phases[0][2] if k < spec.phases[0][0] else spec.phases[-1][2]


def planted_log_growth(spec: MarketSpec, ks: range | np.ndarray) -> np.ndarray:
    """Planted monthly log price growth for each month index in ks."""
    return np.array([np.log1p(annual_rate(spec, int(k))) / 12 for k in ks])


def _index(spec: MarketSpec, k_lo: int, k_hi: int) -> dict[int, float]:
    out: dict[int, float] = {}
    acc = 0.0
    for k in range(k_lo, k_hi + 1):
        out[k] = acc
        acc += np.log1p(annual_rate(spec, k)) / 12
    return out


def _month_start(start: str, k: int) -> pd.Timestamp:
    return pd.Timestamp(start) + pd.DateOffset(months=k)


def generate(seed: int = 42, start: str = "2021-01-01", months: int = 60) -> pd.DataFrame:
    """Return one row per listing, as of the last day of the final reported month.

    Columns: listing_id, property_id, market, list_date, pending_date, close_date,
    withdrawn_date, list_price, sale_price, sqft, beds, year_built.
    Dates after the as-of date are blanked: a listing not yet under contract has no
    pending_date, one under contract but not closed has no close_date.
    """
    rng = np.random.default_rng(seed)
    asof = _month_start(start, months) - pd.Timedelta(days=1)
    rows: list[dict] = []
    next_prop = 0

    for spec in MARKETS:
        idx = _index(spec, -LEAD_MONTHS, months + TAIL_MONTHS)
        pool: list[tuple[int, float, int, int, float, int]] = []  # prop, sqft, beds, yb, q, last_k
        n_sold_events = 0
        for k in range(-LEAD_MONTHS, months + TAIL_MONTHS):
            r = annual_rate(spec, k)
            season = 1 + 0.25 * np.sin(2 * np.pi * (((k % 12) - 3) / 12))
            n = rng.poisson(spec.pendings_per_month * season)
            dom_mean = float(np.clip(100 - 500 * r, 30, 250))
            stl_mean = float(np.clip(0.975 + 0.5 * r, 0.9, 1.05))
            m0 = _month_start(start, k)
            dim = (m0 + pd.offsets.MonthEnd(0)).day
            for _ in range(n):
                eligible = [p for p in pool if p[5] <= k - 6]
                if eligible and rng.random() < RESALE_SHARE:
                    pi = eligible[rng.integers(len(eligible))]
                    prop, sqft, beds, yb, q, _last = pi
                    pool.remove(pi)
                else:
                    prop = next_prop
                    next_prop += 1
                    sqft = float(np.clip(np.exp(rng.normal(np.log(1700), 0.28)), 600, 5000))
                    sqft = round(sqft / 10) * 10
                    beds = int(np.clip(round(1 + sqft / 650 + rng.normal(0, 0.5)), 1, 6))
                    yb = int(rng.integers(1940, 2023))
                    q = float(rng.normal(0, QUALITY_SD))
                age = ASOF_YEAR_REF - yb
                ln_v = (
                    np.log(spec.base_price)
                    + BETA_SQFT * np.log(sqft / 1700)
                    + AGE_EFFECT * (age - 3)
                    + BED_EFFECT * (beds - 3)
                    + q
                    + idx[k]
                )
                sale = float(np.exp(ln_v + rng.normal(0, SALE_NOISE)))
                stl = float(np.clip(rng.normal(stl_mean, 0.03), 0.8, 1.1))
                lst = sale / stl
                dom = max(1, int(round(rng.exponential(dom_mean))))
                pend = m0 + pd.Timedelta(days=int(rng.integers(0, dim)))
                close = pend + pd.Timedelta(days=int(rng.integers(28, 46)))
                pool.append((prop, sqft, beds, yb, q, k))
                n_sold_events += 1
                rows.append(
                    dict(
                        property_id=prop,
                        market=spec.name,
                        list_date=pend - pd.Timedelta(days=dom),
                        pending_date=pend,
                        close_date=close,
                        withdrawn_date=pd.NaT,
                        list_price=round(lst, -2),
                        sale_price=round(sale, -2),
                        sqft=sqft,
                        beds=beds,
                        year_built=yb,
                    )
                )
            # withdrawn listings: never sell, sit for a while, then come off the market
            nw = rng.poisson(n * WITHDRAWN_SHARE / (1 - WITHDRAWN_SHARE))
            for _ in range(nw):
                sqft = (
                    round(float(np.clip(np.exp(rng.normal(np.log(1700), 0.28)), 600, 5000)) / 10)
                    * 10
                )
                beds = int(np.clip(round(1 + sqft / 650 + rng.normal(0, 0.5)), 1, 6))
                yb = int(rng.integers(1940, 2023))
                ln_v = (
                    np.log(spec.base_price)
                    + BETA_SQFT * np.log(sqft / 1700)
                    + AGE_EFFECT * (ASOF_YEAR_REF - yb - 3)
                    + BED_EFFECT * (beds - 3)
                    + rng.normal(0, QUALITY_SD)
                    + idx[k]
                )
                lst = float(np.exp(ln_v + rng.normal(0.03, SALE_NOISE)))
                ld = m0 + pd.Timedelta(days=int(rng.integers(0, dim)))
                wd = ld + pd.Timedelta(days=max(7, int(round(rng.exponential(dom_mean * 2.5)))))
                rows.append(
                    dict(
                        property_id=next_prop,
                        market=spec.name,
                        list_date=ld,
                        pending_date=pd.NaT,
                        close_date=pd.NaT,
                        withdrawn_date=wd,
                        list_price=round(lst, -2),
                        sale_price=np.nan,
                        sqft=sqft,
                        beds=beds,
                        year_built=yb,
                    )
                )
                next_prop += 1

    df = pd.DataFrame(rows)
    df = df[df["list_date"] <= asof].copy()  # not listed yet as of the cut
    not_yet = df["pending_date"] > asof
    df.loc[not_yet, "pending_date"] = pd.NaT
    still_pending = not_yet | (df["close_date"] > asof)
    df.loc[still_pending, "close_date"] = pd.NaT
    df.loc[still_pending, "sale_price"] = np.nan
    df.loc[df["withdrawn_date"] > asof, "withdrawn_date"] = pd.NaT
    df = df.sort_values(["market", "list_date"], kind="stable").reset_index(drop=True)
    df.insert(0, "listing_id", [f"L{i:06d}" for i in range(len(df))])
    return df
