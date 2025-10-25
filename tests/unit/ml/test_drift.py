from __future__ import annotations

import numpy as np
import pandas as pd

from logos.ml.drift import DriftReport, detect_feature_drift, detect_pnl_drift


def _baseline_frame() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    data = {
        "feature_a": rng.normal(0, 1, 500),
        "feature_b": rng.normal(5, 2, 500),
    }
    return pd.DataFrame(data)


def _shifted_frame() -> pd.DataFrame:
    rng = np.random.default_rng(123)
    data = {
        "feature_a": rng.normal(0.5, 1.2, 500),
        "feature_b": rng.normal(7, 2.5, 500),
    }
    return pd.DataFrame(data)


def test_feature_drift_flags_large_psi() -> None:
    baseline = _baseline_frame()
    current = _shifted_frame()
    report = detect_feature_drift(baseline, current, psi_threshold=0.2)
    assert report.feature_psi
    assert any(report.feature_alerts.values())


def test_pnl_drift_computes_zscore_and_merge() -> None:
    idx = pd.date_range("2024-01-01", periods=120, freq="B")
    baseline = pd.Series(np.sin(np.linspace(0, 6, 120)), index=idx)
    current = pd.Series(0.5 + np.sin(np.linspace(0, 6, 120)), index=idx)

    pnl_report = detect_pnl_drift(baseline, current, z_threshold=1.0)
    assert pnl_report.pnl_zscore is not None
    assert pnl_report.pnl_alert

    feature_report = detect_feature_drift(_baseline_frame(), _baseline_frame())
    combined = feature_report.merge(pnl_report)

    assert combined.pnl_alert
    assert combined.feature_alerts == feature_report.feature_alerts
