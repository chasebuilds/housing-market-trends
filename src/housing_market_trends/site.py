"""Build the static dashboard: one HTML file with the data embedded."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from . import pipeline
from .metrics import ALL, BAND_LABELS, METRIC_COLUMNS, months_between
from .summary import DISCLAIMER

PLOTLY_URL = "https://cdn.jsdelivr.net/npm/plotly.js-basic-dist-min@2.35.2/plotly-basic.min.js"


def _clean(v: Any, digits: int) -> float | int | None:
    if v is None or (isinstance(v, float) and not np.isfinite(v)) or pd.isna(v):
        return None
    return round(float(v), digits)


def build_payload(res: pipeline.Result) -> dict:
    months = months_between(pipeline.FIRST_MONTH, pipeline.LAST_MONTH)
    markets = list(res.listings["market"].unique())
    bands = [ALL, *BAND_LABELS]
    digits = {"closed": 0, "active": 0, "pending": 0, "median_dom": 1}
    metrics: dict[str, dict[str, list]] = {}
    adj: dict[str, dict[str, dict[str, list]]] = {}
    summaries: dict[str, dict[str, dict]] = {}
    for mk in markets:
        for bd in bands:
            key = f"{mk}|{bd}"
            cell = res.metrics[(res.metrics["market"] == mk) & (res.metrics["band"] == bd)]
            cell = cell.set_index("month").reindex(months)
            metrics[key] = {
                c: [_clean(v, digits.get(c, 4)) for v in cell[c]] for c in METRIC_COLUMNS
            }
            a = res.adjustment[(res.adjustment["market"] == mk) & (res.adjustment["band"] == bd)]
            adj[key] = {}
            for method in ("hedonic", "paired"):
                g = a[a["method"] == method].set_index("month").reindex(months)
                adj[key][method] = {
                    c: [_clean(v, 4 if c != "n" else 0) for v in g[c]]
                    for c in ("n", "annual", "lo", "hi")
                }
            summaries[key] = {}
    for s in res.summaries:
        d = {k: s[k] for k in ("condition", "headline", "evidence", "supply")}
        summaries[f"{s['market']}|{s['band']}"][s["month"]] = d
    tt = pipeline.truth_table().set_index(["market", "month"])["truth"]
    truth = {mk: [_clean(tt[(mk, m)], 4) for m in months] for mk in markets}
    return {
        "months": months,
        "markets": markets,
        "bands": bands,
        "metrics": metrics,
        "adj": adj,
        "summaries": summaries,
        "truth": truth,
        "disclaimer": DISCLAIMER,
        "listings": int(len(res.listings)),
    }


def build(out_dir: Path, res: pipeline.Result | None = None) -> Path:
    res = res or pipeline.run()
    template = (
        resources.files("housing_market_trends").joinpath("dashboard.html").read_text("utf-8")
    )
    html = template.replace("__PLOTLY_URL__", PLOTLY_URL).replace(
        "__DATA__", json.dumps(build_payload(res), separators=(",", ":"))
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path
