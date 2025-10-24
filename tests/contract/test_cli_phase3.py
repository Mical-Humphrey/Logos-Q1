from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

import logos.cli.quickstart as quickstart
import logos.cli.doctor as doctor
import logos.cli.status as status


@pytest.fixture
def tmp_env(tmp_path: Path) -> Path:
    env_path = tmp_path / ".env"
    env_path.write_text("", encoding="utf-8")
    return env_path


def test_quickstart_creates_session(tmp_path: Path, tmp_env: Path) -> None:
    runs_dir = tmp_path / "sessions"
    args = Namespace(
        offline=True,
        lookback=5,
        z_entry=1.5,
        notional=1000.0,
        fee_bps=5.0,
        fixture=None,
        output_dir=runs_dir,
        env_path=tmp_env,
        skip_env=True,
        seed=42,
    )

    exit_code = quickstart.run(args, settings=None)
    assert exit_code == 0

    session_dirs = [path for path in runs_dir.iterdir() if (path / "snapshot.json").exists()]
    assert session_dirs, "quickstart did not create a session directory"
    session_dir = session_dirs[0]

    snapshot_path = session_dir / "snapshot.json"
    metrics_path = session_dir / "artifacts" / "metrics.json"
    session_path = session_dir / "session.md"

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    fills = snapshot.get("fills") or []
    assert fills, "quickstart session should contain at least one fill"
    assert fills[0]["side"].lower() == "buy"

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert any(key.lower() == "sharpe" for key in metrics)

    session_text = session_path.read_text(encoding="utf-8")
    assert "Why we traded" in session_text


def test_doctor_reports_retention_failure(tmp_path: Path, capsys) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LOGOS_RETENTION_ENABLED=1\n", encoding="utf-8")

    args = Namespace(
        env_path=env_path,
        runs_dir=tmp_path,
        logs_dir=tmp_path,
        offline=False,
        json=False,
    )

    exit_code = doctor.run(args, settings=None)
    captured = capsys.readouterr().out
    assert exit_code == 1
    assert "retention" in captured.lower()


def test_status_reports_positions(tmp_path: Path, tmp_env: Path, capsys) -> None:
    runs_dir = tmp_path / "sessions"
    args = Namespace(
        offline=True,
        lookback=5,
        z_entry=1.5,
        notional=1000.0,
        fee_bps=5.0,
        fixture=None,
        output_dir=runs_dir,
        env_path=tmp_env,
        skip_env=False,
        seed=41,
    )
    quickstart.run(args, settings=None)
    session_dir = next(path for path in runs_dir.iterdir() if (path / "snapshot.json").exists())

    status_args = Namespace(
        run_id=None,
        path=session_dir,
        base_dir=runs_dir,
        env_path=tmp_env,
    )
    exit_code = status.run(status_args, settings=None)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Equity:" in output
    assert "Last Signal" in output
    assert "Health" in output
