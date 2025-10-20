# Logos-Q1

> “Learn like a student. Trade like a professional.”

---

## 🔷 Overview
**Logos-Q1** is a **quantitative trading research and execution system** designed for two parallel purposes:

1. **Education** — a readable, well-documented codebase that teaches the core mathematics and logic behind algorithmic trading.
2. **Execution** — a fully modular, pluggable framework that can connect to live markets and trade autonomously as a **solo quant developer** system.

Every line of code in Logos-Q1 is structured to be *understood, extended, and trusted* — making it both a learning laboratory and a professional tool for real-world trading.

---

## ⚙️ Core Features
| Layer | Description |
|--------|--------------|
| **CLI / GUI Interface** | Command-line interface for research; GUI planned for execution and dashboards. |
| **Data Loader** | Pulls equities, crypto, and FX data via Yahoo Finance or live exchange APIs. |
| **Strategy Engine** | Modular strategies (Mean Reversion, Momentum, Pairs Trading) — all plug-and-play. |
| **Backtesting** | Multi-asset backtesting with equity, crypto, and FX cost models. |
| **Execution Simulator** | Models fills, slippage, commissions, and fees with configurable parameters. |
| **Metrics Suite** | Computes Sharpe, CAGR, Max Drawdown, Win Rate, Exposure, and custom ratios. |
| **Educational Math Docs** | Detailed `MATH.html` explaining the quantitative principles behind every function. |
| **Finance Docs** | `FINANCE.md` translates concepts into practical market behavior and case studies. |

---

## 🧠 Philosophy
- **Transparency first.** Every function and line is annotated and explained.
- **Modularity.** Each layer can be replaced — data, strategy, execution, GUI.
- **Education through engineering.** The app is built so that every component *teaches itself* to the reader.
- **Competitive edge.** Designed to be the foundation of a true quant-research and execution workstation.

---

## 📈 Vision Roadmap
| Stage | Focus | Deliverable |
|--------|--------|-------------|
| **Phase 1** | Educational Backtesting (Complete) | CLI backtester with strategy plugins |
| **Phase 2** | Live Execution | Add broker/exchange connectors (CCXT, Alpaca, Interactive Brokers) |
| **Phase 3** | Visual Dashboard | Streamlit-based GUI with live trades, metrics, and logs |
| **Phase 4** | Advanced Research Tools | Portfolio optimization, ML alpha generation, risk modeling |
| **Phase 5** | Deployment | Run as local desktop app or EC2 instance with cloud sync |

---

## 🧩 Example Usage
```bash
# Mean reversion on equities
python -m logos.cli backtest --asset-class equity --symbol MSFT \
  --strategy mean_reversion --start 2023-01-01 --end 2025-01-01 \
  --params "lookback=20,z_entry=2.0"

# Momentum on crypto
python -m logos.cli backtest --asset-class crypto --symbol BTC-USD \
  --strategy momentum --start 2023-01-01 --end 2025-01-01 \
  --interval 1h --params "fast=20,slow=50"


Educational Mode
    Use MATH.html to learn each formula.
    Use FINANCE.md to understand market context.
    Use MANUAL.md for CLI and future GUI workflows.
    Each subsystem (data, strategy, execution) can be studied independently or extended as a course module.

🏗️ Built With
    Python 3.12+
    pandas, numpy, matplotlib
    yfinance
    (Future: Streamlit / CCXT / SQLite / FastAPI)

🕊️ MIT License — Logos-Q1 is open for study, extension, and responsible live trading use.



Command Examples

— Daily equity backtest, paper mode, saves artifacts under runs/<timestamp>_MSFT_mean_reversion/.
    python -m logos.cli backtest --symbol MSFT --strategy mean_reversion --asset-class equity --start 2022-01-01 --end 2024-01-01 --paper

— Crypto hourly momentum test with custom sizing/fees.
    python -m logos.cli backtest --symbol BTC-USD --strategy momentum --asset-class crypto --interval 1h --dollar-per-trade 5000 --fee-bps 15 --paper

— FX intraday run with explicit cost model.
    python -m logos.cli backtest --symbol EURUSD=X --strategy mean_reversion --asset-class forex --interval 30m --slip-bps 8 --commission 0.0 --fx-pip-size 0.0001 --start 2023-06-01 --end 2023-08-31

— Pairs trade using custom window/threshold parameters.
    python -m logos.cli backtest --symbol AAPL --strategy pairs_trading --params window=20,threshold=1.5 --paper

— Momentum run using .env defaults for costs and interval.
    python -m logos.cli backtest --symbol TSLA --strategy momentum --start 2024-01-01 --end 2024-03-31

— High-frequency crypto smoke test (5-minute bars).
    python -m logos.cli backtest --symbol BTC-USD --strategy mean_reversion --asset-class crypto --interval 5m --start 2024-01-01 --end 2024-01-07 --paper

— Momentum run with custom moving-average windows and smaller sizing.
    python -m logos.cli backtest --symbol MSFT --strategy momentum --params fast=20,slow=50 --paper --dollar-per-trade 2000

— Forex pairs lesson run via CLI wrapper.
    python -m logos.cli backtest --symbol EURUSD --strategy pairs_trading --asset-class forex --params hedge_ratio=0.95 --paper

Tutor Mode Commands

— List available Tutor lessons and exit.
    python -m logos.tutor --list

— Narrated mean-reversion lesson with transcript and glossary output.
    python -m logos.tutor --lesson mean_reversion

— Mean-reversion lesson with annotated plots and formula derivations.
    python -m logos.tutor --lesson mean_reversion --plot --explain-math

— Momentum lesson emphasizing regime shifts with visuals.
    python -m logos.tutor --lesson momentum --plot

— Pairs trading lesson with spread/z-score panels and math notes.
    python -m logos.tutor --lesson pairs_trading --plot --explain-math

Maintenance and Diagnostics

— Full CLI/Tutor option reference (like a man page).
    python -m logos.cli backtest --help
    python -m logos.tutor --help

— Run deterministic regression suite.
    pytest -q

— Quick synthetic smoke test on bundled fixture data.
    python -m logos.cli backtest --symbol DEMO --strategy mean_reversion --paper --start 2023-01-01 --end 2023-01-15

— Verify directory scaffolding after checkout
    python - <<'PY'
from logos.paths import ensure_dirs

ensure_dirs()
print("dirs ok")
PY