"""Bring-your-own-data loader, comparable time adjustment, command line."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from housing_market_trends import pipeline, site
from housing_market_trends.cli import main
from housing_market_trends.loader import LoadError, load_listings
from housing_market_trends.sample import make_sample_export
from housing_market_trends.timeadj import (
    DAYS_PER_MONTH,
    adjust_price,
    adjustment_factor,
    hedonic_time_rate,
    months_between_labels,
)

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sample_mls_export.csv"


# ---- comparable time adjustment, worked by hand ------------------------------------------


def test_adjustment_factor_by_hand():
    assert adjustment_factor(0.12, 12) == pytest.approx(0.12)  # a full year is the annual rate
    assert adjustment_factor(0.06, 6) == pytest.approx(1.06**0.5 - 1)  # 0.029563
    assert adjustment_factor(0.06, 6) == pytest.approx(0.0295630, abs=1e-7)
    assert adjustment_factor(0.10, 0) == 0.0
    assert adjustment_factor(-0.05, 12) == pytest.approx(-0.05)
    assert adjustment_factor(0.06, -6) == pytest.approx(1 / 1.06**0.5 - 1)  # moving backwards


def test_adjust_price_by_hand():
    r = adjust_price(200_000, 0.06, 0.02, 0.10, 12)  # one year: price x (1 + rate)
    assert r["adjusted"] == pytest.approx(212_000)
    assert r["adjusted_lo"] == pytest.approx(204_000)
    assert r["adjusted_hi"] == pytest.approx(220_000)
    assert r["months"] == 12 and r["factor"] == pytest.approx(0.06)


def test_months_between_labels():
    assert months_between_labels("2024-11", "2025-02") == 3
    assert months_between_labels("2025-02", "2025-02") == 0
    assert months_between_labels("2025-03", "2025-01") == -2


# ---- hedonic with optional covariates ----------------------------------------------------


def test_hedonic_works_without_age_and_bedrooms():
    rng = np.random.default_rng(5)
    n, end = 80, pd.Timestamp("2025-06-30")
    days = rng.integers(0, 360, n)
    sqft = rng.uniform(900, 3000, n)
    df = pd.DataFrame(
        {
            "close_date": end - pd.to_timedelta(days, unit="D"),
            "sqft": sqft,
            "year_built": np.nan,
            "beds": np.nan,
            "sale_price": np.exp(11 + 0.8 * np.log(sqft) - 0.004 * days / DAYS_PER_MONTH),
        }
    )
    est = hedonic_time_rate(df, end)
    assert est is not None
    assert est.annual == pytest.approx(np.expm1(0.048), abs=1e-9)  # +0.4% a month, log terms


# ---- loader ------------------------------------------------------------------------------

RESO = (
    "ListingContractDate,PurchaseContractDate,CloseDate,ListPrice,ClosePrice,LivingArea,Area\n"
    '01/05/2025,01/20/2025,02/25/2025,"$210,000","$205,000","1,500",North\n'
    '01/15/2025,,,"$150,000",,1100,North\n'
    "02/01/2025,02/10/2025,03/15/2025,$300000,$310000,2000,South\n"
)


def write(tmp_path, text, name="x.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_loader_maps_reso_headers_and_cleans_prices(tmp_path):
    df, rep = load_listings(write(tmp_path, RESO))
    assert rep.rows_read == 3 and rep.rows_used == 3
    assert rep.mapped["list_price"] == "ListPrice" and rep.mapped["close_date"] == "CloseDate"
    assert df.loc[0, "list_price"] == 210_000 and df.loc[0, "sale_price"] == 205_000
    assert df.loc[0, "sqft"] == 1500  # "1,500"
    assert df.loc[2, "sale_price"] == 310_000  # "$310000"
    assert df.loc[0, "close_date"] == pd.Timestamp("2025-02-25")
    assert pd.isna(df.loc[1, "close_date"]) and pd.isna(df.loc[1, "sale_price"])
    assert list(df["market"]) == ["North", "North", "South"]


def test_loader_notes_missing_optional_columns(tmp_path):
    rows = [
        "ListDate,ListPrice,SqFt,CloseDate,ClosePrice",
        "01/05/2025,210000,1500,02/25/2025,205000",
        "01/15/2025,150000,1100,03/01/2025,148000",
    ]
    df, rep = load_listings(write(tmp_path, chr(10).join(rows) + chr(10)))
    notes = " ".join(rep.notes)
    assert "no market/area column" in notes and "no pending/contract" in notes
    assert "paired-resale" in notes
    assert (df["market"] == "All listings").all()
    assert df.loc[0, "pending_date"] == df.loc[0, "close_date"]  # DOM runs to the close date
    assert df["property_id"].is_unique


def test_loader_rejects_missing_required_columns(tmp_path):
    with pytest.raises(LoadError, match="missing required columns: sqft"):
        load_listings(
            write(tmp_path, "ListDate,ListPrice,CloseDate,ClosePrice\n1/1/2025,1,1/2/2025,1\n")
        )


def test_loader_needs_closed_sales(tmp_path):
    text = "ListDate,ListPrice,SqFt,CloseDate,ClosePrice\n01/01/2025,100000,1000,,\n"
    with pytest.raises(LoadError, match="close_date and sale_price|no closed sales"):
        load_listings(write(tmp_path, text.replace(",CloseDate,ClosePrice", "").replace(",,", "")))
    with pytest.raises(LoadError, match="no closed sales"):
        load_listings(write(tmp_path, text))


def test_loader_counts_bad_rows(tmp_path):
    text = (
        "ListDate,ListPrice,SqFt,CloseDate,ClosePrice\n"
        "01/01/2025,100000,1000,02/01/2025,95000\n"
        "not a date,100000,1000,02/01/2025,95000\n"  # unreadable list date: dropped
        "01/01/2025,100000,0,02/01/2025,95000\n"  # zero sq ft: dropped
        "01/01/2025,100000,1000,02/01/2025,\n"  # close date without a price: not closed
    )
    df, rep = load_listings(write(tmp_path, text))
    assert rep.rows_read == 4 and rep.rows_used == 2
    assert "unreadable list_date" in " ".join(rep.notes)
    assert "2 rows dropped" in " ".join(rep.notes)
    assert df["close_date"].notna().sum() == 1


# ---- analyze on any listings --------------------------------------------------------------


def test_analyze_short_history_does_not_crash(tmp_path):
    df, _ = load_listings(write(tmp_path, RESO))
    res = pipeline.analyze(df)
    assert (res.first, res.last) == ("2025-02", "2025-03")
    assert res.adjustment.empty and res.summaries == []  # needs 12 months of sales
    assert not res.synthetic


def test_sample_export_round_trip(tmp_path):
    p = tmp_path / "s.csv"
    n = make_sample_export(p)
    assert n > 3000
    df, rep = load_listings(p)
    assert rep.rows_used == n - 9  # 6 rows lost sq ft, 3 lost their list date
    assert any("unreadable list_date" in x for x in rep.notes)
    res = pipeline.analyze(df)
    assert (res.first, res.last) == ("2023-01", "2025-12")
    s = next(
        x
        for x in res.summaries
        if (x["market"], x["band"], x["month"]) == ("Maple Ridge", "All prices", "2025-12")
    )
    assert s["condition"] == "increasing"  # planted +8% a year
    flat = next(
        x
        for x in res.summaries
        if (x["market"], x["band"], x["month"]) == ("Stonebrook", "All prices", "2025-12")
    )
    assert flat["condition"] == "stable"  # planted 0%


def test_committed_sample_matches_generator(tmp_path):
    p = tmp_path / "again.csv"
    make_sample_export(p)
    assert p.read_text(encoding="utf-8") == SAMPLE.read_text(encoding="utf-8")


def test_site_for_your_own_data_has_no_planted_truth(tmp_path):
    df, _ = load_listings(SAMPLE)
    res = pipeline.analyze(df)
    payload = site.build_payload(res)
    assert payload["synthetic"] is False and payload["truth"] == {}
    assert payload["months"][0] == "2023-01" and len(payload["months"]) == 36
    html = site.build(tmp_path, res).read_text(encoding="utf-8")
    raw = html.split('<script id="data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(raw)["synthetic"] is False


# ---- command line -------------------------------------------------------------------------


def test_cli_summary_on_your_data(capsys):
    main(["summary", "--listings", str(SAMPLE), "Maple Ridge"])
    out = capsys.readouterr().out
    assert "prices look rising" in out and "USPAP" in out
    assert "unreadable list_date" in out  # the cleaning report is shown


def test_cli_adjust_prints_factor_and_price(capsys):
    main(
        [
            "adjust",
            "--listings",
            str(SAMPLE),
            "--market",
            "Maple Ridge",
            "--sale-month",
            "2025-06",
            "--price",
            "250000",
        ]
    )
    out = capsys.readouterr().out
    assert "(6 months)" in out and "time adjustment +" in out and "adjusted price" in out
    assert "Not an appraisal" in out


def test_cli_rejects_a_bad_file(tmp_path):
    bad = write(tmp_path, "a,b\n1,2\n")
    with pytest.raises(SystemExit, match="missing required columns"):
        main(["summary", "--listings", str(bad)])


def test_cli_build_for_your_data(tmp_path):
    main(["build", "--listings", str(SAMPLE), "--out", str(tmp_path)])
    assert (tmp_path / "index.html").exists() and (tmp_path / "metrics.csv").exists()
    assert not (tmp_path / "listings_synthetic.csv").exists()  # your rows are not re-exported
