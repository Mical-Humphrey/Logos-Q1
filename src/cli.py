# src/cli.py
# =============================================================================
# Purpose:
#   Command-line interface (CLI) for the Logos-Q1 project.
#   This is the main user entry point — it lets you run backtests from the
#   terminal, choose which trading strategy to use, and export logs/plots.
#
# Summary:
#   - Loads configuration (dates, symbol, logging level)
#   - Parses user arguments from the command line
#   - Fetches historical data via data_loader.get_prices()
#   - Selects and runs a trading strategy from src/strategies
#   - Backtests the results via src/backtest.engine.run_backtest()
#   - Displays key performance metrics and saves outputs
#
# Design Philosophy:
#   - Keep CLI "thin": it orchestrates modules but doesn’t do computation.
#   - Output artifacts (plots, CSVs) to logs/ for reproducibility.
#   - Avoid side effects elsewhere in the codebase.
# =============================================================================

from __future__ import annotations
import argparse          # Used for parsing command-line arguments
import logging           # Unified logging for console + file
import os                # File path manipulations
import matplotlib.pyplot as plt  # Plotting the equity curve
import pandas as pd       # Type hints / Series handling

# Internal modules: glued here, implemented elsewhere
from .config import load_settings         # Loads .env configuration (dates, defaults)
from .utils import setup_logging, ensure_dirs, parse_params
from .data_loader import get_prices       # Downloads or loads historical price data
from .strategies import STRATEGIES        # Registry mapping names to strategy functions
from .backtest.engine import run_backtest # Core backtesting simulation logic

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Plotting helper
# -----------------------------------------------------------------------------
def _plot_equity(equity: pd.Series, symbol: str, strat: str) -> str:
    """Save the equity curve PNG into logs/ and return its path.
    
    We keep plotting separate from the engine so the engine can remain headless
    (pure computation). That separation makes testing and reuse easier.
    """
    ensure_dirs()  # create logs/ if needed
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
    """Run a full backtest with the chosen strategy and parameters.
    
    Steps:
      1) Load defaults (from .env) + configure logging
      2) Fetch price data (cache-aware)
      3) Generate strategy signals (-1/0/+1)
      4) Run the engine to simulate trades
      5) Print metrics, save trades CSV + equity plot
    """
    s = load_settings()
    setup_logging(s.log_level)
    logger.info("Starting backtest via CLI")

    # CLI args override .env defaults
    symbol = args.symbol or s.symbol
    start  = args.start or s.start
    end    = args.end or s.end

    # Load historical OHLCV data
    df = get_prices(symbol, start, end)

    # Resolve strategy function from registry
    strat_func = STRATEGIES[args.strategy]

    # Parse CLI key=value parameters to a dict (best-effort typing)
    params = parse_params(args.params)

    # Strategy functions are pure: df + params -> signal Series
    signals = strat_func(df, **params) if params else strat_func(df)

    # Hand off to the engine for the actual simulation
    res = run_backtest(prices=df, signals=signals)

    # Console summary
    print("\n=== Metrics ===")
    for k in ["CAGR", "Sharpe", "MaxDD", "WinRate", "Exposure"]:
        print(f"{k:8s}: {res['metrics'].get(k):.4f}")

    # Persist trades + plot for offline inspection
    trades_path = os.path.join("logs", f"trades_{symbol}_{args.strategy}.csv")
    res["trades"].to_csv(trades_path, index=False)
    print(f"Saved trades -> {trades_path}")

    png = _plot_equity(res["equity_curve"], symbol, args.strategy)
    print(f"Saved equity plot -> {png}")


# -----------------------------------------------------------------------------
# CLI entrypoint
# -----------------------------------------------------------------------------
def main() -> None:
    """Parse arguments and dispatch to subcommands.
    
    We start small with a single "backtest" subcommand, but this structure
    makes it trivial to add new commands later (e.g., "optimize", "paper-trade").
    """
    parser = argparse.ArgumentParser(prog="Logos-Q1", description="Quant backtesting CLI")    
    sub = parser.add_subparsers(dest="command")  # allows multiple subcommands

    # backtest: main user entry
    p = sub.add_parser("backtest", help="Run a single-symbol backtest")    
    p.add_argument("--symbol", required=True, help="Ticker (e.g., MSFT)")
    p.add_argument("--strategy", required=True, choices=list(STRATEGIES), help="Strategy name")    
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    p.add_argument("--params", default=None, help="Comma list 'k=v,k=v' for strategy params")    

    args = parser.parse_args()
    if args.command == "backtest":
        cmd_backtest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
