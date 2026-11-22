import pandas as pd
import pytest


@pytest.fixture
def tiny() -> pd.DataFrame:
    """Seven hand-made listings in one market; March 2025 is worked out by hand in the tests."""
    na = pd.NaT
    rows = [
        # id, property, list, pending, close, withdrawn, list_price, sale_price, sqft
        ("L1", 1, "2025-01-10", "2025-02-20", "2025-03-15", na, 200_000, 190_000, 1000),
        ("L2", 2, "2025-02-01", "2025-03-01", "2025-03-20", na, 300_000, 300_000, 1500),
        ("L3", 3, "2025-02-10", "2025-03-05", "2025-03-31", na, 260_000, 247_000, 1300),
        ("L4", 4, "2025-03-02", na, na, na, 150_000, float("nan"), 1200),
        ("L5", 5, "2025-01-15", "2025-03-10", "2025-04-12", na, 400_000, float("nan"), 2000),
        ("L6", 6, "2025-02-20", na, na, "2025-03-10", 500_000, float("nan"), 2500),
        ("L7", 7, "2025-04-05", na, na, na, 220_000, float("nan"), 1100),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "listing_id",
            "property_id",
            "list_date",
            "pending_date",
            "close_date",
            "withdrawn_date",
            "list_price",
            "sale_price",
            "sqft",
        ],
    )
    for c in ("list_date", "pending_date", "close_date", "withdrawn_date"):
        df[c] = pd.to_datetime(df[c])
    df["market"] = "A"
    df["beds"] = 3
    df["year_built"] = 1990
    return df
