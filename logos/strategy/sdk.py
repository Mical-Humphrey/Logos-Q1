from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Mapping, Sequence

import pandas as pd

from logos.utils.data_hygiene import ensure_no_object_dtype, require_datetime_index


class StrategyError(RuntimeError):
    """Raised when a strategy preset encounters invalid inputs or state."""


@dataclass(frozen=True)
class StrategyContext:
    """Snapshot of the most recent decision used for explain output."""

    timestamp: pd.Timestamp
    price: float
    signal: float
    diagnostics: Dict[str, float | int | str | None] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "timestamp": self.timestamp.isoformat(),
            "price": float(self.price),
            "signal": float(self.signal),
        }
        if self.diagnostics:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


def ensure_price_frame(
    df: pd.DataFrame,
    *,
    context: str,
    required: Sequence[str] = ("Close",),
) -> pd.DataFrame:
    """Validate price frame structure used by strategy presets."""

    if df is None:
        raise StrategyError(f"{context}: dataframe is None")
    if df.empty:
        raise StrategyError(f"{context}: dataframe is empty")
    require_datetime_index(df, context=f"{context}.index")
    ensure_no_object_dtype(df, context=f"{context}.dtypes")
    missing = [col for col in required if col not in df.columns]
    if missing:
        missing_cols = ", ".join(sorted(str(col) for col in missing))
        raise StrategyError(f"{context}: missing required columns: {missing_cols}")
    required_slice = df.loc[:, list(required)]
    if required_slice.isna().any().any():
        raise StrategyError(f"{context}: NaN detected in required price columns")
    return df


def guard_no_nan(series: pd.Series, *, context: str) -> None:
    """Fail closed when NaNs are observed in a signal series."""

    if series.isna().any():
        raise StrategyError(f"{context}: NaN detected in signals")


def _validate_cap(cap: float) -> float:
    if not math.isfinite(cap) or cap <= 0:
        raise StrategyError("exposure_cap must be positive and finite")
    return float(cap)


class StrategyPreset:
    """Base implementation of the Strategy SDK contract."""

    name: str = "strategy"

    def __init__(self, *, exposure_cap: float = 1.0) -> None:
        self.exposure_cap = _validate_cap(exposure_cap)
        self._last_context: StrategyContext | None = None
        self._fitted = False

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> None:
        """Optional subclasses can override to pre-compute state."""

        ensure_price_frame(df, context=f"{self.name}.fit")
        self._fitted = True

    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> pd.Series:
        """Return target exposure signals. Subclasses must implement."""

        raise NotImplementedError

    # ------------------------------------------------------------------
    def generate_order_intents(self, signals: pd.Series) -> pd.Series:
        """Clamp exposures to the configured cap and guard against NaNs."""

        guard_no_nan(signals, context=f"{self.name}.signals")
        clipped = signals.clip(lower=-self.exposure_cap, upper=self.exposure_cap)
        if not clipped.empty:
            self._last_signal = float(clipped.iloc[-1])
        return clipped

    # ------------------------------------------------------------------
    def params(self) -> Mapping[str, object]:
        """Expose preset parameters for documentation and explain output."""

        return {}

    # ------------------------------------------------------------------
    def explain(self, ctx: StrategyContext | None = None) -> Dict[str, object]:
        """Return a structured explanation of the last decision."""

        resolved = ctx or self._last_context
        if resolved is None:
            return {
                "reason": "No strategy context available.",
                "signal": {"value": 0.0, "timestamp": None, "price": None},
                "thresholds": {},
                "risk_note": f"Exposure capped to ±{self.exposure_cap}.",
                "params": dict(self.params()),
            }
        payload: Dict[str, object] = {
            "reason": "",
            "signal": {
                "value": resolved.signal,
                "timestamp": resolved.timestamp.isoformat(),
                "price": resolved.price,
            },
            "thresholds": {},
            "risk_note": f"Exposure capped to ±{self.exposure_cap}.",
            "params": dict(self.params()),
        }
        if resolved.diagnostics:
            payload["diagnostics"] = dict(resolved.diagnostics)
        return payload

    # ------------------------------------------------------------------
    def _record_context(self, ctx: StrategyContext) -> None:
        """Persist the most recent decision for later explain() calls."""

        self._last_context = ctx

    # ------------------------------------------------------------------
    def _build_payload(
        self,
        ctx: StrategyContext,
        *,
        reason: str,
        thresholds: Mapping[str, float | int | str | None],
        risk_note: str | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "reason": reason,
            "signal": {
                "value": ctx.signal,
                "timestamp": ctx.timestamp.isoformat(),
                "price": ctx.price,
            },
            "thresholds": dict(thresholds),
            "risk_note": risk_note or f"Exposure capped to ±{self.exposure_cap}.",
            "params": dict(self.params()),
        }
        diagnostics = dict(ctx.diagnostics)
        if extra:
            diagnostics.update(extra)
        if diagnostics:
            payload["diagnostics"] = diagnostics
        return payload

    # ------------------------------------------------------------------
    def _require_fit(self) -> None:
        if not self._fitted:
            raise StrategyError(f"{self.name}: call fit() before predict()")

    # ------------------------------------------------------------------
    @staticmethod
    def _clip_series(series: pd.Series, *, cap: float) -> pd.Series:
        return series.clip(lower=-cap, upper=cap)

    # ------------------------------------------------------------------
    @staticmethod
    def _rolling_mean(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window, min_periods=window).mean()

    # ------------------------------------------------------------------
    @staticmethod
    def _rolling_std(series: pd.Series, window: int) -> pd.Series:
        return series.rolling(window=window, min_periods=window).std(ddof=0)

    # ------------------------------------------------------------------
    @staticmethod
    def _validate_window(name: str, value: int) -> int:
        if int(value) < 2:
            raise StrategyError(f"{name} must be >= 2")
        return int(value)

    # ------------------------------------------------------------------
    @staticmethod
    def _validate_non_negative(name: str, value: float) -> float:
        numeric = float(value)
        if numeric < 0:
            raise StrategyError(f"{name} must be >= 0")
        return numeric

    # ------------------------------------------------------------------
    @staticmethod
    def _validate_positive(name: str, value: float) -> float:
        numeric = float(value)
        if numeric <= 0:
            raise StrategyError(f"{name} must be > 0")
        return numeric


def clip_exposure(series: pd.Series, *, cap: float) -> pd.Series:
    """Standalone helper mirroring StrategyPreset.generate_order_intents."""

    _validate_cap(cap)
    guard_no_nan(series, context="clip_exposure")
    return series.clip(lower=-cap, upper=cap)


def ensure_positive_numeric(name: str, value: float) -> float:
    """Helper to validate CLI/Config numeric parameters."""

    numeric = float(value)
    if not math.isfinite(numeric) or numeric <= 0:
        raise StrategyError(f"{name} must be positive and finite")
    return numeric


def ensure_bounds(sequence: Iterable[float], *, cap: float) -> None:
    """Verify that all values sit within ±cap for safety checks."""

    _validate_cap(cap)
    for item in sequence:
        if abs(float(item)) > cap + 1e-9:
            raise StrategyError(f"signal value {item} exceeds exposure cap ±{cap}")
