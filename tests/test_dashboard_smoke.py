from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pytest

from logos.ui.streamlit import app


class _GuardStreamlit:
    def __init__(self) -> None:
        self.calls: Dict[str, int] = {}

    def _record(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def title(self, *args: Any, **kwargs: Any) -> None:
        self._record("title")

    def subheader(self, *args: Any, **kwargs: Any) -> None:
        self._record("subheader")

    def json(self, *args: Any, **kwargs: Any) -> None:
        self._record("json")

    def info(self, *args: Any, **kwargs: Any) -> None:
        self._record("info")

    def warning(self, *args: Any, **kwargs: Any) -> None:
        self._record("warning")

    def error(self, *args: Any, **kwargs: Any) -> None:
        self._record("error")

    def selectbox(self, label: str, options: Any, **kwargs: Any) -> Any:
        self._record("selectbox")
        try:
            return next(iter(options))
        except StopIteration:
            return None


@pytest.fixture
def stub_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    run_dir = tmp_path / "2024-01-01_0000_DEMO_mean_reversion"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics.json").write_text(json.dumps({"Sharpe": 1.2}), encoding="utf-8")
    (run_dir / "provenance.json").write_text(
        json.dumps({"symbol": "DEMO"}), encoding="utf-8"
    )
    monkeypatch.setattr(app, "RUNS_DIR", tmp_path, raising=False)
    return run_dir


def test_dashboard_read_only(monkeypatch: pytest.MonkeyPatch, stub_runs: Path) -> None:
    guard = _GuardStreamlit()
    monkeypatch.setattr(app, "st", guard, raising=False)
    app.render_dashboard()
    # Validate that only read operations were attempted (no writes)
    assert all(
        name in {"title", "selectbox", "subheader", "json", "info"}
        for name in guard.calls
    )


def test_dashboard_handles_missing_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    guard = _GuardStreamlit()
    monkeypatch.setattr(app, "st", guard, raising=False)
    monkeypatch.setattr(app, "RUNS_DIR", tmp_path, raising=False)
    (tmp_path / "2024-01-01_0000_DEMO_mean_reversion").mkdir(
        parents=True, exist_ok=True
    )
    app.render_dashboard()
    assert "info" in guard.calls
