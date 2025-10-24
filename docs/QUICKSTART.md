# Logos Quickstart Guide

Welcome! This guide walks you through the Phase 3 onboarding commands that ship with Logos. The flow stays fully offline and produces deterministic paper sessions so you can explore the platform safely.

## Prerequisites

- Python 3.10 or 3.11
- Dependencies installed (`pip install -r requirements.txt -r requirements/dev.txt`)
- No live exchange keys required; everything runs on fixtures

Add the project root to your `PATH` (or invoke with `python -m logos.cli`). The CLI automatically guards outbound network access when `LOGOS_OFFLINE_ONLY=1`.

## Step 1 — Configure (optional)

`logos configure` writes `.env` defaults that the other commands reuse. The wizard prompts for:

- Symbol / asset class / interval
- Paper trading risk guard rails (notional, fee assumptions)
- Offline flag (`LOGOS_OFFLINE_ONLY`)

Re-running the wizard is safe; the file updates idempotently. To script answers, export environment variables beforehand (e.g. `SYMBOL=BTC-USD LOGOS_OFFLINE_ONLY=1 logos configure --non-interactive`).

## Step 2 — Quickstart Session

`logos quickstart` runs a short paper session with deterministic BTC-USD 1 minute bars:

```
LOGOS_OFFLINE_ONLY=1 logos quickstart
```

Outputs land under `runs/live/sessions/<run-id>/` and include:

- `snapshot.json`: account, positions, fills, and configuration
- `artifacts/metrics.json`: Sharpe, exposure, and curve stats
- `session.md`: human summary with an explanation of the first trade
- `provenance.json`: when/where the artifacts originated

The command also updates `runs/live/latest` to point at the newest session.

### Customising Quickstart

Flags let you tune the deterministic run without breaking reproducibility:

- `--lookback` and `--z-entry` adjust the mean reversion trigger
- `--notional` and `--fee-bps` control trade size and costs
- `--fixture` selects an alternate fixture directory if you add one under `tests/fixtures/live/`

## Step 3 — Doctor Checks

`logos doctor` validates the local environment and exits non-zero on actionable issues. Example checks:

- Python version (>=3.10)
- Write access to `runs/` and `logos/logs/`
- Disk free space (>=5%)
- System clock drift (<5 seconds)
- SQLite WAL support for the runs directory
- Retention policy safeguards (`LOGOS_RETENTION_MAX_DAYS` when retention enabled)
- Offline flag confirmation when `--offline` is provided

Use `--json` to emit structured results for tooling.

## Step 4 — Status View

`logos status` reads artifacts and prints a snapshot of the latest session:

- Equity, PnL, and Sharpe
- Open positions with sizing
- Last signal (long/short/flat)
- Health flags: offline-only mode, staleness (>1 hour), open positions

Pass `--run-id <id>` or `--path /path/to/session` to inspect older runs. The command never writes to disk.

## Offline & Determinism Notes

- Fixture data lives at `tests/fixtures/live/quickstart_btc/`
- Random seeding uses `env_seed()`; override with `logos quickstart --seed 42`
- All new artifacts remain under `runs/` and `logos/logs/`

## Troubleshooting

- **No trades placed**: raise `--notional` or lower `--z-entry`. The bundled fixture should trade with default parameters.
- **Doctor retention failure**: either disable retention or set `LOGOS_RETENTION_MAX_DAYS` to a positive integer.
- **Status cannot find a run**: ensure `logos quickstart` completed and `runs/live/sessions/` contains artifacts.
- **Permission errors**: run `logos doctor` to spot missing write access; adjust directory ownership or choose an alternate output path via `--output-dir`.

## Next Steps

- Explore additional strategies by editing `.env` defaults and re-running quickstart
- Integrate the CLI commands into CI using `.github/workflows/phase3-quickstart.yml`
- Review generated artifacts in `runs/live/sessions/<run-id>/` for deeper analysis
