import pandas as pd
import pytest

from housing_market_trends.summary import DISCLAIMER, classify, summarize, supply_read


@pytest.mark.parametrize(
    "annual,lo,hi,want",
    [
        (0.05, 0.02, 0.08, "increasing"),
        (0.05, -0.01, 0.11, "stable"),  # band includes zero
        (0.02, 0.01, 0.03, "stable"),  # significant but under 3% a year
        (-0.05, -0.08, -0.02, "declining"),
        (-0.05, -0.09, 0.01, "stable"),
        (0.03, 0.001, 0.06, "increasing"),  # 3% is the threshold, inclusive
        (0.0, -0.02, 0.02, "stable"),
    ],
)
def test_classify(annual, lo, hi, want):
    assert classify(annual, lo, hi) == want


@pytest.mark.parametrize(
    "moi,want",
    [
        (None, "unknown"),
        (3.9, "seller's market"),
        (4.0, "balanced"),
        (6.0, "balanced"),
        (6.1, "buyer's market"),
    ],
)
def test_supply_read(moi, want):
    assert supply_read(moi) == want


def frames():
    months = [str(p) for p in pd.period_range("2024-01", "2025-03", freq="M")]
    metrics = pd.DataFrame(
        {
            "market": "A",
            "band": "All prices",
            "month": months,
            "closed": 10,
            "median_price": [200_000.0] * 12 + [210_000.0] * 3,
            "median_dom": [40.0] * 12 + [30.0] * 3,
            "sale_to_list": 0.98,
            "active": 30,
        }
    )
    adj = pd.DataFrame(
        [
            ("A", "All prices", "2025-03", "hedonic", 120, 0.06, 0.02, 0.10),
            ("A", "All prices", "2025-03", "paired", 30, 0.05, 0.03, 0.07),
        ],
        columns=["market", "band", "month", "method", "n", "annual", "lo", "hi"],
    )
    return metrics, adj


def test_summary_increasing_with_evidence():
    metrics, adj = frames()
    s = summarize(metrics, adj, "A", "All prices", "2025-03")
    assert s["condition"] == "increasing"
    assert "rising" in s["headline"] and "+6.0%" in s["headline"]
    text = " ".join(s["evidence"])
    assert "120 sales" in text and "30 pairs" in text
    assert "210,000 vs 200,000" in text and "+5.0%" in text  # 3-month median vs year earlier
    assert "days on market 30 vs 40" in text
    assert s["months_of_inventory_3mo"] == pytest.approx(3.0)  # 30 active / 10 closed
    assert s["supply"] == "seller's market"
    assert s["disclaimer"] == DISCLAIMER and "USPAP" in DISCLAIMER


def test_summary_insufficient_data():
    metrics, adj = frames()
    s = summarize(metrics, adj.iloc[0:0], "A", "All prices", "2025-03")
    assert s["condition"] == "insufficient data"


def test_summary_stable_headline_does_not_claim_a_trend():
    metrics, adj = frames()
    adj.loc[0, ["annual", "lo", "hi"]] = [0.01, -0.03, 0.05]
    s = summarize(metrics, adj, "A", "All prices", "2025-03")
    assert s["condition"] == "stable" and "no clear price direction" in s["headline"]


def test_summary_flags_method_disagreement():
    metrics, adj = frames()
    adj.loc[1, ["annual", "lo", "hi"]] = [-0.02, -0.04, 0.0]
    s = summarize(metrics, adj, "A", "All prices", "2025-03")
    assert any("disagree" in e for e in s["evidence"])
