# src/cli.py
# =============================================================================
# Purpose:
#   Command-line interface (CLI) for Logos-Q1.
#   Orchestrates backtests by wiring together configuration, data loading,
#   strategy selection, the simulation engine, and output artifacts.
#
# Summary:
#   - Parses user arguments (symbol, dates, strategy)
#   - NEW: Supports asset classes (equity, crypto, fx) and intervals (1d, 1h, 10m...)
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
import logging
import os
import matplotlib.pyplot as plt
import pandas as pd

from .config import load_settings
from .utils import setup_logging, ensure_dirs, parse_params
from .data_loader import get_prices
from .strategies import STRATEGIES
from .backtest.engine import run_backtest

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Annualization helpers for different asset classes and bar intervals
# -----------------------------------------------------------------------------
# Base "periods per year" for daily bars by asset class:
BASE_PPY = {"equity": 252, "crypto": 365, "fx": 260}

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
    ivl = interval.lower()
    base = BASE_PPY.get(asset, 252)
    mult = BARS_PER_DAY.get(ivl, 1)
    return base * mult


# -----------------------------------------------------------------------------
# Plotting helper
# -----------------------------------------------------------------------------
def _plot_equity(equity: pd.Series, symbol: str, strat: str) -> str:
    """Save the equity curve PNG into logs/ and return its path."""
    ensure_dirs()
    fig, ax = plt.subplots(figsize=(10, 4))
    equity.plot(ax=ax, label="Equity Curve")
    ax.set_title(f"Equity Curve - {symbol} - {strat}")
    ax.set_xlabel("Date"); ax.set_ylabel("Equity")
    ax.legend(loc="best")
    out = os.path.join("logs", f"equity_{symbol}_{strat}.png")
    fig.tight_layout(); fig.savefig(out); plt.close(fig)
    return out


# -----------------------------------------------------------------------------
# Backtest command
# -----------------------------------------------------------------------------
def cmd_backtest(args: argparse.Namespace) -> None:
    """Run a full backtest with asset-aware costs and interval-aware metrics."""
    s = load_settings()
    setup_logging(s.log_level)
    logger.info("Starting backtest via CLI")

    # Resolve CLI or .env defaults
    symbol = args.symbol or s.symbol
    start  = args.start or s.start
    end    = args.end or s.end

    # Load data with requested interval (resampling if yfinance cannot natively)
    df = get_prices(symbol, start, end, interval=args.interval)

    # Strategy function and params
    strat_func = STRATEGIES[args.strategy]
    params = parse_params(args.params)
    signals = strat_func(df, **params) if params else strat_func(df)

    # Compute annualization for metrics (asset + interval)
    ppy = periods_per_year(args.asset_class, args.interval)

    # Run the engine with asset-aware costs
    res = run_backtest(
        prices=df,
        signals=signals,
        dollar_per_trade=args.dollar_per_trade,
        slip_bps=args.slip_bps,
        commission_per_share_rate=args.commission,  # equities
        fee_bps=args.fee_bps,                       # crypto %
        fx_pip_size=args.fx_pip_size,               # fx pip granularity
        asset_class=args.asset_class,
        periods_per_year=ppy,
    )

    # Console summary
    print("\n=== Metrics ===")
    for k in ["CAGR", "Sharpe", "MaxDD", "WinRate", "Exposure"]:
        val = res["metrics"].get(k)
        print(f"{k:8s}: {val:.4f}" if isinstance(val, float) else f"{k:8s}: {val}")

    # Persist artifacts
    trades_path = os.path.join("logs", f"trades_{symbol}_{args.strategy}.csv")
    res["trades"].to_csv(trades_path, index=False)
    print(f"Saved trades -> {trades_path}")

    png = _plot_equity(res["equity_curve"], symbol, args.strategy)
    print(f"Saved equity plot -> {png}")


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    """Parse arguments and dispatch to subcommands."""
    parser = argparse.ArgumentParser(prog="Logos-Q1", description="Quant backtesting CLI")
    sub = parser.add_subparsers(dest="command")

    # backtest: main user entry
    p = sub.add_parser("backtest", help="Run a single-symbol backtest")
    p.add_argument("--symbol", required=True, help="Ticker (e.g., MSFT, BTC-USD, EURUSD=X)")
    p.add_argument("--strategy", required=True, choices=list(STRATEGIES), help="Strategy name")
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")

    # NEW: asset class and interval
    p.add_argument("--asset-class", choices=["equity", "crypto", "fx"], default="equity",
                   help="Affects costs and metric annualization")
    p.add_argument("--interval", default="1d",
                   help="Bar size: 1d, 1h/60m, 30m, 15m, 10m, 5m")

    # Costs & engine knobs
    p.add_argument("--dollar-per-trade", type=float, default=10_000.0, help="Sizing per trade")
    p.add_argument("--slip-bps", type=float, default=1.0, help="Slippage in basis points per order")
    p.add_argument("--commission", type=float, default=0.0035, help="Equity commission $/share")
    p.add_argument("--fee-bps", type=float, default=5.0, help="Crypto maker/taker fee in bps (0.01% = 1 bps)")
    p.add_argument("--fx-pip-size", type=float, default=0.0001, help="FX pip size (0.0001 for EURUSD, 0.01 for USDJPY)")
    p.add_argument("--params", default=None, help="Comma list 'k=v,k=v' for strategy params")

    args = parser.parse_args()
    if args.command == "backtest":
        cmd_backtest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
