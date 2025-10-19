# Overview
“Quantitative Trading Backtesting System (python3, Pandas, Yahoo Finance API)”

What it is:
A quantitative trading research environment — specifically, a backtesting engine that simulates trading strategies on historical price data (like MSFT or AAPL). It lets you test “what if” scenarios — what would have happened if you traded using a given rule (like mean reversion or momentum).

# Logos-Q1
Quantitative Trader backtesting 
Minimal, beginner-friendly solo quant dev project. Pulls equities data from Yahoo Finance (yfinance),
runs pluggable strategies, and backtests with simple costs and slippage.

## Notes for maintainers
- This README intentionally stays short; the Word document you are reading is the canonical maintainer’s guide.
- The code favors clarity over micro-optimizations so new contributors can modify safely.

## Features
- Data: Yahoo Finance daily bars with basic on-disk cache in `data/`
- Strategies: Mean Reversion (z-score), Momentum (SMA crossover)
- Backtester: vectorized daily simulation, simple slippage and commissions
- Metrics: CAGR, Sharpe, Max Drawdown, Win Rate, Exposure
- CLI: one command to run a backtest and save results/plots into `logs/`

## Quickstart
```bash
python3 -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt


# Example: mean reversion on MSFT for 2023-2025
python3 -m src.cli backtest \
--symbol MSFT \
--strategy mean_reversion \
--start 2023-01-01 \
--end 2025-01-01 \
--params "lookback=20,z_entry=2.0"


# Example: momentum crossover
python3 -m src.cli backtest \
--symbol AAPL \
--strategy momentum \
--start 2022-01-01 \
--end 2025-01-01 \
--params "fast=20,slow=50"
