"""Benchmark: how closely do the estimators recover the planted trends?

Run: python -m housing_market_trends.benchmark  (writes BENCHMARK.md)
"""

from __future__ import annotations

import sys

import pandas as pd

from . import pipeline
from .metrics import ALL


def score(res: pipeline.Result) -> pd.DataFrame:
    truth = pipeline.truth_table()
    a = res.adjustment[res.adjustment["band"] == ALL].merge(truth, on=["market", "month"])
    a["err_pp"] = (a["annual"] - a["truth"]) * 100
    a["covered"] = (a["lo"] <= a["truth"]) & (a["truth"] <= a["hi"])
    return a


def band_table(res: pipeline.Result) -> str:
    """Hedonic accuracy inside each price band. Bands are cut on sale price, which is the
    quantity being modeled, so some bias is expected and is reported, not hidden."""
    truth = pipeline.truth_table()
    a = res.adjustment[(res.adjustment["method"] == "hedonic") & (res.adjustment["band"] != ALL)]
    a = a.merge(truth, on=["market", "month"])
    a["err_pp"] = (a["annual"] - a["truth"]) * 100
    a["covered"] = (a["lo"] <= a["truth"]) & (a["truth"] <= a["hi"])
    lines = [
        "| Band | Windows | MAE (pp) | Bias (pp) | Truth inside 95% band |",
        "|---|---|---|---|---|",
    ]
    for band, g in a.groupby("band", sort=False):
        lines.append(
            f"| {band} | {len(g)} | {g['err_pp'].abs().mean():.2f} | {g['err_pp'].mean():+.2f} | "
            f"{g['covered'].mean() * 100:.0f}% |"
        )
    return "\n".join(lines)


def table(a: pd.DataFrame) -> str:
    lines = [
        "| Market | Method | Windows | MAE (pp) | Bias (pp) | Truth inside 95% band |",
        "|---|---|---|---|---|---|",
    ]
    for (market, method), g in a.groupby(["market", "method"], sort=False):
        lines.append(
            f"| {market} | {method} | {len(g)} | {g['err_pp'].abs().mean():.2f} | "
            f"{g['err_pp'].mean():+.2f} | {g['covered'].mean() * 100:.0f}% |"
        )
    for method, g in a.groupby("method"):
        lines.append(
            f"| **All markets** | {method!s} | {len(g)} | {g['err_pp'].abs().mean():.2f} | "
            f"{g['err_pp'].mean():+.2f} | {g['covered'].mean() * 100:.0f}% |"
        )
    return "\n".join(lines)


def direction_hits(res: pipeline.Result) -> tuple[int, int]:
    """Share of market-months (All prices) where the summary label matches the planted
    direction. Planted label: increasing if truth >= +3%, declining if <= -3%, else stable."""
    truth = pipeline.truth_table().set_index(["market", "month"])["truth"]
    hit = tot = 0
    for s in res.summaries:
        if s["band"] != ALL or s["condition"] == "insufficient data":
            continue
        t = truth[(s["market"], s["month"])]
        want = "increasing" if t >= 0.03 else "declining" if t <= -0.03 else "stable"
        tot += 1
        hit += int(s["condition"] == want)
    return hit, tot


def main() -> None:
    res = pipeline.run()
    a = score(res)
    hit, tot = direction_hits(res)
    pine = a[(a["market"] == "Pine Hollow") & (a["method"] == "hedonic")].set_index("month")
    out = [
        "# Benchmark: recovering planted trends",
        "",
        "Seed 42, 4 invented markets, 60 months, "
        f"{len(res.listings):,} listings. Each window is the trailing 12 months ending at the "
        "month shown. Error = estimated annual change minus the planted annual change, in "
        "percentage points (pp). Band = 95% interval from the estimator.",
        "",
        table(a),
        "",
        f"Market-condition label matches the planted direction in {hit} of {tot} "
        f"market-months ({hit / tot * 100:.0f}%).",
        "",
        "Pine Hollow turns from +10% to -6% at month 30 (2023-07). "
        "Hedonic estimate vs planted truth, last month of each half-year around the turn:",
        "",
        "| Month | Planted | Hedonic estimate |",
        "|---|---|---|",
    ]
    for m in ["2023-06", "2023-09", "2023-12", "2024-03", "2024-06", "2024-09"]:
        r = pine.loc[m]
        out.append(f"| {m} | {r['truth'] * 100:+.1f}% | {r['annual'] * 100:+.1f}% |")
    out += [
        "",
        "",
        "Time regression inside each price band (all markets pooled). Cutting a band on "
        "sale price truncates the thing being modeled, so a bias is expected:",
        "",
        band_table(res),
        "",
        "Trailing windows lag a turn: a 12-month window still holds months from before the turn. "
        "Paired resales lag more, because a pair spans the whole gap between its two sales.",
    ]
    text = "\n".join(out) + "\n"
    open("BENCHMARK.md", "w", encoding="utf-8").write(text)
    sys.stdout.write(text)


if __name__ == "__main__":
    main()
