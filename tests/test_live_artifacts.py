from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from logos.live.artifacts import (
    ACCOUNT_COLUMNS,
    ORDER_COLUMNS,
    POSITION_COLUMNS,
    TRADE_COLUMNS,
    load_account,
    load_orders,
    load_positions,
    load_trades,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(f"# {path.name} fixture\n")
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def test_load_trades_handles_legacy_layout(tmp_path: Path) -> None:
    header = [
        "ts",
        "id",
        "symbol",
        "side",
        "qty",
        "price",
        "fees",
        "slip_bps",
        "order_type",
        "session_id",
        "strategy",
    ]
    row = ["2025-01-01T09:31:00+00:00", "F1", "MSFT", "buy", 5, 100.5, 0.25, 5, "market", "legacy-session", "momentum"]
    csv_path = tmp_path / "trades.csv"
    _write_csv(csv_path, header, [row])

    df = load_trades(csv_path)

    assert list(df.columns) == TRADE_COLUMNS
    assert df.iloc[0]["session_id"] == "legacy-session"
    assert df.iloc[0]["strategy"] == "momentum"
    assert pd.Timestamp("2025-01-01T09:31:00+00:00") == df.iloc[0]["ts"]


def test_load_orders_fills_missing_metadata(tmp_path: Path) -> None:
    header = [
        "ts",
        "id",
        "symbol",
        "side",
        "qty",
        "limit_price",
        "state",
        "reject_reason",
        "broker_order_id",
    ]
    row = ["2025-01-01T09:31:00+00:00", "O1", "MSFT", "buy", 5, 101.0, "submitted", "", "PB-1"]
    csv_path = tmp_path / "orders.csv"
    _write_csv(csv_path, header, [row])

    df = load_orders(csv_path, session_id="sess", strategy="momentum")

    assert list(df.columns) == ORDER_COLUMNS
    assert df.iloc[0]["session_id"] == "sess"
    assert df.iloc[0]["strategy"] == "momentum"
    assert df.iloc[0]["order_type"] == ""


def test_load_positions_accepts_new_layout(tmp_path: Path) -> None:
    header = POSITION_COLUMNS
    row = ["2025-01-01T09:31:00+00:00", "sess", "MSFT", "momentum", 5.0, 100.0, 2.0]
    csv_path = tmp_path / "positions.csv"
    _write_csv(csv_path, header, [row])

    df = load_positions(csv_path)

    assert list(df.columns) == POSITION_COLUMNS
    assert df.iloc[0]["qty"] == 5.0


def test_load_account_infers_defaults(tmp_path: Path) -> None:
    header = ["ts", "cash", "equity", "buying_power"]
    row = ["2025-01-01T09:31:00+00:00", 50000.0, 75000.0, 50000.0]
    csv_path = tmp_path / "account.csv"
    _write_csv(csv_path, header, [row])

    df = load_account(csv_path, session_id="sess", strategy="momentum", symbol="MSFT")

    assert list(df.columns) == ACCOUNT_COLUMNS
    assert df.iloc[0]["currency"] == "USD"
    assert df.iloc[0]["symbol"] == "MSFT"
    assert df.iloc[0]["session_id"] == "sess"
