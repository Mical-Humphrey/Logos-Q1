from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolatilityEnvelope:
    forecast: float
    lower: float
    upper: float
    confidence: float
    horizon_days: int
    metadata: dict[str, float] | None = None


class VolatilityAdvisor:
    """Provides EWMA-based volatility forecasts for advisory sizing."""

    def __init__(
        self,
        *,
        halflife: int = 30,
        horizon_days: int = 5,
        band_width: float = 1.5,
    ) -> None:
        if halflife <= 0 or horizon_days <= 0:
            raise ValueError("halflife and horizon must be positive")
        self.halflife = halflife
        self.horizon_days = horizon_days
        self.band_width = band_width

    def forecast(self, prices: pd.Series) -> VolatilityEnvelope:
        prices = prices.dropna()
        if prices.size < self.halflife + 5:
            raise ValueError("insufficient observations for volatility forecast")
        returns = prices.pct_change().dropna()
        ew_var = returns.pow(2).ewm(halflife=self.halflife).mean()
        current_sigma = float(np.sqrt(max(ew_var.iloc[-1], 0.0)))

        annualised = current_sigma * np.sqrt(252)
        horizon_adjustment = np.sqrt(self.horizon_days / 252)
        forecast = annualised * horizon_adjustment
        band = forecast * (self.band_width / np.sqrt(max(self.horizon_days, 1)))

        confidence = min(
            returns.iloc[-self.halflife :].size / float(self.halflife), 1.0
        )
        metadata = {
            "halflife": float(self.halflife),
            "band_width": float(self.band_width),
            "annualised_vol": annualised,
        }
        lower = max(forecast - band, 0.0)
        upper = forecast + band
        return VolatilityEnvelope(
            forecast=forecast,
            lower=lower,
            upper=upper,
            confidence=confidence,
            horizon_days=self.horizon_days,
            metadata=metadata,
        )

    @staticmethod
    def promote(
        envelope: VolatilityEnvelope, *, approved_by: str
    ) -> VolatilityEnvelope:
        if not approved_by:
            raise ValueError("approved_by must be non-empty")
        meta = dict(envelope.metadata or {})
        meta["approved_by"] = approved_by
        return VolatilityEnvelope(
            forecast=envelope.forecast,
            lower=envelope.lower,
            upper=envelope.upper,
            confidence=envelope.confidence,
            horizon_days=envelope.horizon_days,
            metadata=meta,
        )
