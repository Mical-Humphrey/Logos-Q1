# Logos-Q1

> "Learn like a student. Trade like a professional."

---

## Overview
Logos-Q1 is a quantitative trading laboratory that balances **education** and **execution**. Every subsystem is written to be readable and instructive, yet modular enough to wire into real data feeds and brokers as your workflow grows.

### Guiding Principles
- **Transparency** – code is annotated, cross-linked to math/finance docs, and designed to be teachable.
- **Modularity** – data sources, strategies, sizing, and execution layers are pluggable.
- **Safety-first execution** – live trading uses explicit acknowledgements, risk guards, and persistent audit logs.

---

## System Layers at a Glance
| Layer | Highlights |
| --- | --- |
| **CLI Tooling** | `logos.cli` (research backtests), `logos.live` (execution loop), `logos.tutor` (interactive lessons). |
| **Data & Feeds** | File, memory, and streaming adapters across equities, crypto, and FX with deterministic fixtures for testing. |
| **Strategy Engine** | Mean reversion, momentum, and pairs trading modules sharing sizing/risk helpers. |
| **Backtesting Harness** | Vectorized portfolio accounting, cost models, metrics, and artifact export under `runs/`. |
| **Live Execution (Phase 2)** | Runner loop, broker adapters (paper + CCXT/Alpaca/IB scaffolds), risk gates, session persistence, reporting. |
| **Tutor Mode** | Narrated lessons with transcripts, glossary dumps, and optional plots. |
| **Documentation Suite** | Rich HTML guides in `docs/` covering math, finance intuition, manual, and system design. |

---

## Installation & Environment
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optional: copy defaults and edit
cp .env.example .env

# Regression tests
pytest -q
```
`logos.config.Settings` exposes all configuration fields (mode, brokers, risk, credentials). Override via `.env` or environment variables.

---

## CLI Handbook

### Backtesting (`logos.cli backtest`)
The backtest CLI spins up a portfolio simulation using historical data. Results (metrics, CSV logs, equity curve) land in `runs/<timestamp>_<symbol>_<strategy>/`.

#### Scenario: Daily equity mean reversion (paper mode)
```bash
python -m logos.cli backtest --symbol MSFT --strategy mean_reversion \
  --asset-class equity --start 2022-01-01 --end 2024-01-01 --paper
```
**What it does:** pulls daily MSFT bars, applies the mean reversion signal, executes with paper fills, and stores trades/metrics under `runs/`.

#### Scenario: Crypto hourly momentum with custom sizing & fees
```bash
python -m logos.cli backtest --symbol BTC-USD --strategy momentum \
  --asset-class crypto --interval 1h --dollar-per-trade 5000 --fee-bps 15 --paper
```
**What it does:** simulates buying BTC-USD every hour with a 5k notional sizing rule and 15 bps fees.

#### Scenario: FX intraday run with explicit cost model
```bash
python -m logos.cli backtest --symbol EURUSD=X --strategy mean_reversion \
  --asset-class forex --interval 30m --slip-bps 8 --commission 0.0 \
  --fx-pip-size 0.0001 --start 2023-06-01 --end 2023-08-31
```
**What it does:** evaluates a EURUSD strategy with 30-minute bars, custom slippage, and pip sizing.

#### Scenario: Pairs trade with custom window & threshold
```bash
python -m logos.cli backtest --symbol AAPL --strategy pairs_trading \
  --params window=20,threshold=1.5 --paper
```
**What it does:** runs the pairs engine (AAPL hedged with default partner) using a 20-day window and 1.5 z-score threshold.

#### Scenario: Use `.env` sizing defaults for a momentum run
```bash
python -m logos.cli backtest --symbol TSLA --strategy momentum \
  --start 2024-01-01 --end 2024-03-31
```
**What it does:** reuses sizing/fee defaults from `logos.config.Settings`, so command line arguments stay minimal.

#### Scenario: High-frequency crypto smoke test (5-minute bars)
```bash
python -m logos.cli backtest --symbol BTC-USD --strategy mean_reversion \
  --asset-class crypto --interval 5m --start 2024-01-01 --end 2024-01-07 --paper
```
**What it does:** verifies your strategy behaves under shorter intervals and produces artifacts for quick inspection.

#### Scenario: Momentum with tighter windows and smaller sizing
```bash
python -m logos.cli backtest --symbol MSFT --strategy momentum \
  --params fast=20,slow=50 --paper --dollar-per-trade 2000
```
**What it does:** illustrates how to override the default moving-average windows and reduce position size.

#### Scenario: FX pairs lesson via CLI wrapper
```bash
python -m logos.cli backtest --symbol EURUSD --strategy pairs_trading \
  --asset-class forex --params hedge_ratio=0.95 --paper
```
**What it does:** demonstrates the hedged pairs variant developed for the education transcripts.

#### Scenario: Synthetic demo dataset regression
```bash
python -m logos.cli backtest --symbol DEMO --strategy mean_reversion \
  --paper --start 2023-01-01 --end 2023-01-15
```
**What it does:** runs against bundled fixture data; handy for continuous integration or smoke tests.

---

### Live Trading (`logos.live trade`)
The live runner coordinates data feeds, broker adapters, and risk gates. Paper mode is enabled by default; live submission requires an acknowledgement flag.

#### Session lifecycle
1. **Environment prep:** set `MODE=paper` (or `MODE=live` once ready) and choose a default `BROKER` in `.env`. Supply broker credentials (`CCXT_API_KEY`, `ALPACA_KEY_ID`, etc.) if applicable.
2. **Validate config:** `python -m logos.config_validate` ensures all required settings and directories exist.
3. **Run paper session:**
   ```bash
   python -m logos.live trade --symbol BTC-USD --strategy momentum \
     --interval 1m --params '{"fast":10,"slow":30}' --risk.max-dd-bps 400 \
     --kill-switch-file /tmp/logos.kill
   ```
4. **Go live intentionally:** add `--live --i-acknowledge-risk` only when supervision and risk controls are ready.

#### Safety Controls
| Guardrail | Flag / Setting | Purpose |
| --- | --- | --- |
| Acknowledgement | `--i-acknowledge-risk` | Opt-in required before sending real orders. |
| Mode gate | `MODE=paper|live` | Prevents accidental live trading without environment toggle. |
| Notional cap | `--max-notional` / `RISK_MAX_NOTIONAL` | Limits order size by dollar value. |
| Position cap | `--risk.max-position` / `RISK_MAX_POSITION` | Controls net exposure in units. |
| Drawdown breaker | `--risk.max-dd-bps` / `RISK_MAX_DD_BPS` | Stops when equity drawdown breaches threshold. |
| Reject breaker | `--risk.max-rejects` | Halts after repeated broker rejections. |
| Kill switch | `--kill-switch-file` | Touch the file externally to end the session safely. |
| Stale data check | `RISK_STALE_DATA_THRESHOLD_S` | Stops if feed latency is too high. |

#### Session Artifacts
| Path | Contents |
| --- | --- |
| `runs/live/sessions/<session_id>/state.json` | Persisted equity, positions, last bar timestamp. |
| `runs/live/sessions/<session_id>/state.jsonl` | Append-only event log (rejections, state checkpoints). |
| `orders.csv`, `trades.csv`, `positions.csv`, `account.csv` | Auditable record of decisions, fills, and broker snapshots. |
| `session.md` | Markdown summary emitted when the runner stops. |
| `logs/run.log` | Per-session log file attached via `session_manager`. |
| `logos/logs/live.log` | Shared live-mode log stream across sessions. |

#### Broker Adapter Status
| Adapter | Status | Notes |
| --- | --- | --- |
| `PaperBrokerAdapter` | ✅ Ready | Deterministic fills with FIFO lots; ideal for rehearsals and tests. |
| `CCXTBrokerAdapter` | 🛠️ Scaffolded | Credential plumbing exists; execution wiring is pending. |
| `AlpacaBrokerAdapter` | 🛠️ Scaffolded | REST endpoints stubbed; requires API integration. |
| `InteractiveBrokersAdapter` | 🛠️ Scaffolded | Gateway placeholders ready for future plumbing. |

> Strategies connect to the live loop via an `order_generator` hook. The CLI currently uses a placeholder generator until backtest strategies are gated for production order intent output.

---

### Tutor Mode (`logos.tutor`)
Tutor mode narrates strategies step-by-step with optional plots and math derivations. Transcripts and glossaries are stored under `runs/lessons/`.

```bash
# List available lessons
python -m logos.tutor --list

# Narrated mean reversion walkthrough
python -m logos.tutor --lesson mean_reversion

# Add charts and math derivations
python -m logos.tutor --lesson mean_reversion --plot --explain-math

# Momentum lesson with visuals
python -m logos.tutor --lesson momentum --plot

# Pairs trading deep dive with formulas
python -m logos.tutor --lesson pairs_trading --plot --explain-math
```

Each lesson covers signal logic, entry/exit rationale, risk framing, and includes glossary definitions for classroom use.

---

### Diagnostics & Utilities
```bash
# Full CLI/tutor option reference (man-page style)
python -m logos.cli backtest --help
python -m logos.tutor --help

# Validate configuration and directory scaffolding
python -m logos.config_validate

# Verify the path helpers are provisioned
python - <<'PY'
from logos.paths import ensure_dirs
ensure_dirs()
print("dirs ok")
PY
```

Use these commands in CI or before switching to a new machine to ensure consistent environments.

---

## Documentation & Learning Map
| Artifact | Description |
| --- | --- |
| `docs/index.html` | Entry point linking to all documentation pages. |
| `docs/MANUAL.html` | Operations manual with install steps, backtests, and live workflow walk-throughs. |
| `docs/MATH.html` | Mathematical derivations for indicators and metrics. |
| `docs/FINANCE.html` | Market intuition, case studies, and playbooks. |
| `docs/SYSTEM_DESIGN.html` | Architecture diagrams, module responsibilities, and roadmap context. |

---

## Phase 3: Visual Dashboard

Logos-Q1 now includes a **read-only Streamlit dashboard** for exploring backtests, monitoring live sessions, and analyzing performance.

### Quick Start

Launch the dashboard with:

```bash
streamlit run logos/ui/streamlit/app.py
```

The dashboard will open in your browser at `http://localhost:8501`.

### Features

- **📈 Overview** — KPI tiles, recent backtests, and live session status
- **🔍 Backtests** — Detailed analysis with metrics, equity charts, and trade tables
- **📡 Live Monitor** — Real-time account, positions, and log streaming with auto-refresh
- **🧪 Strategy Lab** — Explore strategies, parameters, and example commands
- **⚙️ Settings** — Configuration viewer and dashboard preferences
- **📚 Tutor Viewer** — Browse lesson transcripts and materials

### Key Characteristics

- **Read-Only**: Never writes or modifies any files
- **Fast**: mtime-based caching for quick data access
- **Safe**: Gracefully handles missing or partial data
- **Modular**: Reusable components across pages

For detailed documentation, see [`docs/DASHBOARD.md`](docs/DASHBOARD.md).

---

## Roadmap Snapshot
| Phase | Status | Focus |
| --- | --- | --- |
| Phase 1 | ✅ Complete | Educational backtesting foundation. |
| Phase 2 | 🚧 In Progress | Live execution scaffolding, broker integrations, safety validation. |
| Phase 3 | ✅ Complete | Streamlit dashboard for live monitoring and reporting. |
| Phase 4 | 🔜 Planned | Portfolio construction, ML alpha research, advanced risk modeling. |
| Phase 5 | 🔜 Planned | Deployment automation (desktop bundle, cloud orchestration). |

---

## License
MIT License — Logos-Q1 is open for study, extension, and responsible live trading use.
