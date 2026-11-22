"""Command line: build the dashboard, export CSVs, or print one summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import pipeline, site
from .metrics import ALL


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="hmt", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build dist/index.html and CSVs")
    b.add_argument("--out", type=Path, default=Path("dist"))
    b.add_argument("--seed", type=int, default=42)
    s = sub.add_parser("summary", help="print the market-conditions summary")
    s.add_argument("market")
    s.add_argument("--band", default=ALL)
    s.add_argument("--month", default=pipeline.LAST_MONTH)
    s.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    res = pipeline.run(seed=args.seed)
    if args.cmd == "build":
        path = site.build(args.out, res)
        res.metrics.to_csv(args.out / "metrics.csv", index=False)
        res.adjustment.to_csv(args.out / "time_adjustment.csv", index=False)
        res.listings.to_csv(args.out / "listings_synthetic.csv", index=False)
        print(f"wrote {path}")
    else:
        for item in res.summaries:
            if (item["market"], item["band"], item["month"]) == (
                args.market,
                args.band,
                args.month,
            ):
                print(item["headline"])
                for line in item["evidence"]:
                    print(" -", line)
                print(item["disclaimer"])
                return
        raise SystemExit("no such market, band and month")
