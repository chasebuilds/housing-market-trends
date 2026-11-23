"""Command line: build the dashboard, print a summary, time-adjust a comparable."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import pipeline, site
from .loader import LoadError, load_listings
from .metrics import ALL
from .sample import make_sample_export
from .timeadj import adjust_price, months_between_labels


def _result(args: argparse.Namespace) -> pipeline.Result:
    if not args.listings:
        return pipeline.run(seed=args.seed)
    try:
        df, report = load_listings(args.listings)
    except LoadError as e:
        raise SystemExit(f"cannot use {args.listings}: {e}") from e
    print(f"read {report.rows_read} rows, using {report.rows_used}")
    for note in report.notes:
        print(" -", note)
    return pipeline.analyze(df)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--listings", type=Path, help="your own MLS-style CSV (default: synthetic demo)")
    p.add_argument("--seed", type=int, default=42, help="seed for the synthetic demo")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="hmt", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build dist/index.html and CSVs")
    _common(b)
    b.add_argument("--out", type=Path, default=Path("dist"))
    s = sub.add_parser("summary", help="print the market-conditions summary")
    _common(s)
    s.add_argument("market", nargs="?", help="market name (default: the first market)")
    s.add_argument("--band", default=ALL)
    s.add_argument("--month", help="as-of month, YYYY-MM (default: latest)")
    a = sub.add_parser("adjust", help="time-adjust a comparable sale to an as-of month")
    _common(a)
    a.add_argument("--market", help="market name (default: the first market)")
    a.add_argument("--band", default=ALL)
    a.add_argument("--sale-month", required=True, help="month the comparable sold, YYYY-MM")
    a.add_argument("--as-of", help="effective-date month, YYYY-MM (default: latest)")
    a.add_argument("--price", type=float, help="comparable sale price")
    sm = sub.add_parser("sample", help="write a synthetic MLS-style export to try analyze on")
    sm.add_argument("path", type=Path, nargs="?", default=Path("sample_mls_export.csv"))
    args = ap.parse_args(argv)

    if args.cmd == "sample":
        print(f"wrote {make_sample_export(args.path)} rows to {args.path}")
        return
    res = _result(args)
    if args.cmd == "build":
        path = site.build(args.out, res)
        res.metrics.to_csv(args.out / "metrics.csv", index=False)
        res.adjustment.to_csv(args.out / "time_adjustment.csv", index=False)
        if res.synthetic:
            res.listings.to_csv(args.out / "listings_synthetic.csv", index=False)
        print(f"wrote {path}")
        return
    market = args.market or str(res.listings["market"].iloc[0])
    month = (args.month if args.cmd == "summary" else args.as_of) or res.last
    if args.cmd == "summary":
        for item in res.summaries:
            if (item["market"], item["band"], item["month"]) == (market, args.band, month):
                print(item["headline"])
                for line in item["evidence"]:
                    print(" -", line)
                print(item["disclaimer"])
                return
        raise SystemExit("no such market, band and month (time adjustment starts 12 months in)")
    adj = res.adjustment
    row = adj[(adj["market"] == market) & (adj["band"] == args.band) & (adj["month"] == month)]
    row = row.sort_values("method")  # hedonic first, paired as the fallback
    if row.empty:
        raise SystemExit(f"not enough sales to estimate a rate for {market} ({args.band}), {month}")
    r = row.iloc[0]
    months = months_between_labels(args.sale_month, month)
    out = adjust_price(args.price or 100.0, r["annual"], r["lo"], r["hi"], months)
    print(
        f"{market} ({args.band}): comparable sold {args.sale_month}, as of {month} "
        f"({months} months), rate {r['annual'] * 100:+.1f}% a year from {r['method']} on "
        f"{int(r['n'])} observations"
    )
    print(
        f"time adjustment {out['factor'] * 100:+.2f}% (95% band "
        f"{out['factor_lo'] * 100:+.2f}% to {out['factor_hi'] * 100:+.2f}%)"
    )
    if args.price:
        print(
            f"adjusted price {out['adjusted']:,.0f} "
            f"({out['adjusted_lo']:,.0f} to {out['adjusted_hi']:,.0f})"
        )
    print("Analysis and education only. Not an appraisal; USPAP work needs a licensed appraiser.")
