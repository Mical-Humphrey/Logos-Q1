# Implementation Plan: Phase 3 — Quickstart, Configure, Doctor, Status

**Branch**: `[002-quickstart]` | **Date**: 2025-10-24 | **Spec**: specs/002-quickstart/spec.md  
**Input**: Feature specification from `/specs/002-quickstart/spec.md`

## Summary
Add a delightful, safe onboarding: `logos quickstart`, `logos configure`, `logos doctor`, and `logos status` (read-only). All flows operate offline using deterministic fixtures and produce artifacts under `runs/`.

## Technical Context
**Language/Version**: Python 3.10, 3.11  
**Primary Dependencies**: standard library + existing project deps; optional `rich` for nicer CLI output (defer if it risks CI time).  
**Storage**: SQLite orders store (WAL already configured)  
**Testing**: pytest -q; CLI contract tests; offline fixtures  
**Target Platform**: Linux (CI), Windows optional  
**Project Type**: CLI + library  
**Performance Goals**: ≤10 minutes TTF; CI smoke ≤7 minutes  
**Constraints**: Offline-only default; read-only status; no new artifact roots

## Constitution Check
- Deterministic: fixtures + seeds; no network.
- Safety: paper only; live flags unchanged.
- Read-only UI: status has no write actions.
- Tests & Docs: add CLI contract tests; add docs/QUICKSTART.md.
- Clear paths: only `runs/` and `logos/logs/`.

## Implementation Steps

1) CLI Entrypoints (skeleton + plumbing)
- Add subcommands under `logos/cli/`:
  - quickstart: generate defaults → run short paper session using fixture feed (e.g., `tests/fixtures/live/regression_default`).
  - configure: interactive prompts (exchange, asset class, symbol/pair, timeframe, risk caps) → write `.env` or config file (idempotent).
  - doctor: checks (Python version, write perms to runs/, disk %, time sync, SQLite WAL, retention env flags).
  - status: read-only view from `runs/live/sessions/<id>/` (equity, PnL, positions, last signal, health flags).
- Ensure commands accept `--offline` and respect `LOGOS_OFFLINE_ONLY=1`.

2) Strategy and Explain hook
- Ensure the default preset strategy exposes `explain()` so quickstart can print "why we traded."

3) Fixtures and deterministic session
- Use FixtureReplayFeed for BTC-USD 1m fixture; ensure at least one trade occurs during a short run.
- Add/adjust fixtures only if needed for deterministic trade placement.

4) Tests (CLI contract)
- quickstart: asserts exit=0, creates session dir, produces at least one filled order, prints "why we traded".
- doctor: simulate a failure (e.g., retention enabled without quotas) → non-zero exit and actionable message.
- status: prints expected fields; no write actions invoked.

5) Docs + CI
- docs/QUICKSTART.md: step-by-step onboarding and troubleshooting.
- CI: add a `phase3-quickstart.yml` smoke (lint/type/tests + quickstart smoke). Keep ≤7 minutes.

## Done Criteria
- quickstart/doctor/status/ configure work offline; tests pass.
- CI green with new quickstart smoke.
- docs/QUICKSTART.md present and accurate.
- TTF ≤10 minutes validated on a clean environment.

## Structure
- New: `logos/cli/{quickstart.py,configure.py,doctor.py,status.py}`
- New: `docs/QUICKSTART.md`
- Tests: `tests/contract/test_cli_phase3.py`
