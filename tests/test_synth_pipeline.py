import json

import pandas as pd
import pytest

from housing_market_trends import benchmark, pipeline, site, synth
from housing_market_trends.synth import MARKETS, annual_rate, planted_log_growth


def test_annual_rate_phases():
    pine = next(m for m in MARKETS if m.name == "Pine Hollow")
    assert annual_rate(pine, 0) == 0.10 and annual_rate(pine, 29) == 0.10
    assert annual_rate(pine, 30) == -0.06 and annual_rate(pine, 59) == -0.06
    assert annual_rate(pine, -3) == 0.10 and annual_rate(pine, 70) == -0.06  # extended


def test_planted_log_growth_compounds_to_annual():
    maple = next(m for m in MARKETS if m.name == "Maple Ridge")
    g = planted_log_growth(maple, range(12))
    assert g.sum() == pytest.approx(0.0769610411)  # ln(1.08)


def test_generate_is_deterministic_and_seed_sensitive():
    a, b = synth.generate(seed=7, months=14), synth.generate(seed=7, months=14)
    pd.testing.assert_frame_equal(a, b)
    assert not a.equals(synth.generate(seed=8, months=14))


def test_generate_respects_as_of_date_and_status_logic():
    df = synth.generate(seed=3, months=14)
    asof = pd.Timestamp("2021-01-01") + pd.DateOffset(months=14) - pd.Timedelta(days=1)
    for c in ("list_date", "pending_date", "close_date", "withdrawn_date"):
        assert df[c].dropna().max() <= asof
    sold = df.dropna(subset=["close_date"])
    assert sold["sale_price"].notna().all()
    assert (sold["close_date"] > sold["pending_date"]).all()
    assert df.loc[df["close_date"].isna(), "sale_price"].isna().all()
    assert df["listing_id"].is_unique


def test_names_are_invented_markets_only():
    names = {m.name for m in MARKETS}
    assert names == {"Maple Ridge", "Stonebrook", "Pine Hollow", "Lakeshore Bend"}


@pytest.fixture(scope="module")
def result():
    return pipeline.run()


def test_truth_table_values():
    t = pipeline.truth_table().set_index(["market", "month"])["truth"]
    assert t[("Stonebrook", "2025-12")] == pytest.approx(0.0, abs=1e-12)
    assert t[("Maple Ridge", "2025-12")] == pytest.approx(0.08)
    assert t[("Lakeshore Bend", "2025-12")] == pytest.approx(-0.05)
    assert t[("Pine Hollow", "2023-06")] == pytest.approx(0.10)  # window fully inside +10% phase
    assert t[("Pine Hollow", "2025-12")] == pytest.approx(-0.06)


def test_planted_trends_are_recovered(result):
    a = benchmark.score(result)
    hed = a[a["method"] == "hedonic"]
    assert hed["err_pp"].abs().mean() < 2.5  # measured ~1.5 at seed 42
    assert hed["covered"].mean() > 0.85  # a 95% band should cover the truth most of the time
    for market, g in hed.groupby("market"):
        assert g["err_pp"].abs().mean() < 3.0, market


def test_condition_labels_match_planted_direction(result):
    hit, tot = benchmark.direction_hits(result)
    assert hit / tot > 0.8


def test_flat_market_is_not_called_a_trend(result):
    s = next(
        x
        for x in result.summaries
        if (x["market"], x["band"], x["month"]) == ("Stonebrook", "All prices", "2025-12")
    )
    assert s["condition"] == "stable"


def test_bands_partition_closed_sales(result):
    m = result.metrics
    all_rows = m[m["band"] == "All prices"].set_index(["market", "month"])["closed"]
    band_sum = m[m["band"] != "All prices"].groupby(["market", "month"])["closed"].sum()
    assert (all_rows == band_sum.reindex(all_rows.index)).all()


def test_site_payload_and_html(tmp_path, result):
    p = site.build_payload(result)
    assert len(p["months"]) == 60 and len(p["markets"]) == 4 and len(p["bands"]) == 5
    k = "Pine Hollow|All prices"
    assert len(p["metrics"][k]["median_price"]) == 60
    assert p["summaries"][k]["2025-12"]["condition"] == "declining"
    path = site.build(tmp_path, result)
    html = path.read_text("utf-8")
    raw = html.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(raw)["markets"] == p["markets"]
    assert "USPAP" in html and "—" not in html and "__DATA__" not in html
