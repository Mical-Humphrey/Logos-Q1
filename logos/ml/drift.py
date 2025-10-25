from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DriftReport:
    feature_psi: Dict[str, float] = field(default_factory=dict)
    feature_alerts: Dict[str, bool] = field(default_factory=dict)
    pnl_zscore: Optional[float] = None
    pnl_alert: bool = False
    metadata: Dict[str, float | str] = field(default_factory=dict)

    def merge(self, other: DriftReport) -> DriftReport:
        merged_meta = {**self.metadata, **other.metadata}
        return DriftReport(
            feature_psi={**self.feature_psi, **other.feature_psi},
            feature_alerts={**self.feature_alerts, **other.feature_alerts},
            pnl_zscore=other.pnl_zscore if other.pnl_zscore is not None else self.pnl_zscore,
            pnl_alert=self.pnl_alert or other.pnl_alert,
            metadata=merged_meta,
        )


def detect_feature_drift(
    baseline: pd.DataFrame,
    current: pd.DataFrame,
    *,
    psi_threshold: float = 0.25,
    bins: int = 10,
) -> DriftReport:
    """Compute per-feature Population Stability Index."""

    shared_cols = [col for col in baseline.columns if col in current.columns]
    psi_scores: Dict[str, float] = {}
    alerts: Dict[str, bool] = {}
    for column in shared_cols:
        base_series = baseline[column].dropna()
        cur_series = current[column].dropna()
        if base_series.empty or cur_series.empty:
            continue
        psi = _population_stability_index(base_series, cur_series, bins=bins)
        psi_scores[column] = psi
        alerts[column] = psi >= psi_threshold
    metadata = {
        "psi_threshold": float(psi_threshold),
        "bins": float(bins),
    }
    return DriftReport(feature_psi=psi_scores, feature_alerts=alerts, metadata=metadata)


def detect_pnl_drift(
    baseline: pd.Series,
    current: pd.Series,
    *,
    z_threshold: float = 2.0,
) -> DriftReport:
    baseline = baseline.dropna()
    current = current.dropna()
    if baseline.empty or current.empty:
        return DriftReport(metadata={"pnl_warning": "insufficient data"})
    diff = current.mean() - baseline.mean()
    pooled_std = np.sqrt(
        (baseline.var(ddof=1) + current.var(ddof=1)) / 2.0
    )
    if not np.isfinite(pooled_std) or pooled_std <= 1e-12:
        zscore = 0.0
    else:
        zscore = diff / (pooled_std / np.sqrt(len(current)))
    metadata = {
        "z_threshold": float(z_threshold),
        "baseline_mean": float(baseline.mean()),
        "current_mean": float(current.mean()),
    }
    return DriftReport(
        pnl_zscore=float(zscore),
        pnl_alert=abs(zscore) >= z_threshold,
        metadata=metadata,
    )


def _population_stability_index(
    baseline: pd.Series,
    current: pd.Series,
    *,
    bins: int,
) -> float:
    quantiles = np.linspace(0.0, 1.0, bins + 1)
    cuts = baseline.quantile(quantiles).to_numpy()
    cuts[0] = -np.inf
    cuts[-1] = np.inf
    base_hist, _ = np.histogram(baseline, bins=cuts)
    cur_hist, _ = np.histogram(current, bins=cuts)
    base_probs = _normalise_hist(base_hist)
    cur_probs = _normalise_hist(cur_hist)
    psi = np.sum((cur_probs - base_probs) * np.log(cur_probs / base_probs))
    if not np.isfinite(psi):
        return 0.0
    return float(psi)


def _normalise_hist(hist: np.ndarray) -> np.ndarray:
    hist = hist.astype(float)
    hist += 1e-6  # guards against empty buckets
    total = hist.sum()
    if total <= 0:
        return np.full_like(hist, 1.0 / hist.size)
    return hist / total
