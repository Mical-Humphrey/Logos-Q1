from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["dt", "open", "high", "low", "close", "volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df = df.copy()
    df["dt"] = pd.to_datetime(df["dt"], utc=True)
    df = df.sort_values("dt").reset_index(drop=True)
    return df


def clean_numeric(
    df: pd.DataFrame, cols=("open", "high", "low", "close", "volume")
) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=list(cols))
    return df


def require_datetime_index(obj: Any, *, context: str) -> pd.DatetimeIndex:
    if not hasattr(obj, "index"):
        raise TypeError(f"{context} requires an indexed pandas object.")
    index = obj.index  # type: ignore[attr-defined]
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError(
            f"{context} requires a pandas.DatetimeIndex; got {type(index).__name__}."
        )
    return index


def ensure_no_object_dtype(obj: Any, *, context: str) -> None:
    if isinstance(obj, pd.Series):
        if obj.dtype == "object":
            raise ValueError(f"{context} must not contain object dtype values.")
        return
    if isinstance(obj, pd.DataFrame):
        object_cols = obj.select_dtypes(include=["object"]).columns.tolist()
        if object_cols:
            raise ValueError(
                f"{context} must not contain object dtype columns: {object_cols}"
            )
        return
    raise TypeError(
        f"{context} expects a pandas Series or DataFrame; got {type(obj)!r}."
    )
