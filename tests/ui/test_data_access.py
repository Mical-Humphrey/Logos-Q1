"""
Tests for data_access module using fixtures.

Ensures graceful handling of missing files and correct data loading.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from logos.ui.streamlit import data_access


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def backtests_dir(fixtures_dir):
    """Return path to backtest fixtures."""
    return fixtures_dir / "backtests"


@pytest.fixture
def live_dir(fixtures_dir):
    """Return path to live session fixtures."""
    return fixtures_dir / "live"


def test_list_backtests_with_fixtures(backtests_dir, monkeypatch):
    """Test listing backtests from fixture directory."""
    # Temporarily replace RUNS_BACKTESTS_DIR
    from logos import paths
    monkeypatch.setattr(paths, "RUNS_BACKTESTS_DIR", backtests_dir)
    
    backtests = data_access.list_backtests()
    
    assert len(backtests) == 2
    assert all(bt.path.exists() for bt in backtests)
    assert all(bt.symbol and bt.strategy for bt in backtests)


def test_list_backtests_missing_dir(monkeypatch):
    """Test listing backtests when directory doesn't exist."""
    from logos import paths
    monkeypatch.setattr(paths, "RUNS_BACKTESTS_DIR", Path("/nonexistent"))
    
    backtests = data_access.list_backtests()
    
    assert backtests == []


def test_load_backtest_metrics(backtests_dir):
    """Test loading metrics from a backtest."""
    run_path = backtests_dir / "2024-01-15_MSFT_mean_reversion"
    
    metrics = data_access.load_backtest_metrics(run_path)
    
    assert metrics is not None
    assert "cagr" in metrics
    assert "sharpe_ratio" in metrics
    assert metrics["cagr"] == 0.15


def test_load_backtest_metrics_missing_file(backtests_dir):
    """Test loading metrics when file doesn't exist."""
    run_path = backtests_dir / "nonexistent_run"
    
    metrics = data_access.load_backtest_metrics(run_path)
    
    assert metrics == {}


def test_load_backtest_equity(backtests_dir):
    """Test loading equity curve from a backtest."""
    run_path = backtests_dir / "2024-01-15_MSFT_mean_reversion"
    
    equity = data_access.load_backtest_equity(run_path)
    
    assert equity is not None
    assert len(equity) > 0
    assert equity.iloc[0] == 10000.00


def test_load_backtest_equity_missing_file(backtests_dir):
    """Test loading equity when file doesn't exist."""
    run_path = backtests_dir / "nonexistent_run"
    
    equity = data_access.load_backtest_equity(run_path)
    
    assert equity is None


def test_load_backtest_trades(backtests_dir):
    """Test loading trades from a backtest."""
    run_path = backtests_dir / "2024-01-15_MSFT_mean_reversion"
    
    trades = data_access.load_backtest_trades(run_path)
    
    assert trades is not None
    assert len(trades) > 0
    assert "symbol" in trades.columns
    assert "side" in trades.columns


def test_load_backtest_trades_missing_file(backtests_dir):
    """Test loading trades when file doesn't exist."""
    run_path = backtests_dir / "nonexistent_run"
    
    trades = data_access.load_backtest_trades(run_path)
    
    assert trades is None


def test_list_live_sessions_with_fixtures(live_dir, monkeypatch):
    """Test listing live sessions from fixture directory."""
    from logos import paths
    monkeypatch.setattr(paths, "RUNS_LIVE_SESSIONS_DIR", live_dir / "sessions")
    
    sessions = data_access.list_live_sessions()
    
    assert len(sessions) == 1
    assert sessions[0].session_id == "2024-01-20_session1"


def test_list_live_sessions_missing_dir(monkeypatch):
    """Test listing live sessions when directory doesn't exist."""
    from logos import paths
    monkeypatch.setattr(paths, "RUNS_LIVE_SESSIONS_DIR", Path("/nonexistent"))
    
    sessions = data_access.list_live_sessions()
    
    assert sessions == []


def test_load_live_snapshot(live_dir):
    """Test loading live session snapshot."""
    session_path = live_dir / "sessions" / "2024-01-20_session1"
    
    snapshot = data_access.load_live_snapshot(session_path)
    
    assert snapshot is not None
    assert "account" in snapshot
    assert "positions" in snapshot
    assert "trades" in snapshot
    assert snapshot["account"] is not None
    assert len(snapshot["account"]) > 0


def test_load_live_snapshot_missing_dir():
    """Test loading snapshot when directory doesn't exist."""
    session_path = Path("/nonexistent/session")
    
    snapshot = data_access.load_live_snapshot(session_path)
    
    assert snapshot is not None
    assert snapshot["account"] is None
    assert snapshot["positions"] is None


def test_tail_log(fixtures_dir):
    """Test tailing a log file."""
    log_file = fixtures_dir / "live.log"
    
    lines = data_access.tail_log(log_file, n=10)
    
    assert len(lines) > 0
    assert "Starting live trading session" in lines[-1]


def test_tail_log_with_pattern(fixtures_dir):
    """Test tailing log with regex filter."""
    log_file = fixtures_dir / "live.log"
    
    lines = data_access.tail_log(log_file, n=10, pattern="filled")
    
    assert len(lines) > 0
    assert all("filled" in line.lower() for line in lines)


def test_tail_log_missing_file():
    """Test tailing when log file doesn't exist."""
    log_file = Path("/nonexistent.log")
    
    lines = data_access.tail_log(log_file)
    
    assert lines == []


def test_backtest_meta_from_path(backtests_dir):
    """Test creating BacktestMeta from path."""
    run_path = backtests_dir / "2024-01-15_MSFT_mean_reversion"
    
    meta = data_access.BacktestMeta.from_path(run_path)
    
    assert meta is not None
    assert meta.symbol == "MSFT"
    assert meta.strategy == "mean_reversion"
    assert meta.timestamp == "2024-01-15"


def test_backtest_meta_invalid_path():
    """Test creating BacktestMeta from invalid path."""
    run_path = Path("/nonexistent")
    
    meta = data_access.BacktestMeta.from_path(run_path)
    
    assert meta is None


def test_session_meta_from_path(live_dir):
    """Test creating SessionMeta from path."""
    session_path = live_dir / "sessions" / "2024-01-20_session1"
    
    meta = data_access.SessionMeta.from_path(session_path)
    
    assert meta is not None
    assert meta.session_id == "2024-01-20_session1"
    assert meta.timestamp == "2024-01-20"
