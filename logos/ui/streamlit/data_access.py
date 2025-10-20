"""
Read-only data access layer for Streamlit dashboard.

Provides pure readers using logos.paths with graceful handling of missing files.
Uses mtime-based caching for performance. TODO: migrate to st.cache_data.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from logos import paths


@dataclass
class BacktestMeta:
    """Metadata for a backtest run."""
    path: Path
    run_id: str
    symbol: str
    strategy: str
    timestamp: str
    
    @classmethod
    def from_path(cls, run_path: Path) -> BacktestMeta | None:
        """Create BacktestMeta from a run directory path."""
        if not run_path.is_dir():
            return None
        
        parts = run_path.name.split("_")
        if len(parts) < 3:
            return None
        
        # timestamp_symbol_strategy format
        # Strategy may contain underscores, so join all parts after symbol
        return cls(
            path=run_path,
            run_id=run_path.name,
            timestamp=parts[0] if len(parts) > 0 else "",
            symbol=parts[1] if len(parts) > 1 else "",
            strategy="_".join(parts[2:]) if len(parts) > 2 else "",
        )


@dataclass
class SessionMeta:
    """Metadata for a live trading session."""
    path: Path
    session_id: str
    timestamp: str
    
    @classmethod
    def from_path(cls, session_path: Path) -> SessionMeta | None:
        """Create SessionMeta from a session directory path."""
        if not session_path.is_dir():
            return None
        
        return cls(
            path=session_path,
            session_id=session_path.name,
            timestamp=session_path.name.split("_")[0] if "_" in session_path.name else session_path.name,
        )


# Simple mtime-based cache
_cache: dict[str, tuple[float, Any]] = {}


def _get_cached(key: str, path: Path, loader: callable) -> Any:
    """
    Get cached data if file hasn't changed, otherwise reload.
    
    TODO: Replace with st.cache_data for better integration.
    """
    if not path.exists():
        return None
    
    mtime = path.stat().st_mtime
    if key in _cache:
        cached_mtime, cached_data = _cache[key]
        if cached_mtime == mtime:
            return cached_data
    
    data = loader(path)
    _cache[key] = (mtime, data)
    return data


def list_backtests() -> list[BacktestMeta]:
    """
    List all backtest runs from RUNS_BACKTESTS_DIR.
    
    Returns:
        List of BacktestMeta objects sorted by timestamp (newest first).
    """
    if not paths.RUNS_BACKTESTS_DIR.exists():
        return []
    
    backtests = []
    for run_dir in paths.RUNS_BACKTESTS_DIR.iterdir():
        if run_dir.is_dir() and run_dir.name not in ["live", "lessons", "latest"]:
            meta = BacktestMeta.from_path(run_dir)
            if meta:
                backtests.append(meta)
    
    # Sort by timestamp descending
    backtests.sort(key=lambda x: x.timestamp, reverse=True)
    return backtests


def load_backtest_metrics(run_path: Path) -> dict[str, Any]:
    """
    Load metrics from a backtest run.
    
    Args:
        run_path: Path to the backtest run directory.
    
    Returns:
        Dictionary of metrics, or empty dict if not found.
    """
    metrics_file = run_path / "metrics.json"
    if not metrics_file.exists():
        return {}
    
    def _load(p: Path) -> dict:
        try:
            with open(p, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    return _get_cached(f"metrics_{run_path.name}", metrics_file, _load) or {}


def load_backtest_equity(run_path: Path) -> pd.Series | None:
    """
    Load equity curve from a backtest run.
    
    Args:
        run_path: Path to the backtest run directory.
    
    Returns:
        Pandas Series with equity values, or None if not found.
    """
    equity_file = run_path / "equity.csv"
    if not equity_file.exists():
        return None
    
    def _load(p: Path) -> pd.Series | None:
        try:
            df = pd.read_csv(p, parse_dates=True, index_col=0)
            if "equity" in df.columns:
                return df["equity"]
            elif len(df.columns) == 1:
                return df.iloc[:, 0]
            return None
        except (pd.errors.ParserError, IOError):
            return None
    
    return _get_cached(f"equity_{run_path.name}", equity_file, _load)


def load_backtest_trades(run_path: Path) -> pd.DataFrame | None:
    """
    Load trades from a backtest run.
    
    Args:
        run_path: Path to the backtest run directory.
    
    Returns:
        DataFrame with trade records, or None if not found.
    """
    trades_file = run_path / "trades.csv"
    if not trades_file.exists():
        return None
    
    def _load(p: Path) -> pd.DataFrame | None:
        try:
            return pd.read_csv(p)
        except (pd.errors.ParserError, IOError):
            return None
    
    return _get_cached(f"trades_{run_path.name}", trades_file, _load)


def list_live_sessions() -> list[SessionMeta]:
    """
    List all live trading sessions from RUNS_LIVE_SESSIONS_DIR.
    
    Returns:
        List of SessionMeta objects sorted by timestamp (newest first).
    """
    if not paths.RUNS_LIVE_SESSIONS_DIR.exists():
        return []
    
    sessions = []
    for session_dir in paths.RUNS_LIVE_SESSIONS_DIR.iterdir():
        if session_dir.is_dir():
            meta = SessionMeta.from_path(session_dir)
            if meta:
                sessions.append(meta)
    
    # Sort by timestamp descending
    sessions.sort(key=lambda x: x.timestamp, reverse=True)
    return sessions


def load_live_snapshot(session_path: Path) -> dict[str, Any]:
    """
    Load snapshot data from a live session.
    
    Args:
        session_path: Path to the live session directory.
    
    Returns:
        Dictionary with account, positions, trades, orders.
    """
    result = {
        "account": None,
        "positions": None,
        "trades": None,
        "orders": None,
    }
    
    # Try to load each component
    account_file = session_path / "account.csv"
    if account_file.exists():
        try:
            result["account"] = pd.read_csv(account_file)
        except (pd.errors.ParserError, IOError):
            pass
    
    positions_file = session_path / "positions.csv"
    if positions_file.exists():
        try:
            result["positions"] = pd.read_csv(positions_file)
        except (pd.errors.ParserError, IOError):
            pass
    
    trades_file = session_path / "trades.csv"
    if trades_file.exists():
        try:
            result["trades"] = pd.read_csv(trades_file)
        except (pd.errors.ParserError, IOError):
            pass
    
    orders_file = session_path / "orders.csv"
    if orders_file.exists():
        try:
            result["orders"] = pd.read_csv(orders_file)
        except (pd.errors.ParserError, IOError):
            pass
    
    return result


def tail_log(log_path: Path, n: int = 200, pattern: str | None = None) -> list[str]:
    """
    Read last N lines from a log file, optionally filtering by regex pattern.
    
    Args:
        log_path: Path to the log file.
        n: Number of lines to return from the end.
        pattern: Optional regex pattern to filter lines.
    
    Returns:
        List of log lines (newest first).
    """
    if not log_path.exists():
        return []
    
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        
        # Get last N lines
        lines = lines[-n:]
        
        # Filter by pattern if provided
        if pattern:
            try:
                regex = re.compile(pattern)
                lines = [line for line in lines if regex.search(line)]
            except re.error:
                pass  # Invalid regex, return all lines
        
        # Reverse to show newest first
        return [line.rstrip() for line in reversed(lines)]
    
    except IOError:
        return []
