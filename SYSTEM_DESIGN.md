# Logos-Q1 — System Design Document

## 1. Purpose
The **Logos-Q1** system is a modular, python3-based backtesting framework for learning and prototyping quantitative trading strategies.  
It simulates historical trades using statistical signals and outputs detailed performance metrics and visualizations.

The design emphasizes:
- Transparency — all math and logic are visible and explained.
- Simplicity — runs locally without external dependencies.
- Modularity — strategies, costs, and analytics are plug-and-play.

---

## 2. System Architecture Overview

       ┌────────────────────────────┐
       │        User / CLI          │
       │ python3 -m src.cli backtest │
       └──────────────┬─────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │      Config & Logging         │
      │  src/config.py / src/utils.py │
      └──────────────┬───────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │         Data Layer            │
      │     src/data_loader.py        │
      │  (yfinance → cache → DataFrame) │
      └──────────────┬───────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │       Strategy Layer          │
      │   src/strategies/*.py         │
      │ (mean_reversion, momentum,    │
      │  pairs_trading, etc.)         │
      └──────────────┬───────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │       Backtest Engine         │
      │   src/backtest/engine.py      │
      │  - Executes orders            │
      │  - Simulates fills, PnL       │
      │  - Tracks equity, positions   │
      └──────────────┬───────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │   Analytics & Reporting       │
      │  src/backtest/metrics.py      │
      │  src/cli._plot_equity()       │
      └──────────────┬───────────────┘
                      │
                      ▼
      ┌──────────────────────────────┐
      │        Output Layer           │
      │  logs/*.png, logs/*.csv, app.log │
      │  metrics printed to console    │
      └──────────────────────────────┘


---

## 3. Data Flow Summary

| Step | Component  | Input    |  Output   | Description |
|------|------------|----------|-----------|--------------|
|    1 | CLI        | CLI args | Namespace | Parses strategy, symbol, params |
|    2 | Config     | `.env`   | Settings  | Loads defaults for environment |
|    3 | Data Loader | Yahoo Finance API   | `pandas.DataFrame` | Fetches OHLCV or cached CSV |
|    4 | Strategy    | DataFrame | Signals Series | Computes -1, 0, +1 signals |
|    5 | Backtest Engine | Prices + Signals | Equity curve, trades | Simulates positions & PnL |
|    6 | Metrics    | Equity + Trades | Summary dict | Evaluates performance |
|    7 | CLI Output | Results | Logs & PNG | Exports metrics and plots |

---

## 4. Package Structure

Logos-Q1/
├── src/
│ ├── cli.py ← Command-line entrypoint
│ ├── config.py ← Loads environment settings
│ ├── utils.py ← Logging, parsing, directories
│ ├── data_loader.py ← Fetches and caches data
│ ├── strategies/ ← Pluggable strategy modules
│ │ ├── mean_reversion.py
│ │ ├── momentum.py
│ │ └── pairs_trading.py
│ ├── backtest/ ← Simulation and metrics
│ │ ├── engine.py
│ │ ├── metrics.py
│ │ ├── slippage.py
│ │ └── costs.py
│ └── execution/ ← (Future: live trading integration)
├── data/ ← Cached market data
├── logs/ ← Charts, CSVs, and logs
├── MANUAL.md
├── FINANCE.md
├── MATH.md
├── SYSTEM_DESIGN.md
└── REQUIREMENTS.md


---

## 5. Key Design Principles

| Principle | Description |
|------------|-------------|
| **Single Responsibility** | Each module does one thing (e.g., fetching data, generating signals, simulating trades). |
| **Composability** | Strategies and costs are easily interchangeable. |
| **Transparency** | No black-box calculations — all formulas are explicit. |
| **Offline-first** | Once data is downloaded, everything runs locally. |
| **Beginner-Friendly** | Minimal dependencies, heavy documentation, pure python3. |

---

## 6. Extension Roadmap

| Goal | Extension |
|------|------------|
| Live paper trading | Add `execution/live_trader.py` + streaming dashboard |
| Portfolio simulation | Combine multi-symbol signals in engine |
| Parameter optimization | Add grid-search runner |
| Web dashboard | Integrate Plotly Dash or Streamlit for real-time metrics |
| Database logging | Store runs to SQLite or PostgreSQL |
| API integration | Add Binance / Alpaca / Interactive Brokers connectors |

---

## 7. Design Justification

- **CLI-first design:** simplifies experimentation.
- **Modular structure:** isolates logic for teaching & reuse.
- **CSV caching:** avoids unnecessary API calls and keeps reproducibility.
- **Stateless strategies:** each strategy only depends on price data and params — clean separation between signal generation and portfolio mechanics.

---

## 8. Non-Functional Qualities

| Category | Description |
|-----------|-------------|
| **Performance** | Handles 10+ years of daily data for dozens of symbols easily. |
| **Reliability** | Graceful fallbacks for missing cache or data. |
| **Extensibility** | Plug new strategies or cost models with minimal coupling. |
| **Maintainability** | Verbose docstrings and type hints for every function. |
| **Portability** | Works on Linux, macOS, and Windows with python3 3.10+. |

