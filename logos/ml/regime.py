from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeReport:
    """Summary of the detected market regime.

    The report is advisory only; downstream code must secure human approval
    before acting on `trend_state` or other recommendations.
    """

    trend_state: str
    vol_state: str
    trend_score: float
    vol_score: float
    confidence: float
    metadata: Dict[str, float | str] = field(default_factory=dict)
    promoted: bool = False
    approved_by: Optional[str] = None


class RegimeAdvisor:
    """Calculates simple trend/volatility regimes for offline analysis."""

    def __init__(
        self,
        *,
        trend_lookback: int = 63,
        vol_lookback: int = 21,
        trend_threshold: float = 0.6,
        vol_threshold: float = 1.25,
    ) -> None:
        if trend_lookback <= 1 or vol_lookback <= 1:
            raise ValueError("lookbacks must exceed one observation")
        self.trend_lookback = trend_lookback
        self.vol_lookback = vol_lookback
        self.trend_threshold = trend_threshold
        self.vol_threshold = vol_threshold

    def analyze(self, prices: pd.Series) -> RegimeReport:
        prices = prices.dropna()
        if prices.size < max(self.trend_lookback, self.vol_lookback) + 5:
            raise ValueError("insufficient observations for regime analysis")

        returns = prices.pct_change().dropna()
        volatility = returns.rolling(self.vol_lookback).std(ddof=0)
        trend = returns.rolling(self.trend_lookback).mean()

        trend_score = _sharpe_like(trend.iloc[-1], returns.rolling(self.trend_lookback).std(ddof=0).iloc[-1])
        vol_recent = volatility.iloc[-1]
        vol_long = returns.rolling(self.trend_lookback).std(ddof=0).iloc[-1]
        vol_score = _ratio(vol_recent, vol_long)

        trend_state = _classify_trend(trend_score, self.trend_threshold)
        vol_state = _classify_vol(vol_score, self.vol_threshold)

        effective_samples = min(returns.iloc[-self.trend_lookback :].size, returns.iloc[-self.vol_lookback :].size)
        confidence = min(effective_samples / float(max(self.trend_lookback, self.vol_lookback)), 1.0)

        metadata: Dict[str, float | str] = {
            "trend_lookback": float(self.trend_lookback),
            "vol_lookback": float(self.vol_lookback),
            "trend_threshold": float(self.trend_threshold),
            "vol_threshold": float(self.vol_threshold),
            "vol_recent": float(vol_recent),
            "vol_long": float(vol_long),
        }
        return RegimeReport(
            trend_state=trend_state,
            vol_state=vol_state,
            trend_score=float(trend_score),
            vol_score=float(vol_score),
            confidence=float(confidence),
            metadata=metadata,
        )

    @staticmethod
    def promote(report: RegimeReport, *, approved_by: str) -> RegimeReport:
        if not approved_by:
            raise ValueError("approved_by must be provided for promotion")
        augmented_meta = dict(report.metadata)
        augmented_meta.setdefault("promotion_notes", "approved")
        augmented_meta["approved_by"] = approved_by
        return replace(report, promoted=True, approved_by=approved_by, metadata=augmented_meta)


def classify_regime(prices: pd.Series, **kwargs: float) -> RegimeReport:
    """Convenience wrapper for :class:`RegimeAdvisor`."""

    advisor = RegimeAdvisor(**kwargs)
    return advisor.analyze(prices)


def _sharpe_like(mean_return: float, vol: float) -> float:
    if not np.isfinite(vol) or vol <= 1e-12:
        return 0.0
    return mean_return / vol


def _ratio(numerator: float, denominator: float) -> float:
    if not np.isfinite(denominator) or abs(denominator) <= 1e-12:
        return 0.0
    return numerator / denominator


def _classify_trend(score: float, threshold: float) -> str:
    if score >= threshold:
        return "bull"
    if score <= -threshold:
        return "bear"
    return "sideways"


def _classify_vol(score: float, threshold: float) -> str:
    if score >= threshold:
        return "high"
    if score <= 1 / max(threshold, 1e-6):
        return "low"
    return "normal"
