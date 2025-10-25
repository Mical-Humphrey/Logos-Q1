from __future__ import annotations

import math
from typing import Any, Dict, Mapping

import pandas as pd
import numpy as np

from logos.strategy import StrategyContext, StrategyError, StrategyPreset, ensure_price_frame


class CarryPreset(StrategyPreset):
    """Simple carry preset using rolling percentage change as proxy."""

    name = "carry"

    def __init__(
        self,
        *,
        lookback: int = 30,
        entry_threshold: float = 0.01,
        exposure_cap: float = 1.0,
    ) -> None:
        self.lookback = self._validate_window("lookback", lookback)
        self.entry_threshold = self._validate_non_negative("entry_threshold", entry_threshold)
        super().__init__(exposure_cap=exposure_cap)
        self._pending_context: tuple[pd.Timestamp, float, Dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    def params(self) -> Mapping[str, object]:  # type: ignore[override]
        return {
            "lookback": self.lookback,
            "entry_threshold": self.entry_threshold,
            "exposure_cap": self.exposure_cap,
        }

    # ------------------------------------------------------------------
    def fit(self, df: pd.DataFrame) -> None:  # type: ignore[override]
        ensure_price_frame(df, context=f"{self.name}.fit")
        super().fit(df)

    # ------------------------------------------------------------------
    def predict(self, df: pd.DataFrame) -> pd.Series:  # type: ignore[override]
        self._require_fit()
        ensure_price_frame(df, context=f"{self.name}.predict")

        close = df["Close"].astype(float)
        shifted = close.shift(self.lookback)
        carry_series = (close / shifted) - 1.0
        carry_series = carry_series.replace([np.inf, -np.inf], pd.NA)
        carry_ma = carry_series.rolling(self.lookback, min_periods=self.lookback).mean()

        if carry_ma.isna().all():
            raise StrategyError(f"{self.name}: insufficient data to compute carry")

        signals = pd.Series(0.0, index=df.index, dtype=float)
        signals.loc[carry_ma >= self.entry_threshold] = 1.0
        signals.loc[carry_ma <= -self.entry_threshold] = -1.0

        ts = df.index[-1]
        price = float(close.iloc[-1])
        carry_value = carry_ma.iloc[-1]

        diagnostics: Dict[str, Any] = {
            "carry": float(carry_value) if pd.notna(carry_value) else None,
            "lookback": self.lookback,
            "entry_threshold": self.entry_threshold,
        }

        self._pending_context = (ts, price, diagnostics)
        return signals

    # ------------------------------------------------------------------
    def generate_order_intents(self, signals: pd.Series) -> pd.Series:  # type: ignore[override]
        clipped = super().generate_order_intents(signals)
        if self._pending_context and not clipped.empty:
            ts, price, diagnostics = self._pending_context
            ctx = StrategyContext(
                timestamp=ts,
                price=price,
                signal=float(clipped.iloc[-1]),
                diagnostics=diagnostics,
            )
            self._record_context(ctx)
        self._pending_context = None
        return clipped

    # ------------------------------------------------------------------
    def explain(self, ctx: StrategyContext | None = None) -> Dict[str, object]:  # type: ignore[override]
        resolved = ctx or self._last_context
        if resolved is None:
            return super().explain(ctx)

        carry_value = None
        diagnostics = resolved.diagnostics
        if diagnostics:
            carry_value = diagnostics.get("carry")

        reason = "Carry near zero; staying flat."
        if isinstance(carry_value, (int, float)) and math.isfinite(carry_value):
            if carry_value >= self.entry_threshold:
                reason = f"Carry {carry_value:.4f} >= {self.entry_threshold:.4f}; favoring long."
            elif carry_value <= -self.entry_threshold:
                reason = f"Carry {carry_value:.4f} <= -{self.entry_threshold:.4f}; favoring short."
        else:
            reason = "Carry unavailable; staying flat."

        thresholds = {
            "entry_long": self.entry_threshold,
            "entry_short": -self.entry_threshold,
        }

        return self._build_payload(
            resolved,
            reason=reason,
            thresholds=thresholds,
        )


# ----------------------------------------------------------------------
def _build_strategy(
    df: pd.DataFrame,
    *,
    lookback: int = 30,
    entry_threshold: float = 0.01,
    exposure_cap: float = 1.0,
) -> CarryPreset:
    strat = CarryPreset(
        lookback=lookback,
        entry_threshold=entry_threshold,
        exposure_cap=exposure_cap,
    )
    strat.fit(df)
    return strat


# ----------------------------------------------------------------------
def generate_signals(
    df: pd.DataFrame,
    lookback: int = 30,
    entry_threshold: float = 0.01,
    exposure_cap: float = 1.0,
) -> pd.Series:
    strat = _build_strategy(df, lookback=lookback, entry_threshold=entry_threshold, exposure_cap=exposure_cap)
    raw = strat.predict(df)
    clipped = strat.generate_order_intents(raw)
    return clipped.round().astype(int)


# ----------------------------------------------------------------------
def explain(
    df: pd.DataFrame,
    *,
    timestamp: pd.Timestamp | str | None = None,
    lookback: int = 30,
    entry_threshold: float = 0.01,
    exposure_cap: float = 1.0,
    direction: str | int | None = None,
) -> Dict[str, Any]:
    if df.empty:
        return {"reason": "No price data available for explanation."}

    frame = df.copy()
    if timestamp is not None:
        ts = pd.Timestamp(timestamp)
        frame = frame.loc[:ts]
        if frame.empty:
            raise StrategyError("timestamp requested is before available history")

    strat = _build_strategy(
        frame,
        lookback=lookback,
        entry_threshold=entry_threshold,
        exposure_cap=exposure_cap,
    )
    signals = strat.predict(frame)
    strat.generate_order_intents(signals)

    ctx = strat._last_context  # type: ignore[attr-defined]
    if ctx is None:
        return strat.explain()

    if direction is not None:
        override: float | int | str = direction
        if isinstance(direction, str):
            token = direction.lower()
            override = 1 if token == "long" else -1 if token == "short" else 0
        signal_value = 0.0
        if isinstance(override, (int, float)):
            numeric = float(override)
            if numeric > 0:
                signal_value = 1.0
            elif numeric < 0:
                signal_value = -1.0
        ctx = StrategyContext(
            timestamp=ctx.timestamp,
            price=ctx.price,
            signal=signal_value,
            diagnostics=dict(ctx.diagnostics),
        )

    return strat.explain(ctx)
