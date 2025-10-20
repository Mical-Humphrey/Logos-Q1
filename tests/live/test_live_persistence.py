from __future__ import annotations

import datetime as dt
import hashlib
import json

import pandas as pd
import pytest

from logos.live.persistence import (
    prepare_seeded_run_paths,
    run_id_from_seed,
    write_equity_and_metrics,
    write_snapshot,
)


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_id_is_seed_deterministic() -> None:
    assert run_id_from_seed(7, "Paper Demo") == "0007-Paper-Demo"
    assert run_id_from_seed(42, "") == "0042"


def test_snapshot_serialisation_is_stable(tmp_path) -> None:
    paths = prepare_seeded_run_paths(7, "Paper Demo", base_dir=tmp_path)

    account = {"cash": 100_000.0, "equity": 101_250.0}
    positions = {
        "AAPL": {"qty": 10, "avg_price": 150.0},
        "MSFT": {"qty": -5, "avg_price": 250.0},
    }
    open_orders = [
        {"id": "O-1", "symbol": "AAPL", "side": "buy", "qty": 5},
    ]
    fills = [
        {
            "id": "F-1",
            "symbol": "AAPL",
            "qty": 5,
            "pnl": 125.0,
            "ts": dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc),
        },
    ]
    config = {"strategy": "mean_reversion", "interval": "1m"}
    clock = dt.datetime(2024, 1, 1, 9, 30, tzinfo=dt.timezone.utc)

    first_path = write_snapshot(
        paths,
        account=account,
        positions=positions,
        open_orders=open_orders,
        fills=fills,
        config=config,
        clock=clock,
    )
    first_digest = _sha256(first_path)

    second_path = write_snapshot(
        paths,
        account=account,
        positions=positions,
        open_orders=open_orders,
        fills=fills,
        config=config,
        clock=clock,
    )
    assert first_path == second_path
    assert first_digest == _sha256(second_path)

    payload = json.loads(second_path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "0007-Paper-Demo"
    assert payload["seed"] == 7
    assert payload["account"]["cash"] == pytest.approx(100_000.0)
    assert payload["positions"]["AAPL"]["avg_price"] == pytest.approx(150.0)
    assert payload["open_orders"][0]["id"] == "O-1"
    assert payload["fills"][0]["ts"] == "2024-01-01T00:00:00+00:00"
    assert payload["config"]["interval"] == "1m"


def test_artifacts_and_metrics_are_deterministic(tmp_path) -> None:
    paths = prepare_seeded_run_paths(9, "Paper Demo", base_dir=tmp_path)

    equity_curve = [
        {
            "ts": dt.datetime(2024, 1, 1, 9, 30, tzinfo=dt.timezone.utc),
            "equity": 100_000.0,
            "cash": 100_000.0,
        },
        {
            "ts": dt.datetime(2024, 1, 1, 9, 31, tzinfo=dt.timezone.utc),
            "equity": 100_500.0,
            "cash": 99_500.0,
        },
        {
            "ts": dt.datetime(2024, 1, 1, 9, 32, tzinfo=dt.timezone.utc),
            "equity": 101_000.0,
            "cash": 99_000.0,
        },
    ]
    trades = [
        {"id": "F-1", "pnl": 500.0, "notional": 10_000.0},
        {"id": "F-2", "pnl": -200.0, "notional": 10_000.0},
    ]
    exposures = [0.0, 1.0, 1.0, 0.0]

    equity_csv, metrics_json = write_equity_and_metrics(
        paths,
        equity_curve=equity_curve,
        trades=trades,
        exposures=exposures,
    )
    first_equity_digest = _sha256(equity_csv)
    first_metrics_digest = _sha256(metrics_json)

    equity_csv, metrics_json = write_equity_and_metrics(
        paths,
        equity_curve=equity_curve,
        trades=trades,
        exposures=exposures,
    )
    assert first_equity_digest == _sha256(equity_csv)
    assert first_metrics_digest == _sha256(metrics_json)

    df = pd.read_csv(equity_csv)
    assert list(df.columns) == ["ts", "equity", "cash"]
    assert df.shape == (3, 3)
    assert float(df.iloc[-1]["equity"]) == pytest.approx(101_000.0, rel=1e-6)

    metrics_payload = json.loads(metrics_json.read_text(encoding="utf-8"))
    assert metrics_payload["run_id"] == "0009-Paper-Demo"
    assert metrics_payload["seed"] == 9
    assert metrics_payload["pnl"] == pytest.approx(1_000.0)
    assert metrics_payload["start_equity"] == pytest.approx(100_000.0)
    assert metrics_payload["end_equity"] == pytest.approx(101_000.0)
    assert metrics_payload["max_drawdown"] == pytest.approx(0.0)
    assert metrics_payload["hit_rate"] == pytest.approx(0.5)
    assert metrics_payload["turnover"] == pytest.approx(0.2)
    assert metrics_payload["exposure"] == pytest.approx(0.5)
    returns = pd.Series([row["equity"] for row in equity_curve]).pct_change().dropna()
    expected_sharpe = float(returns.mean() / returns.std(ddof=0) * (252**0.5))
    assert metrics_payload["sharpe"] == pytest.approx(expected_sharpe)
