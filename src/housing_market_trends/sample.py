"""Write a synthetic export that looks like a messy MLS download, to try `hmt analyze` on."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import synth


def make_sample_export(path: str | Path, seed: int = 42) -> int:
    """RESO-style headers, $ and commas in prices, US dates, and a few bad rows. Returns rows."""
    df = synth.generate(seed=seed)
    df = df[df["market"].isin(["Maple Ridge", "Stonebrook"])]
    closed_in = df["close_date"].between("2023-01-01", "2025-12-31")
    open_recent = df["close_date"].isna() & (df["list_date"] >= "2025-06-01")
    df = df[closed_in | open_recent].copy()
    out = pd.DataFrame(
        {
            "MLS Number": df["listing_id"].str.replace("L", "MLS"),
            "ParcelNumber": "APN-" + df["property_id"].astype(str).str.zfill(5),
            "Area": df["market"],
            "ListingContractDate": df["list_date"].dt.strftime("%m/%d/%Y"),
            "PurchaseContractDate": df["pending_date"].dt.strftime("%m/%d/%Y"),
            "CloseDate": df["close_date"].dt.strftime("%m/%d/%Y"),
            "ListPrice": df["list_price"].map(lambda v: f"${v:,.0f}"),
            "ClosePrice": df["sale_price"].map(lambda v: "" if pd.isna(v) else f"${v:,.0f}"),
            "LivingArea": df["sqft"].map(lambda v: f"{v:,.0f}"),
            "BedroomsTotal": df["beds"],
            "YearBuilt": df["year_built"],
        }
    )
    rng = np.random.default_rng(seed)
    bad = rng.choice(len(out), size=12, replace=False)
    out.loc[out.index[bad[:6]], "LivingArea"] = ""  # missing living area
    out.loc[out.index[bad[6:9]], "ClosePrice"] = ""  # close date but no price
    out.loc[out.index[bad[9:]], "ListingContractDate"] = "n/a"
    out.to_csv(path, index=False)
    return len(out)
