# src/cli.py
# =============================================================================
# Purpose:
#   Command-line interface (CLI) for Logos-Q1.
#   Orchestrates backtests by wiring together configuration, data loading,
#   strategy selection, the simulation engine, and output artifacts.
#
# Summary:
#   - Parses user arguments (symbol, dates, strategy)
#   - NEW: Supports asset classes (equity, crypto, forex) and intervals (1d, 1h, 10m...)
#   - Loads historical data via data_loader.get_prices()
#   - Runs a strategy to generate signals
#   - Calls backtest.engine.run_backtest() with asset-aware costs & annualization
#   - Prints key metrics and saves equity/trades artifacts
#
# Design Philosophy:
#   - Keep CLI thin; business logic lives in modules.
#   - All knobs are arguments; no hidden logic here.
# =============================================================================

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Sequence

import matplotlib.pyplot as plt
import pandas as pd

from .config import Settings, load_settings
from .utils import ensure_dirs, parse_params, setup_logging
from .data_loader import get_prices
from .strategies import STRATEGIES
from .backtest.engine import run_backtest

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Annualization helpers for different asset classes and bar intervals
# -----------------------------------------------------------------------------
# Base "periods per year" for daily bars by asset class:
BASE_PPY = {"equity": 252, "crypto": 365, "forex": 260}

# How many bars per day for common intraday intervals
BARS_PER_DAY = {
    "1d": 1,
    "60m": 24,
    "1h": 24,
    "30m": 48,
    "15m": 96,
    "10m": 144,
    "5m": 288,
}

def periods_per_year(asset_class: str, interval: str) -> int:
    """Return the appropriate annualization factor for Sharpe/CAGR."""
    asset = asset_class.lower()
    if asset == "fx":
        asset = "forex"
    ivl = interval.lower()
    base = BASE_PPY.get(asset, 252)
    mult = BARS_PER_DAY.get(ivl, 1)
    return base * mult


# -----------------------------------------------------------------------------
# Plotting helper
# -----------------------------------------------------------------------------
def _plot_equity(equity: pd.Series, output_path: str) -> str:
    """Save the equity curve PNG into the provided run directory."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 4))
    equity.plot(ax=ax, label="Equity Curve")
    ax.set_title("Equity Curve")
    ax.set_xlabel("Date"); ax.set_ylabel("Equity")
    ax.legend(loc="best")
    fig.tight_layout(); fig.savefig(output_path); plt.close(fig)
    return output_path


def _create_run_dir(symbol: str, strategy: str) -> str:
    """Create a timestamped run directory and return its path."""
    ensure_dirs()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    safe_symbol = symbol.replace("/", "-").replace("=", "-")
    dirname = f"{ts}_{safe_symbol}_{strategy}"
    run_dir = os.path.join("runs", dirname)
    os.makedirs(run_dir, exist_ok=True)
    os.makedirs(os.path.join(run_dir, "logs"), exist_ok=True)

    latest = os.path.join("runs", "latest")
    if os.path.lexists(latest):
        if os.path.islink(latest):
            os.unlink(latest)
        elif os.path.isdir(latest):
            shutil.rmtree(latest)
        else:
            os.remove(latest)
    try:
        os.symlink(os.path.basename(run_dir), latest)
    except OSError as err:
        logger.warning("Could not update latest symlink: %s", err)

    return run_dir


def _write_config_yaml(path: str, config: dict[str, object]) -> None:
    """Persist a minimal YAML representation of the effective configuration."""
    lines = ["# Effective run configuration"]
    for key, value in config.items():
        lines.append(f"{key}: {value}")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _write_metrics_json(path: str, metrics: dict[str, object]) -> None:
    serializable = {k: (float(v) if hasattr(v, "__float__") else v) for k, v in metrics.items()}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(serializable, handle, indent=2)


# -----------------------------------------------------------------------------
# Backtest command
# -----------------------------------------------------------------------------
def cmd_backtest(args: argparse.Namespace, settings: Settings | None = None) -> None:
    """Run a full backtest with asset-aware costs and interval-aware metrics."""
    s = settings or load_settings()
    setup_logging(s.log_level)
    logger.info("Starting backtest via CLI")

    # Resolve CLI or .env defaults
    symbol = args.symbol or s.symbol
    start = args.start or s.start
    end = args.end or s.end
    asset_class = (args.asset_class or s.asset_class).lower()

    run_dir = _create_run_dir(symbol, args.strategy)
    run_log_path = os.path.join(run_dir, "logs", "run.log")
    run_handler = logging.FileHandler(run_log_path, mode="a")
    run_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logging.getLogger().addHandler(run_handler)

    try:
        if args.paper:
            logger.info("Paper trading mode enabled: no live broker interactions will be attempted")

        # Load data with requested interval (resampling if yfinance cannot natively)
        df = get_prices(symbol, start, end, interval=args.interval, asset_class=asset_class)

        # Strategy function and params
        strat_func = STRATEGIES[args.strategy]
        params = parse_params(args.params)
        signals = strat_func(df, **params) if params else strat_func(df)

        # Compute annualization for metrics (asset + interval)
        ppy = periods_per_year(asset_class, args.interval)

        # Run the engine with asset-aware costs
        res = run_backtest(
            prices=df,
            signals=signals,
            dollar_per_trade=args.dollar_per_trade,
            slip_bps=args.slip_bps,
            commission_per_share_rate=args.commission,  # equities
            fee_bps=args.fee_bps,  # crypto %
            fx_pip_size=args.fx_pip_size,  # fx pip granularity
            asset_class=asset_class,
            periods_per_year=ppy,
        )

        # Console summary
        print("\n=== Metrics ===")
        for k in ["CAGR", "Sharpe", "MaxDD", "WinRate", "Exposure"]:
            val = res["metrics"].get(k)
            print(f"{k:8s}: {val:.4f}" if isinstance(val, float) else f"{k:8s}: {val}")

        config_payload = {
            "symbol": symbol,
            "strategy": args.strategy,
            "start": start,
            "end": end,
            "asset_class": asset_class,
            "interval": args.interval,
            "dollar_per_trade": args.dollar_per_trade,
            "slip_bps": args.slip_bps,
            "commission_per_share": args.commission,
            "fee_bps": args.fee_bps,
            "fx_pip_size": args.fx_pip_size,
            "params": params or {},
            "paper_mode": bool(args.paper),
        }
        _write_config_yaml(os.path.join(run_dir, "config.yaml"), config_payload)
        _write_metrics_json(os.path.join(run_dir, "metrics.json"), res["metrics"])

        trades_path = os.path.join(run_dir, "trades.csv")
        res["trades"].to_csv(trades_path, index=False)
        print(f"Saved trades -> {trades_path}")

        png_path = os.path.join(run_dir, "equity.png")
        _plot_equity(res["equity_curve"], png_path)
        print(f"Saved equity plot -> {png_path}")
        print(f"Run artifacts -> {run_dir}")

    finally:
        logging.getLogger().removeHandler(run_handler)
        run_handler.close()


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------
def build_parser(settings: Settings) -> argparse.ArgumentParser:
    """Construct the CLI parser so shim modules can reuse it."""
    parser = argparse.ArgumentParser(prog="Logos-Q1", description="Quant backtesting CLI")
    sub = parser.add_subparsers(dest="command")

    # backtest: main user entry
    p = sub.add_parser("backtest", help="Run a single-symbol backtest")
    p.add_argument("--symbol", required=True, help="Ticker (e.g., MSFT, BTC-USD, EURUSD=X)")
    p.add_argument("--strategy", required=True, choices=list(STRATEGIES), help="Strategy name")
    p.add_argument("--start", default=None, help="Start date YYYY-MM-DD (defaults to .env START_DATE)")
    p.add_argument("--end", default=None, help="End date YYYY-MM-DD (defaults to .env END_DATE)")

    # NEW: asset class and interval
    p.add_argument("--asset-class", choices=["equity", "crypto", "forex"],
                   default=settings.asset_class,
                   help="Affects costs and metric annualization")
    p.add_argument("--interval", default="1d",
                   help="Bar size: 1d, 1h/60m, 30m, 15m, 10m, 5m")

    # Costs & engine knobs
    p.add_argument("--dollar-per-trade", type=float, default=10_000.0, help="Sizing per trade")
    p.add_argument("--slip-bps", type=float, default=settings.slippage_bps,
                   help="Slippage in basis points per order")
    p.add_argument("--commission", type=float, default=settings.commission_per_share,
                   help="Equity commission $/share")
    p.add_argument("--fee-bps", type=float, default=5.0, help="Crypto maker/taker fee in bps (0.01% = 1 bps)")
    p.add_argument("--fx-pip-size", type=float, default=0.0001, help="FX pip size (0.0001 for EURUSD, 0.01 for USDJPY)")
    p.add_argument("--params", default=None, help="Comma list 'k=v,k=v' for strategy params")
    p.add_argument("--paper", action="store_true", help="Enable paper trading simulation mode")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """Parse arguments and dispatch to subcommands."""
    settings = load_settings()
    parser = build_parser(settings)
    args = parser.parse_args(argv)

    if args.command == "backtest":
        cmd_backtest(args, settings=settings)
    elif args.command is None and argv is None:
        # User invoked bare CLI with no subcommand; show help
        parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
