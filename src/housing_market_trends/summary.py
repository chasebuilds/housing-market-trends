"""Plain-English market-conditions summary: increasing, stable or declining, with evidence."""

from __future__ import annotations

import math

import pandas as pd

MIN_RATE = 0.03  # annual change needed, with a band that excludes zero, to call a direction
SELLER_MOI = 4.0
BUYER_MOI = 6.0
DISCLAIMER = (
    "Analysis and education only. This is not an appraisal. A USPAP-compliant appraisal "
    "requires a licensed or certified appraiser."
)


def classify(annual: float, lo: float, hi: float) -> str:
    """increasing / declining only when the point rate is at least 3% a year and the 95% band
    excludes zero; otherwise stable."""
    if annual >= MIN_RATE and lo > 0:
        return "increasing"
    if annual <= -MIN_RATE and hi < 0:
        return "declining"
    return "stable"


def supply_read(moi: float | None) -> str:
    if moi is None:
        return "unknown"
    if moi < SELLER_MOI:
        return "seller's market"
    if moi > BUYER_MOI:
        return "buyer's market"
    return "balanced"


def _w3(cell: pd.DataFrame, month: str, col: str) -> float | None:
    """Closed-sales-weighted average of a monthly metric over the 3 months ending at month."""
    p = pd.Period(month, freq="M")
    win = cell[cell["month"].isin([str(p - i) for i in range(3)])].dropna(subset=[col])
    w = win["closed"].sum()
    return None if w == 0 else float((win[col] * win["closed"]).sum() / w)


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def summarize(
    metrics: pd.DataFrame,
    adj: pd.DataFrame,
    market: str,
    band: str,
    month: str,
) -> dict:
    cell = metrics[(metrics["market"] == market) & (metrics["band"] == band)]
    a = adj[(adj["market"] == market) & (adj["band"] == band) & (adj["month"] == month)]
    hed = a[a["method"] == "hedonic"]
    pai = a[a["method"] == "paired"]

    p = pd.Period(month, freq="M")
    prior = str(p - 12)
    cur_row = cell[cell["month"] == month]
    closed3 = sum(int(cell.loc[cell["month"] == str(p - i), "closed"].sum()) for i in range(3))
    active = int(cur_row["active"].iloc[0]) if len(cur_row) else 0
    moi = (active / (closed3 / 3)) if closed3 else None

    evidence: list[str] = []
    condition = "insufficient data"
    headline = f"Not enough closed sales in {market} ({band}) to estimate a trend for {month}."
    rate = None
    if len(hed):
        h = hed.iloc[0]
        condition = classify(h["annual"], h["lo"], h["hi"])
        rate = float(h["annual"])
        evidence.append(
            f"Time regression on {int(h['n'])} sales in the last 12 months: {_pct(h['annual'])} a "
            f"year (95% band {_pct(h['lo'])} to {_pct(h['hi'])})."
        )
    if len(pai):
        r = pai.iloc[0]
        evidence.append(
            f"Paired resales ({int(r['n'])} pairs): {_pct(r['annual'])} a year (95% band "
            f"{_pct(r['lo'])} to {_pct(r['hi'])})."
        )
        if len(hed) and (hed.iloc[0]["annual"] > 0) != (r["annual"] > 0):
            evidence.append("The two methods disagree on direction, so treat the call as weak.")
        if not len(hed):
            condition = classify(r["annual"], r["lo"], r["hi"])
            rate = float(r["annual"])
    price_now, price_then = _w3(cell, month, "median_price"), _w3(cell, prior, "median_price")
    if price_now and price_then:
        evidence.append(
            f"Median price (3-month) {price_now:,.0f} vs {price_then:,.0f} a year earlier "
            f"({_pct(price_now / price_then - 1)}). This mixes in changes in what sold."
        )
    dom_now, dom_then = _w3(cell, month, "median_dom"), _w3(cell, prior, "median_dom")
    if dom_now is not None and dom_then is not None:
        evidence.append(f"Median days on market {dom_now:.0f} vs {dom_then:.0f} a year earlier.")
    stl = _w3(cell, month, "sale_to_list")
    if stl is not None:
        evidence.append(f"Sale-to-list ratio {stl * 100:.1f}% (3-month).")
    if moi is not None:
        evidence.append(
            f"Months of inventory {moi:.1f} ({supply_read(moi)}; under {SELLER_MOI:.0f} favors "
            f"sellers, over {BUYER_MOI:.0f} favors buyers)."
        )
    if rate is not None:
        word = {"increasing": "rising", "declining": "falling", "stable": "stable"}[condition]
        tail = "" if not math.isfinite(rate) else f" at about {_pct(rate)} a year"
        if condition == "stable":
            headline = (
                f"{market} ({band}), {month}: no clear price direction (estimate{tail[3:]}; "
                "the band is too wide or the rate too small to call a trend)."
            )
        else:
            headline = f"{market} ({band}), {month}: prices look {word}{tail}."
    return {
        "market": market,
        "band": band,
        "month": month,
        "condition": condition,
        "headline": headline,
        "evidence": evidence,
        "months_of_inventory_3mo": None if moi is None else round(moi, 2),
        "supply": supply_read(moi),
        "disclaimer": DISCLAIMER,
    }
