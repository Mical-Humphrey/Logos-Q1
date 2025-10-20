# Logos-Q1 Manual Regression Test Playbook (Phase 1–3)

A narrated, step-by-step manual test checklist for Logos-Q1 covering:
- Phase 1–3 scope: Backtesting CLI, Tutor Mode, Live (paper) scaffolding loop, and Streamlit dashboard (view-only).
- Deterministic-enough test assets and date windows.
- No production credentials; paper/sim mode only.
- Idempotent steps and cleanup.

Why this matters: This playbook provides a consistent, repeatable way for a human tester to verify core functionality, catch regressions early, and leave the repository clean for subsequent runs.

---

## Test Data and Conventions (Fixed Inputs for Determinism)

- Symbols / assets:
  - Equity: AAPL, MSFT
  - Crypto: BTC-USD
  - Forex: EURUSD (maps to EURUSD=X under the hood)
- Date window: `--start 2023-01-01 --end 2023-06-30`
- Strategies: `mean_reversion`, `momentum`, `pairs_trading`
- Interval: `--interval 1d`
- Paper flag: `--paper` where applicable
- CLI entry points:
  - Backtests: `python -m logos.backtest …`
  - Tutor: `python -m logos.tutor …`
  - Live (paper scaffold): `python -m logos.live trade …`
  - Streamlit: `streamlit run app/dashboard.py`

Directory conventions:
- `data/{raw,equity,crypto,forex,cache}/…`
- `runs/{backtests,lessons,live,portfolio,brain,logs}/…`
- `logos/logs/app.log` (and `runs/logs/` if used)

Assumptions:
- Python venv is activated; dependencies installed.
- `.env` exists (copied from `.env.example`) with safe defaults. No real API keys required.

---

## 0. Summary Results (Fill During Test)

| Module                                | Result (Pass/Fail) | Tester Initials | Timestamp (UTC)       | Notes / Links to Logs |
|---------------------------------------|--------------------|------------------|------------------------|-----------------------|
| Pre-flight & Environment Sanity       | [ ] Pass / [ ] Fail |                  |                        |                       |
| Backtesting CLI — Equity/Momentum     | [ ] Pass / [ ] Fail |                  |                        |                       |
| Backtesting CLI — Crypto/MeanRev      | [ ] Pass / [ ] Fail |                  |                        |                       |
| Backtesting CLI — Forex/Momentum      | [ ] Pass / [ ] Fail |                  |                        |                       |
| Backtesting CLI — Errors & Edge Cases | [ ] Pass / [ ] Fail |                  |                        |                       |
| Tutor Mode                            | [ ] Pass / [ ] Fail |                  |                        |                       |
| Live (Paper) Loop                     | [ ] Pass / [ ] Fail |                  |                        |                       |
| Streamlit Dashboard (View-only)       | [ ] Pass / [ ] Fail |                  |                        |                       |

Why this matters: A single roll-up view makes it easy to gauge release readiness at a glance.

---

## 1. Pre-flight & Environment Sanity

Goal: Ensure environment, paths, and logging are correctly set up before functional tests.

### 1.1 Python and venv checks
- [ ] Verify Python version and venv activation:
  ```bash
  python --version
  which python
  ```
  Expect: Python 3.9+ and `which python` points to venv.

- [ ] Confirm key dependencies are installed:
  ```bash
  pip list | grep -E 'pandas|numpy|scipy|matplotlib|plotly|streamlit|yfinance|requests|pydantic|pytest'
  ```
  Expect: Packages listed; versions are non-empty.

Why this matters: Many runtime issues stem from missing or mismatched dependencies.

### 1.2 Minimal directory skeleton
- [ ] Ensure expected directories exist (create if missing):
  ```bash
  mkdir -p data/{raw,equity,crypto,forex,cache} \
           runs/{backtests,lessons,live,portfolio,brain,logs} \
           logos/logs
  ```
  Expect: No error; directories present.

- [ ] If available, initialize system paths:
  ```bash
  python -c "from logos.paths import ensure_dirs; ensure_dirs(); print('OK')"
  ```
  Expect: Prints `OK` (if module exists); otherwise skip with note.

Why this matters: Components expect these paths for IO.

### 1.3 .env presence and safe defaults
- [ ] Verify `.env` file exists:
  ```bash
  test -f .env && echo "Found .env" || echo "Missing .env"
  ```
  Expect: `Found .env`. If missing, copy from example:
  ```bash
  cp .env.example .env
  ```

- [ ] Open `.env` and confirm minimal safe values, e.g.:
  ```
  ENV=dev
  LOG_LEVEL=INFO
  DATA_PROVIDER=yfinance
  PAPER_TRADING=true
  # Placeholder (should remain blank for this playbook)
  ALPACA_API_KEY_ID=
  ALPACA_API_SECRET_KEY=
  ```
  Expect: No real API keys present; paper mode enabled.

Why this matters: Prevents accidental live trading and stabilizes behavior.

### 1.4 Log routing sanity
- [ ] Confirm logs file exists and is writable:
  ```bash
  touch logos/logs/app.log && ls -l logos/logs/app.log
  ```
  Expect: File exists; updated timestamp.

- [ ] Tail logs while performing a quick no-op (if available) to see append behavior:
  ```bash
  tail -n 20 -f logos/logs/app.log &
  TAIL_PID=$!
  # Optional lightweight command that triggers logging:
  python -c "import logging; logging.getLogger().setLevel('INFO'); logging.info('preflight-log-check')"
  sleep 1
  kill $TAIL_PID
  ```
  Expect: New `INFO` line appended; file grows (rotating/append acceptable).

Why this matters: Logging is a primary debugging surface.

- [ ] Record Pre-flight result:

| Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|--------------------|------------------|-----------|-------------|
|                    |                  |           |             |

---

## 2. Backtesting CLI — Happy Paths

Common expectations for all runs:
- Console includes: “Starting backtest via CLI” and a data loader line for the specific symbol/interval.
- Artifacts under `runs/backtests/…` (some projects use a timestamped subdir).
- Logs appended to `logos/logs/app.log` with `INFO` lines referencing the run.

Tip: If the implementation writes per-run directories, identify the newest run path with:
```bash
LATEST_BT_DIR=$(ls -td runs/backtests/*/ 2>/dev/null | head -n 1); echo "$LATEST_BT_DIR"
```

### 2.1 Equity / momentum (AAPL)
- [ ] Run:
  ```bash
  python -m logos.backtest \
    --symbol AAPL \
    --strategy momentum \
    --asset-class equity \
    --start 2023-01-01 --end 2023-06-30 \
    --interval 1d \
    --paper
  ```
- [ ] Expect console to include:
  - “Starting backtest via CLI”
  - “Loading data: symbol=AAPL interval=1d”
  - “Strategy: momentum asset_class=equity”
  - “Completed backtest” or similar success line

- [ ] Artifact checks (adjust for actual filenames and subdirs):
  - `runs/backtests/trades_AAPL_momentum.csv` exists, non-empty
  - `runs/backtests/equity_AAPL_momentum.png` exists, size > 10KB
  - Optional: `runs/backtests/metrics.json` exists; contains numeric `CAGR`, `Sharpe`, `MaxDD`

- [ ] Minimal schema check for trades CSV:

| Column | Type expectation | Sample rule |
|--------|-------------------|-------------|
| time   | datetime/string   | parseable as datetime |
| side   | string            | in {buy, sell} |
| qty    | number            | qty != 0 |
| price  | number            | price > 0 |
| fee    | number            | fee >= 0 |

- [ ] Log check:
  ```bash
  grep -E "backtest|AAPL|momentum" -n logos/logs/app.log | tail -n 10
  ```
  Expect: INFO lines referencing this run; no stack traces.

Why this matters: Validates a core, representative equity strategy path.

### 2.2 Crypto / mean_reversion (BTC-USD)
- [ ] Run:
  ```bash
  python -m logos.backtest \
    --symbol BTC-USD \
    --strategy mean_reversion \
    --asset-class crypto \
    --start 2023-01-01 --end 2023-06-30 \
    --interval 1d \
    --paper
  ```
- [ ] Expect similar console success lines; ensure crypto loader is invoked.

- [ ] Artifacts:
  - `runs/backtests/trades_BTC-USD_mean_reversion.csv` non-empty
  - `runs/backtests/crypto_BTC-USD_mean_reversion.png` size > 10KB
  - Optional `metrics.json` with numeric fields

- [ ] Minimal schema check (CSV):
  Same columns and rules as above.

- [ ] Log check for “BTC-USD” and “mean_reversion”.

Why this matters: Confirms crypto pipeline behavior and data source normalization.

### 2.3 Forex / momentum (EURUSD) — ticker normalization
- [ ] Run:
  ```bash
  python -m logos.backtest \
    --symbol EURUSD \
    --strategy momentum \
    --asset-class forex \
    --start 2023-01-01 --end 2023-06-30 \
    --interval 1d \
    --paper
  ```
- [ ] Expect console to show normalized loader (e.g., EURUSD -> EURUSD=X) and success.

- [ ] Artifacts:
  - `runs/backtests/trades_EURUSD_momentum.csv` non-empty
  - `runs/backtests/forex_EURUSD_momentum.png` size > 10KB
  - Optional `metrics.json`

- [ ] Minimal schema check (CSV):
  Same columns and rules as above.

- [ ] Log check for “EURUSD” and normalization note (if implemented).

Why this matters: Ensures FX tickers map correctly to data providers.

- [ ] Record Backtesting Happy Path results:

| Case                | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|---------------------|--------------------|------------------|-----------|-------------|
| Equity/Momentum     |                    |                  |           |             |
| Crypto/MeanRev      |                    |                  |           |             |
| Forex/Momentum      |                    |                  |           |             |

---

## 3. Backtesting CLI — Error Handling & Edge Cases

Run in a clean shell or after previous steps. Expect graceful messages and no crashes.

### 3.1 Missing dates → helpful error or fallback note
- [ ] Command (omit dates):
  ```bash
  python -m logos.backtest \
    --symbol AAPL \
    --strategy momentum \
    --asset-class equity \
    --interval 1d \
    --paper
  ```
- [ ] Expect: clear error or explicit note about using `.env` defaults; process exits gracefully (non-zero exit OK if documented).

### 3.2 Unknown strategy name
- [ ] Command:
  ```bash
  python -m logos.backtest \
    --symbol AAPL \
    --strategy not_a_real_strategy \
    --asset-class equity \
    --start 2023-01-01 --end 2023-06-30 \
    --interval 1d \
    --paper
  ```
- [ ] Expect: clear error listing valid options; no stack dump.

### 3.3 Empty data window
- [ ] Command (start > end):
  ```bash
  python -m logos.backtest \
    --symbol AAPL \
    --strategy momentum \
    --asset-class equity \
    --start 2023-06-30 --end 2023-01-01 \
    --interval 1d \
    --paper
  ```
- [ ] Expect: graceful exit with informative message; no crash.

### 3.4 Logs reflect user-friendly errors
- [ ] Verify logs:
  ```bash
  grep -E "ERROR|invalid|unknown strategy|date" -n logos/logs/app.log | tail -n 20
  ```
  Expect: user-friendly text, minimal/no stack traces.

Why this matters: Good errors reduce support load and improve UX.

- [ ] Record Error Handling results:

| Scenario             | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|----------------------|--------------------|------------------|-----------|-------------|
| Missing dates        |                    |                  |           |             |
| Unknown strategy     |                    |                  |           |             |
| Empty data window    |                    |                  |           |             |
| Logs user-friendly   |                    |                  |           |             |

---

## 4. Tutor Mode

### 4.1 List lessons
- [ ] Command:
  ```bash
  python -m logos.tutor --list
  ```
  Expect: printed lesson IDs with one-line descriptions (includes `mean_reversion`).

### 4.2 Run mean_reversion with plots and math
- [ ] Command:
  ```bash
  python -m logos.tutor \
    --lesson mean_reversion \
    --plot \
    --explain-math \
    --start 2023-01-01 --end 2023-03-31
  ```
- [ ] Expect:
  - Console indicates lesson run start/end and output directory.
  - Artifacts under `runs/lessons/mean_reversion/<timestamp>/`:
    - `transcript.md` (non-empty; mentions SMA/z-score)
    - `plots/*.png` (≥1 image; each > 10KB)
    - `explain.md` (math derivations present)

- [ ] Quick quality rubric for `transcript.md`:
  - [ ] Definitions present (SMA, z-score)
  - [ ] Entry/exit triggers explained
  - [ ] At least one numeric example or pseudo-formula
  - [ ] No TODO placeholders

Why this matters: Verifies educational assets and documentation generation.

- [ ] Record Tutor Mode results:

| Subtest                  | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|--------------------------|--------------------|------------------|-----------|-------------|
| List lessons             |                    |                  |           |             |
| Run mean_reversion lesson|                    |                  |           |             |
| Transcript quality       |                    |                  |           |             |

---

## 5. Live (Paper) Loop — Scaffold Smoke Test

Short simulated session; no real broker.

- [ ] Start session (terminal window A):
  ```bash
  python -m logos.live trade \
    --symbol BTC-USD \
    --strategy mean_reversion \
    --interval 1m \
    --paper \
    --max-notional 1000 \
    --kill-switch-file .kill
  ```
  Expect console:
  - Session start banner with parameters
  - Risk-limit parse line; session allocation line
  - Running… waiting for ticks or simulated loop
  - Graceful stop message on interrupt or kill-switch

- [ ] Verify session artifacts (when running):
  - `runs/live/sessions/<id>/`
    - `logs/run.log`
    - `state.json`
    - `trades.csv` (may be empty initially but appears after first tick)
    - `positions.csv` (optional)

- [ ] Trigger clean shutdown (terminal window B):
  ```bash
  touch .kill
  ```
  Expect in terminal A: shutdown detected, clean exit. Remove `.kill` after:
  ```bash
  rm -f .kill
  ```

- [ ] Log verification:
  ```bash
  SESSION_DIR=$(ls -td runs/live/sessions/*/ 2>/dev/null | head -n 1)
  echo "$SESSION_DIR"
  tail -n 50 "$SESSION_DIR/logs/run.log"
  ```
  Expect: lines for risk limits, allocation, start/end markers; no uncaught exceptions.

Why this matters: Confirms the live orchestration scaffolding and kill-switch behave predictably in paper mode.

- [ ] Record Live Loop results:

| Checkpoint                    | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|------------------------------|--------------------|------------------|-----------|-------------|
| Session starts               |                    |                  |           |             |
| Artifacts created            |                    |                  |           |             |
| Kill-switch clean shutdown   |                    |                  |           |             |
| Logs clean (no exceptions)   |                    |                  |           |             |

---

## 6. Streamlit Dashboard (View-only)

- [ ] Launch:
  ```bash
  streamlit run app/dashboard.py
  ```
- [ ] In browser, verify pages load (within ~5s) with no terminal errors:
  - Overview: shows counts of recent backtests, lessons, live sessions read from `runs/*`
  - Backtests: table listing artifacts with links (no write actions)
  - Live Monitor (paper): shows last session’s summary from `runs/live/sessions/latest/` or most recent

- [ ] Open a few artifact links; ensure they render (CSVs open/download, PNGs display).

- [ ] Stop Streamlit with Ctrl+C.

Why this matters: Smoke-tests the read-only UI over generated artifacts.

- [ ] Record Streamlit results:

| Checkpoint                 | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|---------------------------|--------------------|------------------|-----------|-------------|
| Overview renders          |                    |                  |           |             |
| Backtests table OK        |                    |                  |           |             |
| Live Monitor shows latest |                    |                  |           |             |
| No terminal errors        |                    |                  |           |             |

---

## 7. Artifacts & Schema Checks (Quick Tables)

Use these to validate shape/quality of common outputs.

### 7.1 trades_*.csv

| Column | Required | Type expectation | Validation rule            |
|--------|----------|------------------|----------------------------|
| time   | Yes      | datetime/string  | parseable as datetime      |
| side   | Yes      | string           | in {buy, sell}             |
| qty    | Yes      | number           | qty != 0                   |
| price  | Yes      | number           | price > 0                  |
| fee    | Yes      | number           | fee >= 0                   |

Quick check:
```bash
csv_path="runs/backtests/trades_AAPL_momentum.csv"
head -n 5 "$csv_path"
```

### 7.2 positions.csv (if present)

| Column        | Required | Type expectation | Validation rule       |
|---------------|----------|------------------|-----------------------|
| symbol        | Yes      | string           | not empty             |
| qty           | Yes      | number           | numeric               |
| avg_price     | Yes      | number           | avg_price >= 0        |
| unrealized_pnl| Yes      | number           | numeric               |

### 7.3 metrics.json (if present)

| Key    | Type   | Notes                                 |
|--------|--------|----------------------------------------|
| CAGR   | number | Annualized growth rate                |
| Sharpe | number | Annualized (state units in UI/logs)   |
| MaxDD  | number | Drawdown as fraction or percent       |

Quick check:
```bash
jq '.' runs/backtests/metrics.json
```

### 7.4 PNG outputs

| File                               | Check                |
|------------------------------------|----------------------|
| equity_*_*.png / crypto_*_*.png    | size > 10KB          |
| plots/*.png (tutor)                | size > 10KB          |

Quick check:
```bash
find runs -name "*.png" -printf "%p %k KB\n" 2>/dev/null | sort
```

---

## 8. Troubleshooting & Log Anchors

Common issues and where to look:

- Missing dependencies or incompatible versions
  - Symptom: `ModuleNotFoundError` or import errors.
  - Action: `pip install -r requirements.txt` (or project’s install step), re-run.

- Network/data provider issues (e.g., rate limits, unreachable)
  - Symptom: HTTP errors, empty datasets.
  - Action: Re-run later; for tests prefer cached or local data if supported. Verify `.env` `DATA_PROVIDER`.

- Timezone or date parsing
  - Symptom: Empty data windows or off-by-one-day.
  - Action: Ensure ISO `YYYY-MM-DD`; check provider normalization.

- Strategy not found
  - Symptom: “Unknown strategy” errors.
  - Action: Use valid set: `mean_reversion`, `momentum`, `pairs_trading`.

- Enable DEBUG logging to investigate
  - Set in `.env`:
    ```
    LOG_LEVEL=DEBUG
    ```
    Or run with a `--log-level DEBUG` flag if supported.

- Log locations
  - Global: `logos/logs/app.log`
  - Backtests: under `runs/backtests/...`
  - Tutor: `runs/lessons/<lesson>/<timestamp>/`
  - Live: `runs/live/sessions/<id>/logs/run.log`

Search tips:
```bash
grep -nE "ERROR|WARN|Exception|Traceback" logos/logs/app.log | tail -n 50
```

---

## 9. Cleanup (Idempotency)

Warning: Destructive. Removes generated artifacts for a clean re-run.

- [ ] Confirm you want to delete generated artifacts:
  ```bash
  read -p "This will delete runs/* and data/cache/*. Proceed? (yes/no) " yn; [ "$yn" = "yes" ] || exit 0
  ```
- [ ] Cleanup:
  ```bash
  rm -rf runs/backtests/* \
         runs/lessons/* \
         runs/live/sessions/* \
         data/cache/*
  ```
- [ ] Verify directories still exist (empty is OK):
  ```bash
  find runs -maxdepth 2 -type d -print
  find data -maxdepth 2 -type d -print
  ```

Why this matters: Ensures the playbook can be repeated reliably.

- [ ] Record Cleanup result:

| Result (Pass/Fail) | Tester Initials | Timestamp | Notes |
|--------------------|------------------|-----------|-------|
|                    |                  |           |       |

---

## 10. Per-section Pass/Fail Recording

Use these tables to log each section’s outcome.

### Pre-flight & Environment Sanity
| Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|--------------------|------------------|-----------|-------------|
|                    |                  |           |             |

### Backtesting CLI — Happy Paths
| Case                | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|---------------------|--------------------|------------------|-----------|-------------|
| Equity/Momentum     |                    |                  |           |             |
| Crypto/MeanRev      |                    |                  |           |             |
| Forex/Momentum      |                    |                  |           |             |

### Backtesting CLI — Errors & Edges
| Scenario             | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|----------------------|--------------------|------------------|-----------|-------------|
| Missing dates        |                    |                  |           |             |
| Unknown strategy     |                    |                  |           |             |
| Empty data window    |                    |                  |           |             |
| Logs user-friendly   |                    |                  |           |             |

### Tutor Mode
| Subtest                   | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|---------------------------|--------------------|------------------|-----------|-------------|
| List lessons              |                    |                  |           |             |
| Run mean_reversion lesson |                    |                  |           |             |
| Transcript quality        |                    |                  |           |             |

### Live (Paper) Loop
| Checkpoint                    | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|------------------------------|--------------------|------------------|-----------|-------------|
| Session starts               |                    |                  |           |             |
| Artifacts created            |                    |                  |           |             |
| Kill-switch clean shutdown   |                    |                  |           |             |
| Logs clean (no exceptions)   |                    |                  |           |             |

### Streamlit Dashboard
| Checkpoint                 | Result (Pass/Fail) | Tester Initials | Timestamp | Notes/Links |
|---------------------------|--------------------|------------------|-----------|-------------|
| Overview renders          |                    |                  |           |             |
| Backtests table OK        |                    |                  |           |             |
| Live Monitor shows latest |                    |                  |           |             |
| No terminal errors        |                    |                  |           |             |

---

## Appendix: Handy Commands

- Latest backtest directory:
  ```bash
  ls -td runs/backtests/*/ 2>/dev/null | head -n 1
  ```
- Show recent log lines:
  ```bash
  tail -n 100 logos/logs/app.log
  ```
- Validate JSON:
  ```bash
  jq '.' runs/backtests/metrics.json
  ```
- Kill background tail:
  ```bash
  kill $TAIL_PID
  ```

---