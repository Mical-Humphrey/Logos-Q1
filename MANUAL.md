# Logos-Q1 — User Manual

## Overview
**Logos-Q1** is a self-contained **quantitative trading backtesting system** built in python3.

It teaches you how to:
- Pull market data (`yfinance`)
- Run algorithmic trading strategies (mean reversion, momentum, pairs)
- Backtest performance with commissions & slippage
- Visualize results
- Learn the math and finance behind it

---

## 🧰 Setup
    ```bash
    git clone https://github.com/you/Logos-Q1
    cd Logos-Q1
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

=============================================

Example 1 — Mean Reversion
    python3 -m src.cli backtest --symbol MSFT \
    --strategy mean_reversion \
    --start 2023-01-01 --end 2025-01-01 \
    --params "lookback=20,z_entry=2.0"

    Uses 20-day rolling z-score of closing prices.
    Buys when price is 2 std dev below mean, sells when above.

    Output:
    === Metrics ===
    CAGR    : 0.0453
    Sharpe  : 1.27
    MaxDD   : -0.1021
    WinRate : 0.5312
    Exposure: 0.72
    Saved equity plot -> logs/equity_MSFT_mean_reversion.png

=============================================

Example 2 — Momentum
    python3 -m src.cli backtest --symbol AAPL \
    --strategy momentum \
    --start 2022-01-01 --end 2025-01-01 \
    --params "fast=20,slow=50"

    Long when short-term SMA > long-term SMA.
    Short when short-term SMA < long-term SMA.

=============================================

Example 3 — Pairs Trading
    (You must manually fetch two symbols first.)

    import yfinance as yf, pandas as pd
    from src.strategies import pairs_trading
    data = yf.download(["MSFT", "AAPL"], start="2023-01-01", end="2025-01-01")["Close"]
    signals = pairs_trading.generate_signals(data, "MSFT", "AAPL", lookback=30)
    signals.tail()

    Long MSFT / Short AAPL when spread z-score ≤ -2
    Reverse when z-score ≥ +2
    Flat when z-score near 0

=============================================

📊 Outputs and Logs
    logs/equity_*.png — equity curve chart
    logs/trades_*.csv — all trade events
    logs/app.log — run logs

How to Interpret Results
    Metric	Meaning
    CAGR	Compound annual growth rate — long-term return speed
    Sharpe	Risk-adjusted return; >1 is decent, >2 is strong
    MaxDD	Maximum drawdown; biggest peak-to-trough loss
    WinRate	% of trades profitable
    Exposure	% of time the system held open positions

=============================================

Adding Your Own Strategy
    Add a new file in src/strategies/, e.g. my_strategy.py
    Define generate_signals(df: pd.DataFrame, **params) -> pd.Series
    Add it to STRATEGIES in src/strategies/__init__.py
    Run from CLI:
    python3 -m src.cli backtest --symbol XYZ --strategy my_strategy --start ... --end ...

Debugging Tips
    Delete cache in data/ to re-download.
    Use print(df.head()) to inspect raw data.
    Increase verbosity: set LOG_LEVEL=DEBUG in .env
