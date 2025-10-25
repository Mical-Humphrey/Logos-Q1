from __future__ import annotations

import pandas as pd
import pytest

from logos.data import ColumnSpec, DataContract, SchemaViolationError, time_safe_join


def _frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2024-01-01 09:30", "2024-01-01 09:31"], utc=True)
    return pd.DataFrame({"Open": [100.0, 101.0], "Close": [101.0, 102.0]}, index=idx)


def test_contract_validates_schema():
    contract = DataContract(
        "bars",
        (
            ColumnSpec("Open", "float"),
            ColumnSpec("Close", "float"),
        ),
    )
    contract.validate(_frame())
    bad = _frame().drop(columns=["Close"])
    with pytest.raises(SchemaViolationError):
        contract.validate(bad)


def test_contract_rejects_unsorted_index():
    contract = DataContract("bars", (ColumnSpec("Open", "float"),))
    frame = _frame().sort_index(ascending=False)
    with pytest.raises(SchemaViolationError):
        contract.validate(frame)


def test_time_safe_join(monkeypatch):
    left = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([
                "2024-01-01 09:31",
                "2024-01-01 09:32",
                "2024-01-01 09:33",
            ], utc=True),
            "target": [1, 2, 3],
        }
    )
    right = pd.DataFrame(
        {
            "timestamp": pd.to_datetime([
                "2024-01-01 09:30",
                "2024-01-01 09:31",
            ], utc=True),
            "feature": [10.0, 11.0],
        }
    )
    joined = time_safe_join(left, right)
    assert list(joined["feature"]) == [10.0, 11.0, 11.0]

    unsorted = right.iloc[::-1].reset_index(drop=True)
    with pytest.raises(SchemaViolationError):
        time_safe_join(left, unsorted)
