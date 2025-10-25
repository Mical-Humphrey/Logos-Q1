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
# Developer tooling, lint, tests
pip install -r requirements/dev.txt

# Optional: copy defaults and edit
cp .env.example .env

# Regression tests
pytest -q
```
Regenerate the pinned requirement files with `pip-compile --generate-hashes` using
the manifests in `requirements/*.in` when bumping dependencies.
`logos.config.Settings` exposes all configuration fields (mode, brokers, risk, credentials). Override via `.env` or environment variables.

---

## CLI Handbook

### Backtesting (`logos.cli backtest`)
The backtest CLI spins up a portfolio simulation using historical data. Results (metrics, CSV logs, equity curve) land in `runs/<timestamp>_<symbol>_<strategy>/`.

#### Date & window contract
- Supply either an explicit `[--start YYYY-MM-DD --end YYYY-MM-DD]` pair **or** a single `--window ISO-8601-duration` (for example `P90D`).
- `--tz` controls timezone parsing for both modes (default: `UTC`). Provide any IANA identifier (`America/New_York`, `Europe/London`, ...). ISO timestamps with offsets are respected.
- `--allow-env-dates` re-enables the legacy `.env` fallback and the CLI logs the exact keys and values consumed when this path is taken.
- Empty, reversed, or otherwise invalid windows will become hard failures in the validator; phase 2 wiring will make this guard enforceable.
- Omit both options and the CLI fails fast (exit code 2) before any downloads or run directories are created, with an actionable hint on how to fix the call.
- When `--allow-env-dates` is supplied, the CLI logs the exact environment keys and values used so the provenance is auditable.
- Timezone names are validated up front; misspellings such as `America/Nwe_York` are rejected with guidance to supply a valid IANA identifier.

> **Window primer:** Logos treats every window as a first-class type, normalizing inputs to UTC and enforcing `[start, end)` semantics (inclusive start, exclusive end). Mixed inputs (`--window` together with `--start/--end`) are rejected before any artifacts are written.

- **UTC normalization:** tz-aware timestamps or `--tz` inputs are converted to UTC immediately; provenance files capture both the normalized bounds and the original timezone label.
- **Duration conversion example:** `python -m logos.cli backtest --symbol DEMO --strategy mean_reversion --window P5D --paper --tz America/New_York` resolves to `start=2024-03-25T00:00:00+00:00`, `end=2024-03-30T00:00:00+00:00` when launched on `2024-03-30` (UTC midnight anchor).
- **Explicit bounds example:** `--start 2024-06-01T09:30:00-04:00 --end 2024-06-05T16:00:00-04:00 --tz America/New_York` becomes `2024-06-01T13:30:00+00:00 → 2024-06-05T20:00:00+00:00` internally.
- **Bar-count assurance:** `tests/test_barcount_windows.py` covers DST fallback (expect 7 NYSE sessions), leap day spans (Feb 29 retained), and month-end crossovers (July 31 → Aug 2 yields three closes) so downstream analytics see predictable row counts when `[start, end)` windows traverse calendar edges.

> **Migration note:** Prior releases silently read `.env` defaults when `--start/--end` were omitted. Phase 2 hardening requires an explicit window. Example:
> - Before: `python -m logos.cli backtest --symbol MSFT --strategy momentum`
> - After:  `python -m logos.cli backtest --symbol MSFT --strategy momentum --window P60D`

#### Scenario: Daily equity mean reversion (paper mode)
```bash
python -m logos.cli backtest --symbol MSFT --strategy mean_reversion \
  --asset-class equity --start 2022-01-01 --end 2024-01-01 --paper --tz America/New_York
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
  --window P90D --allow-env-dates
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

### Indexing contract
- Prefer `.iloc` for positional access (rolling windows, loop counters, fixture slices) and `.loc` with `pandas.Timestamp` labels when operating on `DatetimeIndex` data.
- Strategy outputs, price frames, and run artifacts must retain `DatetimeIndex` with tz-aware timestamps; avoid object dtypes for time series columns so provenance and window checks stay deterministic.
- Session metadata (e.g., `metrics.json` → `provenance.window`) records the UTC bounds generated by the `Window` object for post-run audits.

### Synthetic Data Policy & Provenance
- Synthetic bars are **disabled by default**. Any attempt to reach fixture generators without `--allow-synthetic` exits early with guidance and no artifacts written.
- Enable synthetic data explicitly with `--allow-synthetic` when rehearsing demos or fixtures. The CLI logs the acknowledgement and tags the run as synthetic.
- Every run now emits provenance alongside metrics:
  - `metrics.json` gains a `provenance` block explaining window, timezone, seeds, synthetic usage, and adapter context.
  - `provenance.json` holds the full audit payload: git SHA (when available), data lineage (fixture/cache paths, download symbol, resampling), CLI arguments, environment flags, and adapter entrypoint metadata.
  - `session.md` is the human-readable summary; synthetic runs are prefixed with `# SYNTHETIC RUN` and enumerate generator/fixture details.
  - Expect these files under `runs/<timestamp>_<symbol>_<strategy>/` for CLI backtests and `runs/live/reg_cli/<seed>-<label>/` for regression harness outputs. Set `LOGOS_SEED=7` (or another integer) before invoking backtests or live regressions when you need reproducible shuffles in strategy logic.
- Tests in `tests/test_cli_provenance.py` assert that real runs omit synthetic labeling and that metrics/session artifacts reflect the correct provenance fields.

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

## Deterministic Regression Harness
Phase 2 ships a reproducible regression runner that exercises the translator, brokers, feeds, risk
guards, and artifact writers under a fixed seed and dataset.

- Fixture bundle: `tests/fixtures/live/regression_default`
- Fixed seed: `--seed 7` (prepends a deterministic run id: `0007-<label>`)
- Clock: `MockTimeProvider` pinned to `2024-01-01T09:29Z` → `09:32Z`

```bash
# Paper broker reference run (matches smoke baselines)
python -m logos.live.regression --adapter-mode paper \
  --label regression-smoke --seed 7 \
  --dataset tests/fixtures/live/regression_default \
  --output-dir runs/live/reg_cli

# CCXT dry-run adapter rehearsal (emits adapter_logs.jsonl)
python -m logos.live.regression --adapter-mode adapter --adapter ccxt \
  --label ccxt-dry-run --seed 7 \
  --dataset tests/fixtures/live/regression_default \
  --output-dir runs/live/reg_cli

# Alpaca dry-run adapter rehearsal (same seed + dataset)
python -m logos.live.regression --adapter-mode adapter --adapter alpaca \
  --label alpaca-dry-run --seed 7 \
  --dataset tests/fixtures/live/regression_default \
  --output-dir runs/live/reg_cli
```

> **Deterministic reminder:** You can front-load `LOGOS_SEED=7` (or any integer) when calling the CLI or live regression harness to tag artifacts with the seed and reproduce pseudo-random branches. Provenance now captures the window bounds, timezone label, and seed together for each run.

Resulting artifacts (snapshot, equity curve, metrics, adapter logs) are indexed — together with
sha256 checksums — in `docs/PHASE2-ARTIFACTS.md`. Each regression run also writes `provenance.json`
and `session.md`, mirroring the CLI provenance contract so baseline comparisons cover data lineage
and human-readable notes.

---

## Safety Checklist (Paper & Dry-Run)
- Confirm `.env` contains `MODE=paper` and desired broker identifiers before launching the live
  loop.
- Run `python -m logos.config_validate` to verify credentials, directories, and risk defaults.
- Stage kill-switch and monitoring: create/touch the file passed via `--kill-switch-file` and tail
  `logos/logs/live.log` in a dedicated terminal.
- Start the runner (paper or dry-run). On launch the guard evaluation order is:
  1. Max notional & position caps (`RiskLimits.max_notional`, `RiskLimits.max_position`).
  2. Per-symbol position caps (`RiskLimits.symbol_position_limits`).
  3. Session drawdown breaker (`RiskLimits.max_drawdown_bps`).
  4. Consecutive reject breaker (`RiskLimits.max_consecutive_rejects`).
  5. Stale data threshold (`RiskLimits.stale_data_threshold_s`).
  6. Kill switch file check.
- Every halt writes a structured event to `state.jsonl` and a summary bullet to `session.md`.
- To rehearse recovery, re-run the same command; the runner reloads `state.json`, rehydrates FIFO
  inventory, and resumes after guards pass.
Detailed drill scripts live in `docs/LIVE-RUNBOOK.md` (Safety Checklist section).

---

## QA Stack Commands
Run these in the project root with the virtual environment activated:

```bash
# Unit + integration suite with coverage
coverage run -m pytest -q
coverage report -m

# Linting & formatting gatekeepers
ruff check .
black --check .   # known formatting backlog documented in CHANGELOG

# Static types (requires pandas & yaml stubs; see CHANGELOG for open items)
mypy .

# Deterministic regression smoke matrix (paper + adapters)
python -m logos.live.regression --help
```

---

## Artifact Layout & Checksum Verification
- Live sessions write to `runs/live/sessions/<session_id>/` (state snapshots, CSVs, Markdown
  summary, logs).
- Regression rehearsals land in `runs/live/reg_cli/0007-<label>/` as described above.
- Daily trade consolidations live under `runs/live/trades/` with `<symbol>_<YYYYMMDD>.csv` naming.
- Repository-wide logs stream to `logos/logs/`.
- Validate artifacts with `sha256sum <file>`; expected digests are recorded in
  `docs/PHASE2-ARTIFACTS.md` alongside baseline references in `tests/fixtures/regression/smoke/`.

---

## Baseline Refresh Governance
1. Run the regression matrix (paper, CCXT, Alpaca) and confirm diffs are intentional.
2. Request peer review; consensus is required before promoting new baselines.
3. Refresh via
   ```bash
   python -m logos.live.regression --refresh-baseline --confirm-refresh \
     --dataset tests/fixtures/live/regression_default --seed 7
   ```
4. Commit updated artifacts under `tests/fixtures/regression/smoke/` and update
   `docs/PHASE2-ARTIFACTS.md` with new checksums.
5. Document rationale and scope in `CHANGELOG.md` and link the review issue.

---

## Phase 2 Traceability
The following matrix links Phase 2 requirements to operating procedures and evidence:

| ID | Scope | Evidence |
| --- | --- | --- |
| FR-001 | Translator emits quantized orders | `docs/LIVE-RUNBOOK.md` §Deterministic Translator Drill; `tests/test_live_runner.py` |
| FR-002 | Deterministic paper broker | `docs/LIVE-RUNBOOK.md` §Paper Broker Audit; `runs/live/reg_cli/0007-regression-smoke/` |
| FR-003 | Deterministic feeds & freshness | `docs/LIVE-RUNBOOK.md` §Feed Replay Checklist; `tests/test_cached_feed.py` |
| FR-004 | Risk guard enforcement & halts | Safety Checklist above; `tests/test_risk.py`, `tests/test_live_runner.py` |
| FR-005 | Session persistence & restart | `docs/LIVE-RUNBOOK.md` §Recovery Playbook; `runs/live/sessions/` examples |
| FR-006 | Artifact bundle | Artifact Layout section; `tests/test_live_artifacts.py` |
| FR-007 | Dry-run adapters | Regression matrix commands (CCXT/Alpaca) & adapter logs; `docs/PHASE2-ARTIFACTS.md` |
| FR-008 | Offline CI hardening | QA Stack commands (pytest/coverage offline); `docs/LIVE-RUNBOOK.md` §Environment Guards |
| SC-001 | Deterministic rehearsal in <15 min | Regression Harness section; `docs/LIVE-RUNBOOK.md` §Timeline Expectations |
| SC-002 | Guardrail rehearsal scripts | Safety Checklist + `docs/LIVE-RUNBOOK.md` §Guard Simulations |
| SC-003 | Offline test posture | QA Stack commands; `tests/test_readme_commands.py` |
| SC-004 | Documentation coverage | This README + `docs/MANUAL.html`, `docs/LIVE-RUNBOOK.md`, `CHANGELOG.md` |

## Documentation & Learning Map
| Artifact | Description |
| --- | --- |
| `docs/index.html` | Entry point linking to all documentation pages. |
| `docs/MANUAL.html` | Operations manual with install steps, backtests, and live workflow walk-throughs. |
| `docs/MATH.html` | Mathematical derivations for indicators and metrics. |
| `docs/FINANCE.html` | Market intuition, case studies, and playbooks. |
| `docs/SDK_PRESETS.md` | Strategy SDK HOWTO covering preset usage, parameters, and explain output. |
| `docs/SYSTEM_DESIGN.html` | Architecture diagrams, module responsibilities, and roadmap context. |

---

## Phase 3: Visual Dashboard

Logos-Q1 now includes a **read-only Streamlit dashboard** for exploring backtests, monitoring live sessions, and analyzing performance.

### Quick Start

Launch the dashboard with:

```bash
streamlit run logos/ui/streamlit/app.py
```
The server binds to `127.0.0.1` by default so the dashboard is only reachable
locally. Open `http://localhost:8501` in your browser.

> **Remote access?** Create an SSH tunnel instead of exposing the process:
> `ssh -N -L 8501:127.0.0.1:8501 user@your-host`. Only set
> `LOGOS_DASHBOARD_ALLOW_REMOTE=true` (binding to `0.0.0.0`) when fronted by a
> TLS proxy or VPN gateway.

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

### CLI Troubleshooting Quick Reference
- `error: Backtest requires either --window ISO-8601 duration or both --start and --end` → provide `--window P30D` or explicit bounds; the validator blocks unset inputs.
- `error: Pass either --window or the --start/--end pair, but not both.` → remove one set; mixed inputs are unsupported because the `Window` type enforces a single source of truth.
- `error: Window 'P-30D' is not a supported ISO-8601 duration.` → fix the token (e.g., `P30D`, `P4W`); all duration components must be positive integers.
