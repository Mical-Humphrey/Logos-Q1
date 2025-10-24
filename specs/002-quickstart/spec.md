# Feature Specification: Phase 3 — Quickstart, Configure, Doctor, Status

**Feature Branch**: `[002-quickstart]`  
**Created**: 2025-10-24  
**Status**: Draft  
**Input**: "Deliver a ≤10-minute guided first-run: quickstart, configure wizard, doctor checks, and a read-only status surface."

## User Scenarios & Testing (mandatory)

### User Story 1 — Quickstart to First Paper Trade (P1)
As a new user, I can run `logos quickstart` and see a paper trade placed using deterministic fixtures within 10 minutes.

- Independent Test:
  - Offline: `LOGOS_OFFLINE_ONLY=1`.
  - Command: `logos quickstart`.
  - Outcome: run directory created under `runs/live/sessions/<id>/`, at least one filled order, status shows PnL and last signal.
- Acceptance:
  1. Uses a default crypto preset (BTC-USD, 1m) with a deterministic fixture feed.
  2. Writes only to `runs/` and `logos/logs/`; no network calls.
  3. Prints "why we traded" from strategy explain() contract.

### User Story 2 — Configure Wizard (P1)
As a user, I can run `logos configure` to set exchange/asset/timeframe/risk in an interactive flow that writes a config file.

- Independent Test:
  - Command: `logos configure`.
  - Outcome: `.env` and/or config file updated; re-running `logos quickstart` consumes these settings.

### User Story 3 — Doctor (P1)
As a user, I can run `logos doctor` to diagnose environment problems and get actionable fixes.

- Independent Test:
  - Simulate issues (e.g., missing write permissions, low disk).
  - Outcome: clear error messages; non-zero exit on failures; suggested commands to remediate.

### User Story 4 — Status (Read-only) (P2)
As a user, I can run `logos status` to view current paper session equity, PnL, open positions, last signal, and health flags.

- Independent Test:
  - While a paper session is running, `logos status` shows live metrics sourced only from `runs/` artifacts.

### Edge Cases
- Missing `.env` → quickstart creates defaults.
- Retention disabled by default; doctor warns if enabled without quotas.
- Windows optional; Linux primary target. Status falls back to plain text if TTY features unavailable.

## Determinism, Safety & Compliance (mandatory)

### Reproducibility & Deterministic Execution
- All first-run flows rely on fixture feeds; seeds fixed via shared helpers. No network in CI or quickstart.

### Live Trading Safety
- quickstart always uses paper mode; live requires explicit flags and is out of scope here.

### Streamlit UI Accessibility & Performance
- N/A (status is CLI/TUI and read-only; the dashboard remains separate and read-only).

### Documentation & Artifact Updates
- Add docs/QUICKSTART.md with step-by-step instructions and troubleshooting.
- No new artifact roots; outputs remain under `runs/` and `logos/logs/`.

## Requirements (mandatory)

### Functional Requirements
- FR-001: Provide `logos quickstart` that runs a short deterministic paper session and exits successfully.
- FR-002: Provide `logos configure` interactive wizard that writes config safely.
- FR-003: Provide `logos doctor` with actionable checks and non-zero exit on failures.
- FR-004: Provide `logos status` read-only view backed by `runs/` artifacts.
- FR-005: Keep offline determinism: no network calls in these commands unless explicitly enabled.

## Success Criteria (mandatory)
- SC-001: Fresh environment → quickstart produces a filled paper order in ≤10 minutes.
- SC-002: doctor identifies and explains common problems with fixes.
- SC-003: status shows equity, PnL, open positions, last signal, and health flags without write actions.
- SC-004: CI smoke completes ≤7 minutes (lint/type/tests + quickstart smoke).
