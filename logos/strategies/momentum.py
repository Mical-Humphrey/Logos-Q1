from __future__ import annotations

import math
from typing import Any, Dict, Mapping

import pandas as pd

from logos.strategy import (
    StrategyContext,
    StrategyError,
    StrategyPreset,
    ensure_price_frame,
)


class MomentumPreset(StrategyPreset):
    """Momentum preset via simple moving-average crossover."""

    name = "momentum"

    def __init__(
        self,
        *,
        fast: int = 20,
        slow: int = 50,
        exposure_cap: float = 1.0,
    ) -> None:
        self.fast = self._validate_window("fast", fast)
        self.slow = self._validate_window("slow", slow)
        if self.fast >= self.slow:
            raise StrategyError("fast window must be < slow window")
        super().__init__(exposure_cap=exposure_cap)
        self._pending_context: tuple[pd.Timestamp, float, Dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    def params(self) -> Mapping[str, object]:  # type: ignore[override]
        return {
            "fast": self.fast,
            "slow": self.slow,
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
        fast_ma = self._rolling_mean(close, self.fast)
        slow_ma = self._rolling_mean(close, self.slow)

        if fast_ma.isna().all() or slow_ma.isna().all():
            raise StrategyError(f"{self.name}: insufficient data for moving averages")

        raw = (fast_ma > slow_ma).astype(float) - (fast_ma < slow_ma).astype(float)
        signals = raw.reindex(df.index).fillna(0.0)

        price = float(close.iloc[-1])
        ts = df.index[-1]
        diagnostics: Dict[str, Any] = {
            "fast_ma": float(fast_ma.iloc[-1]) if pd.notna(fast_ma.iloc[-1]) else None,
            "slow_ma": float(slow_ma.iloc[-1]) if pd.notna(slow_ma.iloc[-1]) else None,
            "spread": (
                float(fast_ma.iloc[-1] - slow_ma.iloc[-1])
                if pd.notna(fast_ma.iloc[-1]) and pd.notna(slow_ma.iloc[-1])
                else None
            ),
            "fast": self.fast,
            "slow": self.slow,
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

        diagnostics = resolved.diagnostics
        fast_ma = diagnostics.get("fast_ma") if diagnostics else None
        slow_ma = diagnostics.get("slow_ma") if diagnostics else None
        spread = diagnostics.get("spread") if diagnostics else None

        reason = "Moving averages aligned; staying flat."
        if isinstance(fast_ma, (int, float)) and isinstance(slow_ma, (int, float)):
            if fast_ma > slow_ma:
                reason = "Fast MA above slow MA; trend up."
            elif fast_ma < slow_ma:
                reason = "Fast MA below slow MA; trend down."
        elif isinstance(spread, (int, float)) and math.isfinite(spread):
            if spread > 0:
                reason = "Positive MA spread; trend up."
            elif spread < 0:
                reason = "Negative MA spread; trend down."
            else:
                reason = "Zero MA spread; staying flat."
        else:
            reason = "MA spread unavailable; staying flat."

        thresholds = {
            "fast_window": self.fast,
            "slow_window": self.slow,
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
    fast: int = 20,
    slow: int = 50,
    exposure_cap: float = 1.0,
) -> MomentumPreset:
    strat = MomentumPreset(fast=fast, slow=slow, exposure_cap=exposure_cap)
    strat.fit(df)
    return strat


# ----------------------------------------------------------------------
def generate_signals(
    df: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    exposure_cap: float = 1.0,
) -> pd.Series:
    strat = _build_strategy(df, fast=fast, slow=slow, exposure_cap=exposure_cap)
    raw = strat.predict(df)
    clipped = strat.generate_order_intents(raw)
    return clipped.round().astype(int)


# ----------------------------------------------------------------------
def explain(
    df: pd.DataFrame,
    *,
    timestamp: pd.Timestamp | str | None = None,
    fast: int = 20,
    slow: int = 50,
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

    strat = _build_strategy(frame, fast=fast, slow=slow, exposure_cap=exposure_cap)
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
