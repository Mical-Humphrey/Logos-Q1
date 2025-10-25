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


class MeanReversionPreset(StrategyPreset):
    """Mean reversion preset that trades when price deviates from its mean."""

    name = "mean_reversion"

    def __init__(
        self,
        *,
        lookback: int = 20,
        z_entry: float = 2.0,
        exposure_cap: float = 1.0,
    ) -> None:
        self.lookback = self._validate_window("lookback", lookback)
        self.z_entry = self._validate_positive("z_entry", z_entry)
        super().__init__(exposure_cap=exposure_cap)
        self._pending_context: tuple[pd.Timestamp, float, Dict[str, Any]] | None = None

    # ------------------------------------------------------------------
    def params(self) -> Mapping[str, object]:  # type: ignore[override]
        return {
            "lookback": self.lookback,
            "z_entry": self.z_entry,
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
        rolling_mean = self._rolling_mean(close, self.lookback)
        rolling_std = self._rolling_std(close, self.lookback)

        if rolling_std.isna().all():
            raise StrategyError(f"{self.name}: insufficient data to compute z-score")

        z_score = (close - rolling_mean) / rolling_std

        signals = pd.Series(0.0, index=df.index, dtype=float)
        signals.loc[z_score <= -self.z_entry] = 1.0
        signals.loc[z_score >= self.z_entry] = -1.0

        last_mean = rolling_mean.iloc[-1]
        last_std = rolling_std.iloc[-1]
        last_z = z_score.iloc[-1]
        price = float(close.iloc[-1])
        ts = df.index[-1]

        diagnostics: Dict[str, Any] = {
            "mean": float(last_mean) if pd.notna(last_mean) else None,
            "std": float(last_std) if pd.notna(last_std) else None,
            "z_score": float(last_z) if pd.notna(last_z) else None,
            "lookback": self.lookback,
            "z_entry": self.z_entry,
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
        z_value = diagnostics.get("z_score") if diagnostics else None
        reason = "Z-score within neutral band; staying flat."
        if isinstance(z_value, (int, float)) and math.isfinite(z_value):
            if z_value <= -self.z_entry:
                reason = f"Z-score {z_value:.2f} <= -{self.z_entry:.2f}; entering long."
            elif z_value >= self.z_entry:
                reason = f"Z-score {z_value:.2f} >= {self.z_entry:.2f}; entering short."
        else:
            reason = "Latest z-score unavailable; no position taken."

        thresholds = {
            "entry_long": -self.z_entry,
            "entry_short": self.z_entry,
        }

        payload = self._build_payload(
            resolved,
            reason=reason,
            thresholds=thresholds,
        )
        return payload


# ----------------------------------------------------------------------
def _build_strategy(
    df: pd.DataFrame,
    *,
    lookback: int = 20,
    z_entry: float = 2.0,
    exposure_cap: float = 1.0,
) -> MeanReversionPreset:
    strat = MeanReversionPreset(
        lookback=lookback,
        z_entry=z_entry,
        exposure_cap=exposure_cap,
    )
    strat.fit(df)
    return strat


# ----------------------------------------------------------------------
def generate_signals(
    df: pd.DataFrame,
    lookback: int = 20,
    z_entry: float = 2.0,
    exposure_cap: float = 1.0,
) -> pd.Series:
    strat = _build_strategy(
        df, lookback=lookback, z_entry=z_entry, exposure_cap=exposure_cap
    )
    raw = strat.predict(df)
    clipped = strat.generate_order_intents(raw)
    return clipped.round().astype(int)


# ----------------------------------------------------------------------
def explain(
    df: pd.DataFrame,
    *,
    timestamp: pd.Timestamp | str | None = None,
    lookback: int = 20,
    z_entry: float = 2.0,
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
        frame, lookback=lookback, z_entry=z_entry, exposure_cap=exposure_cap
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
