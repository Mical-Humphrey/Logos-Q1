"""Helpers to read live session artifacts with backward-compatible schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

import pandas as pd

TRADE_COLUMNS: List[str] = [
    "ts",
    "session_id",
    "symbol",
    "strategy",
    "id",
    "side",
    "qty",
    "price",
    "fees",
    "slip_bps",
    "order_type",
]

ORDER_COLUMNS: List[str] = [
    "ts",
    "session_id",
    "symbol",
    "strategy",
    "id",
    "side",
    "order_type",
    "qty",
    "limit_price",
    "state",
    "reject_reason",
    "broker_order_id",
]

POSITION_COLUMNS: List[str] = [
    "ts",
    "session_id",
    "symbol",
    "strategy",
    "qty",
    "avg_price",
    "unrealized_pnl",
]

ACCOUNT_COLUMNS: List[str] = [
    "ts",
    "session_id",
    "symbol",
    "strategy",
    "cash",
    "equity",
    "buying_power",
    "currency",
]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, comment="#")


def _ensure_columns(
    df: pd.DataFrame,
    expected: Sequence[str],
    *,
    defaults: dict[str, object] | None = None,
) -> pd.DataFrame:
    defaults = defaults or {}
    for column, value in defaults.items():
        if column not in df.columns:
            df[column] = value
    for column in expected:
        if column not in df.columns:
            df[column] = ""
    return df.loc[:, list(expected)]


def _fill_metadata(df: pd.DataFrame, *, session_id: str | None, strategy: str | None, symbol: str | None) -> None:
    if "session_id" in df.columns and session_id:
        df["session_id"] = df["session_id"].replace("", pd.NA).fillna(session_id)
    elif session_id:
        df["session_id"] = session_id

    if "strategy" in df.columns and strategy:
        df["strategy"] = df["strategy"].replace("", pd.NA).fillna(strategy)
    elif strategy:
        df["strategy"] = strategy

    if symbol and "symbol" in df.columns:
        df["symbol"] = df["symbol"].replace("", pd.NA).fillna(symbol)


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df.sort_values("ts" if "ts" in df.columns else df.index.name or df.index, ignore_index=True)


def load_trades(path: Path, *, session_id: str | None = None, strategy: str | None = None) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS)
    df = _ensure_columns(df, TRADE_COLUMNS)
    _fill_metadata(df, session_id=session_id, strategy=strategy, symbol=None)
    return _finalize(df)


def load_orders(
    path: Path,
    *,
    session_id: str | None = None,
    strategy: str | None = None,
    default_order_type: str = "",
) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=ORDER_COLUMNS)
    df = _ensure_columns(df, ORDER_COLUMNS, defaults={"order_type": default_order_type})
    _fill_metadata(df, session_id=session_id, strategy=strategy, symbol=None)
    return _finalize(df)


def load_positions(
    path: Path,
    *,
    session_id: str | None = None,
    strategy: str | None = None,
) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=POSITION_COLUMNS)
    df = _ensure_columns(df, POSITION_COLUMNS)
    _fill_metadata(df, session_id=session_id, strategy=strategy, symbol=None)
    return _finalize(df)


def load_account(
    path: Path,
    *,
    session_id: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
    default_currency: str = "USD",
) -> pd.DataFrame:
    df = _read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=ACCOUNT_COLUMNS)
    df = _ensure_columns(df, ACCOUNT_COLUMNS, defaults={"currency": default_currency})
    _fill_metadata(df, session_id=session_id, strategy=strategy, symbol=symbol)
    if "currency" in df.columns:
        df["currency"] = df["currency"].replace("", pd.NA).fillna(default_currency)
    return _finalize(df)
