# Logos Live Runbook

Phase 2 elevates Logos-Q1 from a deterministic backtest lab to an operational live rehearsal loop.
This runbook documents the exact steps, safety expectations, artifact audits, and governance
controls required to operate the system without touching real broker endpoints.

---

## Backtest Input Contract *(Phase 2 prerequisite)*
- Provide either a `[--start YYYY-MM-DD --end YYYY-MM-DD]` pair or a single `--window` ISO-8601 duration (for example `P45D`) when launching backtests. Inputs are mutually exclusive; the CLI normalizes what you provide.
- The resolved window is always normalized to UTC and treated as `[start, end)` (inclusive start, exclusive end). Provenance files record the original timezone label alongside the UTC bounds.
- `--tz` specifies the timezone used to interpret date strings (default `UTC`). Offsets supplied in ISO timestamps are honoured before UTC promotion.
- Use `--allow-env-dates` only when you deliberately want the legacy `.env` fallback; the CLI logs the environment keys consumed whenever this path is exercised.
- Empty, reversed, or otherwise invalid windows transition to hard failures once the validator hooks land later in Phase 2. Example failure: `requires either --window or --start and --end`.
- Validation runs before any run directories are created. Missing or malformed parameters exit immediately with a descriptive fix, preventing accidental artifact creation.

> **UTC conversion example:** `python -m logos.cli backtest --symbol MSFT --strategy momentum --window P5D --tz America/New_York` resolves to `start=2024-03-25T00:00:00+00:00`, `end=2024-03-30T00:00:00+00:00`.

> **Migration example:** `python -m logos.cli backtest --symbol MSFT --strategy momentum` ➜ `python -m logos.cli backtest --symbol MSFT --strategy momentum --window P60D`

---

## Window Semantics & Indexing
- Always supply a single window source: either `--window` or the `--start/--end` pair. The offline validator (wired into CI) stops execution before artifacts are emitted if both forms appear or if the ISO duration token is malformed.
- Treat UTC as canonical. tz-aware bounds like `--start 2024-06-01T09:30:00-04:00 --end 2024-06-05T16:00:00-04:00` normalize to `2024-06-01T13:30:00+00:00 → 2024-06-05T20:00:00+00:00`; daylight shifts merely change how many bars load.
- Use `.iloc` for positional loops (warm-up windows, rolling computations) and reserve `.loc` for label-based lookups against tz-aware `DatetimeIndex` columns. This contract keeps regression artifacts portable across feeds and timezones.
- Regression fixtures and `metrics.json` now embed `window.start_utc`, `window.end_utc`, and `timezone_label` so live rehearsals can be audited against offline results.

> **DST assurance:** Because the validator runs in UTC, month-end and DST edges cannot silently truncate your dataset; watch the validator output for the normalized bounds when investigating missing bars.

---

## Deterministic Translator Drill *(FR-001 · SC-001)*
1. Activate the project virtualenv and ensure dependencies are installed (`pip install -r requirements.txt`).
2. Confirm fixtures exist at `tests/fixtures/live/regression_default/` (bars, account, symbols).
3. Run the translator regression harness:
	 ```bash
	 python -m logos.live.regression --adapter-mode paper \
		 --label regression-smoke --seed 7 \
		 --dataset tests/fixtures/live/regression_default \
		 --output-dir runs/live/reg_cli
	 ```
4. Inspect `runs/live/reg_cli/0007-regression-smoke/snapshot.json` — orders appear as quantized
	 `order_intents` matching symbol precision (4 decimal price, whole-share quantity for AAPL).
5. Cross-check with `tests/test_live_runner.py::test_strategy_order_generator_emits_intents` to
	 verify canonical rounding and side selection.

---

## Paper Broker Audit *(FR-002)*
- Review `runs/live/reg_cli/0007-regression-smoke/artifacts/metrics.json` for realized/unrealized PnL.
- Confirm FIFO inventory state in `snapshot.json` under `positions` (`quantity` and `average_price`).
- If differences from the baseline arise, run `pytest tests/test_paper_broker.py -q` to confirm the
	fill engine remains deterministic.
- Expected checksum references appear in `docs/PHASE2-ARTIFACTS.md` — any deviation requires a
	baseline review.

---

## Feed Replay Checklist *(FR-003)*
1. Clear cache directories (`rm -rf input_data/cache/*`) to guarantee fixture replay.
2. Run `pytest tests/test_cached_feed.py tests/live/test_live_feed.py -q` to validate deterministic
	 iteration and freshness timestamps.
3. Inspect `runs/live/reg_cli/0007-regression-smoke/artifacts/equity_curve.csv`; each timestamp is
	 spaced exactly one minute, proving the fixed `MockTimeProvider` clock.
4. For CCXT/Alpaca dry-runs, ensure `adapter_logs.jsonl` records credential validation events
	 without outbound network requests.

---

## Guard Simulations *(FR-004 · SC-002)*
The runner evaluates guardrails in the following order each loop:
1. **Notional & position limits** — `RiskLimits.max_notional`, `RiskLimits.max_position`.
2. **Per-symbol caps** — `RiskLimits.symbol_position_limits`.
3. **Drawdown breaker** — `RiskLimits.max_drawdown_bps` compared against session peak equity.
4. **Consecutive rejects** — halts after `RiskLimits.max_consecutive_rejects` failures.
5. **Stale data** — aborts when the clock gap exceeds `RiskLimits.stale_data_threshold_s`.
6. **Kill switch** — exits once the configured file exists (touch to trigger).

**Simulation recipes**
- Run `pytest tests/test_risk.py -q` — covers each guard with deterministic fixtures.
- Manual kill-switch drill: launch the runner in paper mode, then `touch /tmp/logos.kill` and watch
	`session.md` record `kill_switch_triggered` while `state.jsonl` logs the structured event.
- Stale data rehearsal: set `--risk.stale-data-threshold-s 1` and pause the feed generator; the loop
	halts within 5 seconds.
- Drawdown rehearsal: configure `--risk.max-dd-bps 10` and replay a scenario with known loss (see
	`tests/fixtures/live/risk_drawdown/`).

---

## Recovery Playbook *(FR-005)*
1. When the runner halts, note the last log line in `runs/live/sessions/<session_id>/session.md`.
2. Review `state.json` to confirm `positions`, `equity`, and `last_bar_iso` align with expectations.
3. Restart with the same CLI arguments; the runner reloads FIFO inventory and resumes from the
	 persisted bar timestamp.
4. Validate no duplicate trades by diffing the tail of `orders.csv`/`trades.csv` before and after
	 restart (`tail -n 20`).

---

## Artifact Bundle Verification *(FR-006)*
- Required files per session:
	- `orders.csv`, `trades.csv`, `positions.csv`, `account.csv`
	- `state.json`, `state.jsonl`
	- `session.md`, `logs/run.log`
- Use `python -m logos.live.artifacts` (see module docstring) to read and normalize CSVs.
- Cross-reference checksums with `docs/PHASE2-ARTIFACTS.md` whenever baselines change.

---

## Adapter Dry-Run Matrix *(FR-007)*
- CCXT rehearsal:
	```bash
	python -m logos.live.regression --adapter-mode adapter --adapter ccxt \
		--label ccxt-dry-run --seed 7 \
		--dataset tests/fixtures/live/regression_default \
		--output-dir runs/live/reg_cli
	```
	Expect `adapter_logs.jsonl` containing credential validation events only.
- Alpaca rehearsal (same structure, `--adapter alpaca`).
- IB remains documented as a stub; see `logos/live/broker_ib.py` for current placeholders.

---

## Environment Guards *(FR-008 · SC-003)*
- Default `.env.example` ships with `LIVE_DISABLE_NETWORK=1`; keep that flag for CI and local tests.
- `pytest -q` and the regression CLI operate purely on fixtures — the repo contains no network calls
	when this flag is set.
- Run `ruff check .` followed by `black --check .`; legacy formatting debt is tracked in
	`CHANGELOG.md` under Known Limitations.
- Type checks: install stubs (`pip install pandas-stubs types-PyYAML`) before running `mypy .`.
- Seed reproducibility: export `LOGOS_SEED=7` (or another integer) before invoking the regression CLI to align with the documented baselines and the window bounds stored in provenance.

---

## Timeline Expectations *(SC-001)*
- **< 5 minutes** — Run config validation, launch deterministic regression harness, compare
	checksums against documented values.
- **< 10 minutes** — Execute guard rehearsals (kill switch + stale data) and restart using
	`state.json`.
- **< 15 minutes** — Iterate through CCXT and Alpaca dry-runs, capturing adapter logs for review.

---

## Baseline Governance & Refresh
1. Request a review issue describing proposed baseline change (paper + adapters).
2. Share checksum diffs from `docs/PHASE2-ARTIFACTS.md` and attach regression CLI output.
3. Once approved, refresh via:
	 ```bash
	 python -m logos.live.regression --refresh-baseline --confirm-refresh \
		 --dataset tests/fixtures/live/regression_default --seed 7
	 ```
4. Update `tests/fixtures/regression/smoke/`, adjust `docs/PHASE2-ARTIFACTS.md`, and log the change
	 in `CHANGELOG.md`.

---

## Reference Evidence *(FR/SC Traceability)*
- `tests/test_live_runner.py`, `tests/test_live_regression.py` — integration coverage.
- `tests/test_live_dry_run_adapters.py` — dry-run behaviour for CCXT/Alpaca.
- `docs/PHASE2-ARTIFACTS.md` — artifact index & checksums.
- `README.md` — window primer, indexing contract, QA stack, acceptance matrix.
