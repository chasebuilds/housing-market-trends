"""Load your own MLS-style CSV export.

Headers are matched loosely (case, spaces and punctuation ignored), so RESO-style names such
as ListingContractDate or ClosePrice work. Prices may carry $ and commas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ALIASES: dict[str, tuple[str, ...]] = {
    "list_date": ("listingdate", "listingcontractdate", "dateonmarket", "listed"),
    "pending_date": ("contractdate", "undercontractdate", "purchasecontractdate"),
    "close_date": ("closeddate", "solddate", "saledate", "closingdate"),
    "withdrawn_date": ("offmarketdate", "canceldate", "withdrawn"),
    "list_price": ("listingprice", "currentprice", "originallistprice"),
    "sale_price": ("closeprice", "soldprice", "closedprice"),
    "sqft": ("squarefeet", "livingarea", "gla", "grosslivingarea", "buildingareatotal"),
    "beds": ("bedrooms", "bedroomstotal", "br"),
    "year_built": ("builtyear",),
    "market": ("area", "city", "neighborhood", "submarket", "marketarea"),
    "property_id": ("propertyid", "parcel", "parcelid", "apn", "parcelnumber"),
}
REQUIRED = ("list_date", "list_price", "sqft")
DATES = ("list_date", "pending_date", "close_date", "withdrawn_date")
NUMBERS = ("list_price", "sale_price", "sqft", "beds", "year_built")


class LoadError(ValueError):
    """The file cannot be analyzed; the message says what to fix."""


@dataclass
class LoadReport:
    rows_read: int = 0
    rows_used: int = 0
    mapped: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[$,\s]", "", regex=True), errors="coerce")


def load_listings(path: str | Path) -> tuple[pd.DataFrame, LoadReport]:
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    report = LoadReport(rows_read=len(raw))
    by_norm = {_norm(c): c for c in raw.columns}
    out = pd.DataFrame(index=raw.index)
    for canon, names in ALIASES.items():
        for cand in (canon.replace("_", ""), *names):
            if cand in by_norm:
                out[canon] = raw[by_norm[cand]]
                report.mapped[canon] = by_norm[cand]
                break
    missing = [c for c in REQUIRED if c not in out]
    if missing:
        raise LoadError(
            f"missing required columns: {', '.join(missing)}. "
            f"Found headers: {', '.join(raw.columns)}"
        )
    if "close_date" not in out or "sale_price" not in out:
        raise LoadError("need both close_date and sale_price (closed sales) to estimate a trend")

    for c in DATES:
        if c in out:
            parsed = pd.to_datetime(out[c], errors="coerce")
            bad = int(out[c].notna().sum() - parsed.notna().sum())
            if bad:
                report.notes.append(f"{bad} unreadable {c} values were treated as blank")
            out[c] = parsed
        else:
            out[c] = pd.NaT
    for c in NUMBERS:
        out[c] = _num(out[c]) if c in out else np.nan

    if "pending_date" not in report.mapped:
        out["pending_date"] = out["close_date"]
        report.notes.append(
            "no pending/contract date column: days on market runs to the close date and "
            "pending counts are zero"
        )
    if "market" not in out:
        out["market"] = "All listings"
        report.notes.append("no market/area column: everything is one market")
    out["market"] = out["market"].fillna("Unknown").astype(str)
    if "property_id" not in out:
        out["property_id"] = np.arange(len(out))
        report.notes.append("no parcel/property id: paired-resale estimates are unavailable")

    keep = out["list_date"].notna() & out["list_price"].gt(0) & out["sqft"].gt(0)
    dropped = int((~keep).sum())
    if dropped:
        report.notes.append(f"{dropped} rows dropped: bad list date, list price or sq ft")
    out = out[keep].copy()
    odd = out["sale_price"].notna() != out["close_date"].notna()
    if int(odd.sum()):
        report.notes.append(
            f"{int(odd.sum())} rows had a sale price without a close date (or the reverse) "
            "and were treated as not closed"
        )
        out.loc[odd, "sale_price"] = np.nan
        out.loc[odd, "close_date"] = pd.NaT
    if out["close_date"].notna().sum() == 0:
        raise LoadError("no closed sales found after cleaning")
    out = out.reset_index(drop=True)
    out.insert(0, "listing_id", [f"R{i:06d}" for i in range(len(out))])
    report.rows_used = len(out)
    return out, report
