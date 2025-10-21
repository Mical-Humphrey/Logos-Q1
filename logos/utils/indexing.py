from __future__ import annotations

from typing import Any

import pandas as pd


def _ensure_datetime_index(
    obj: pd.Series | pd.DataFrame, *, context: str
) -> pd.DatetimeIndex:
    index = obj.index
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError(
            f"{context} requires a pandas.DatetimeIndex; got {type(index).__name__}."
        )
    return index


def _coerce_timestamp(label: Any, *, context: str) -> pd.Timestamp:
    if isinstance(label, pd.Timestamp):
        return label
    try:
        return pd.Timestamp(label)
    except Exception as exc:  # pragma: no cover - defensive
        raise TypeError(
            f"{context} requires a pandas.Timestamp-compatible label; got {label!r}."
        ) from exc


def label_value(series: pd.Series, label: Any) -> Any:
    """Return the value at ``label`` using ``.loc`` on a DatetimeIndex-aware series."""
    _ensure_datetime_index(series, context="label_value")
    ts = _coerce_timestamp(label, context="label_value")
    return series.loc[ts]


def adjust_from(series: pd.Series, label: Any, delta: float) -> None:
    """Add ``delta`` to all rows at or after ``label`` using label-aware selection."""
    _ensure_datetime_index(series, context="adjust_from")
    ts = _coerce_timestamp(label, context="adjust_from")
    label_slice = slice(ts, None)
    tail = series.loc[label_slice]
    series.loc[label_slice] = tail + delta


def adjust_at(series: pd.Series, label: Any, delta: float) -> None:
    """Add ``delta`` to the row(s) exactly at ``label`` using label-aware selection."""
    _ensure_datetime_index(series, context="adjust_at")
    ts = _coerce_timestamp(label, context="adjust_at")
    current = series.loc[ts]
    series.loc[ts] = current + delta  # type: ignore[call-overload]


def last_value(series: pd.Series) -> Any:
    """Return the last value in a series using positional indexing."""
    return series.iloc[-1]


def last_row(frame: pd.DataFrame) -> pd.Series:
    """Return the last row of ``frame`` using positional indexing."""
    return frame.iloc[-1]
