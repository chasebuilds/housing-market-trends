import math

import pandas as pd
import pytest

from housing_market_trends.metrics import (
    ALL,
    BAND_LABELS,
    band_of,
    month_label,
    monthly_metrics,
    months_between,
)


def march(tiny, band=ALL):
    m = monthly_metrics(tiny, "2025-03", "2025-03")
    return m[m["band"] == band].iloc[0]


def test_closed_count(tiny):
    assert march(tiny)["closed"] == 3  # L1, L2, L3 close in March; L5 closes in April


def test_median_and_mean_price(tiny):
    r = march(tiny)
    assert r["median_price"] == 247_000  # sorted 190k, 247k, 300k
    assert r["mean_price"] == pytest.approx((190_000 + 247_000 + 300_000) / 3)


def test_price_per_sqft(tiny):
    # 190, 200, 190 per sq ft
    assert march(tiny)["median_ppsf"] == pytest.approx(190.0)


def test_sale_to_list(tiny):
    # 190/200 = 0.95, 300/300 = 1.0, 247/260 = 0.95
    assert march(tiny)["sale_to_list"] == pytest.approx(0.95)


def test_days_on_market(tiny):
    # Jan 10 -> Feb 20 = 41, Feb 1 -> Mar 1 = 28, Feb 10 -> Mar 5 = 23
    assert march(tiny)["median_dom"] == 28


def test_active_pending(tiny):
    r = march(tiny)
    assert r["active"] == 1  # only L4; L6 withdrawn Mar 10, L7 not listed yet
    assert r["pending"] == 1  # only L5; L3 closed on Mar 31 so it is closed, not pending


def test_absorption_and_months_of_inventory(tiny):
    r = march(tiny)
    assert r["absorption_rate"] == pytest.approx(3.0)  # 3 closed / 1 active
    assert r["months_of_inventory"] == pytest.approx(1 / 3)


def test_band_split_uses_sale_price_for_closed_and_list_price_for_open(tiny):
    low = march(tiny, "$150k-$250k")  # L1 190k, L3 247k closed; L4 list 150k active
    assert low["closed"] == 2
    assert low["median_price"] == pytest.approx(218_500)
    assert low["active"] == 1
    mid = march(tiny, "$250k-$400k")
    assert mid["closed"] == 1 and mid["median_price"] == 300_000
    assert mid["active"] == 0 and mid["pending"] == 0
    top = march(tiny, "$400k+")
    assert top["pending"] == 1  # L5 listed at 400k, boundary goes up
    assert top["closed"] == 0


def test_empty_cells_are_none_not_zero(tiny):
    r = march(tiny, "Under $150k")
    assert r["closed"] == 0
    assert pd.isna(r["median_price"]) and pd.isna(r["median_dom"])
    assert pd.isna(r["months_of_inventory"])  # no closings: undefined, not infinite


def test_april_by_hand(tiny):
    m = monthly_metrics(tiny, "2025-04", "2025-04")
    r = m[m["band"] == ALL].iloc[0]
    assert r["closed"] == 1  # L5 closes Apr 12
    assert r["active"] == 2  # L4 and L7
    assert r["absorption_rate"] == pytest.approx(0.5)
    assert r["months_of_inventory"] == pytest.approx(2.0)


def test_band_boundaries():
    s = band_of(pd.Series([149_999, 150_000, 249_999, 250_000, 399_999, 400_000]))
    assert list(s) == [
        BAND_LABELS[0],
        BAND_LABELS[1],
        BAND_LABELS[1],
        BAND_LABELS[2],
        BAND_LABELS[2],
        BAND_LABELS[3],
    ]


def test_months_and_labels():
    assert months_between("2024-11", "2025-02") == ["2024-11", "2024-12", "2025-01", "2025-02"]
    assert month_label(pd.Timestamp("2025-03-09")) == "2025-03"


def test_every_market_band_month_present(tiny):
    m = monthly_metrics(tiny, "2025-01", "2025-03")
    assert len(m) == 3 * (1 + len(BAND_LABELS))
    assert not any(math.isinf(v) for v in m["months_of_inventory"].dropna())
