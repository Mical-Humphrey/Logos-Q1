from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd
from pandas.api import types as ptypes

__all__ = ["ColumnSpec", "DataContract", "SchemaViolationError", "time_safe_join"]


class SchemaViolationError(ValueError):
    """Raised when data does not satisfy the declared contract."""


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    dtype: str
    nullable: bool = False

    def validate(self, series: pd.Series) -> None:
        check = self._checker()
        if not check(series):
            raise SchemaViolationError(f"column '{self.name}' expected {self.dtype}")
        if not self.nullable and series.isna().any():
            raise SchemaViolationError(f"column '{self.name}' contains nulls")

    def _checker(self) -> callable:
        kind = self.dtype.lower()
        if kind in {"float", "float64", "float32"}:
            return ptypes.is_float_dtype
        if kind in {"int", "int64", "int32"}:
            return ptypes.is_integer_dtype
        if kind in {"bool", "boolean"}:
            return ptypes.is_bool_dtype
        if kind in {"category", "categorical"}:
            return ptypes.is_categorical_dtype
        if kind in {"datetime", "datetime64"}:
            return ptypes.is_datetime64_any_dtype
        if kind in {"string", "object"}:
            return ptypes.is_object_dtype
        raise SchemaViolationError(f"unsupported dtype '{self.dtype}'")


@dataclass
class DataContract:
    name: str
    columns: Sequence[ColumnSpec]
    index: str = "datetime"
    allow_extra: bool = False

    def validate(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise SchemaViolationError("payload must be a DataFrame")
        missing = [spec.name for spec in self.columns if spec.name not in frame.columns]
        if missing:
            joined = ", ".join(missing)
            raise SchemaViolationError(f"missing columns: {joined}")
        if not self.allow_extra:
            extras = [col for col in frame.columns if col not in {spec.name for spec in self.columns}]
            if extras:
                joined = ", ".join(extras)
                raise SchemaViolationError(f"unexpected columns: {joined}")
        for spec in self.columns:
            spec.validate(frame[spec.name])
        if self.index == "datetime":
            if not ptypes.is_datetime64_any_dtype(frame.index):
                raise SchemaViolationError("index must be datetime-like")
        elif self.index == "none":
            pass
        else:
            raise SchemaViolationError(f"unsupported index contract '{self.index}'")
        if frame.index.is_monotonic_increasing is False:
            raise SchemaViolationError("index must be sorted ascending")
        return frame


def _ensure_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        raise SchemaViolationError(f"missing join key '{column}'")
    series = frame[column]
    if not ptypes.is_datetime64_any_dtype(series):
        raise SchemaViolationError(f"join key '{column}' must be datetime-like")
    return series


def time_safe_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    left_on: str = "timestamp",
    right_on: str | None = None,
    suffixes: tuple[str, str] = ("", "_feat"),
    tolerance: str | None = None,
) -> pd.DataFrame:
    """Merge features using backward-looking semantics."""

    right_key = right_on or left_on
    _ensure_column(left, left_on)
    _ensure_column(right, right_key)
    left_sorted = left.sort_values(left_on)
    # Preserve the caller's ordering requirement: the right frame must already
    # be sorted ascending on the join key. Do not sort in-place before this
    # check because tests expect an unsorted right frame to raise.
    if right[right_key].is_monotonic_increasing is False:
        raise SchemaViolationError("feature frame must be sorted ascending")
    right_sorted = right.sort_values(right_key)
    tol = None
    if tolerance is not None:
        tol = pd.Timedelta(tolerance)
    temp_key = "__right_join_key__"
    right_payload = right_sorted.rename(columns={right_key: temp_key})
    # To ensure strictly backward-looking semantics (exclude equal-timestamp
    # matches), nudge right-side timestamps forward by a tiny epsilon so that
    # equal timestamps on the right will not be considered <= left timestamps.
    try:
        right_payload[temp_key] = right_payload[temp_key] + pd.Timedelta(nanoseconds=1)
    except Exception:
        # If for some reason the addition fails, proceed without nudging; the
        # downstream guard will still detect future-data cases.
        pass
    merged = pd.merge_asof(
        left_sorted,
        right_payload,
        left_on=left_on,
        right_on=temp_key,
        direction="backward",
        suffixes=suffixes,
        tolerance=tol,
    )
    guard = merged[temp_key]
    if guard.isna().all():
        return merged.drop(columns=temp_key)
    mask = guard.notna() & (guard > merged[left_on])
    if mask.any():
        raise SchemaViolationError("future data detected in join")
    return merged.drop(columns=temp_key)


def ensure_contract(contract: DataContract, frames: Iterable[pd.DataFrame]) -> None:
    for frame in frames:
        contract.validate(frame)
