---
description: "Task list for Phase 2 live execution completion"
---

# Tasks: Phase 2 - Live Execution Completion

**Input**: docs/specs/LOGOS-SPEC-0002-phase-2-live-execution-completion.md
**Prerequisites**: plan.md (required), spec.md (required), research.md (existing design notes), sprints.txt

**Tests**: Automated tests are REQUIRED for every feature. Failing-first tests precede implementation.

**Documentation**: Each story MUST include documentation updates (README, MANUAL, LIVE-RUNBOOK) describing the user-facing impact.

## Format: `[ID] [P?] [Sprint] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Sprint]**: SprintA or SprintB alignment for scheduling
- Include exact file paths in descriptions

## Sprint A — Core Loop Completion

### Translator & Metadata

- [ ] T201 [SprintA] Implement symbol metadata registry in `logos/live/metadata.py`
  - Owner: Mical Humphrey
  - Estimate: 1 day
  - Dependencies: Baseline strategy signal outputs
  - Acceptance:
    - Registry defines precision, lot size, and notional caps for BTC-USD, AAPL, DEMO.
    - Unit tests cover metadata lookups and validation errors in `tests/live/test_metadata.py`.
  - Spec: FR-001, US1

- [ ] T202 [P] [SprintA] Quantize strategy signals into `OrderIntent`s in `logos/live/order_intent.py`
  - Owner: Mical Humphrey
  - Estimate: 1 day
  - Dependencies: T201
  - Acceptance:
    - Translator rejects orders violating precision/caps with descriptive errors.
    - Unit tests in `tests/live/test_order_intent.py` cover buy/sell flows and boundary rounding.
  - Spec: FR-001, US1, SC-001

### Paper Broker

- [ ] T203 [SprintA] Implement deterministic fill engine in `logos/live/broker/paper.py`
  - Owner: Mical Humphrey
  - Estimate: 1 day
  - Dependencies: T202
  - Acceptance:
    - Engine simulates maker/taker fills deterministically with seeded randomness.
    - Unit tests in `tests/live/broker/test_paper_fill.py` cover full lifecycle states.
  - Spec: FR-002, US1

- [ ] T204 [P] [SprintA] Add FIFO inventory and PnL computation in `logos/live/broker/inventory.py`
  - Owner: Support Dev
  - Estimate: 0.5 day
  - Dependencies: T203
  - Acceptance:
    - FIFO queue persists across partial fills and cancellations.
    - Unit tests validate realized/unrealized PnL accuracy for multi-leg scenarios.
  - Spec: FR-002, US1

### Deterministic Feeds

- [ ] T205 [SprintA] Build cache replay provider in `logos/live/data/cache_provider.py`
  - Owner: Support Dev
  - Estimate: 1 day
  - Dependencies: None (fixtures available)
  - Acceptance:
    - Provider reads `data/cache/<asset>/` fixtures deterministically with idempotent iteration.
    - Unit tests in `tests/live/data/test_cache_provider.py` verify repeatable sequences.
  - Spec: FR-003, US3, SC-001

- [ ] T206 [P] [SprintA] Implement mocked yfinance/CCXT pollers with freshness logic in `logos/live/data/pollers.py`
  - Owner: Support Dev
  - Estimate: 1 day
  - Dependencies: T205
  - Acceptance:
    - Pollers track freshness timestamps, retry/backoff schedules, and expose telemetry.
    - Tests simulate stale data, retries, and ensure no real network calls (`tests/live/data/test_pollers.py`).
  - Spec: FR-003, US3

### Risk & State

- [ ] T207 [SprintA] Wire risk guards in `logos/live/risk/guards.py`
  - Owner: Support Dev
  - Estimate: 0.75 day
  - Dependencies: T202, T203
  - Acceptance:
    - Unit tests trigger max-notional, exposure, drawdown, stale-data, and kill-switch events.
    - Guard events surface structured messages consumed by runner.
  - Spec: FR-004, US2, SC-002

- [ ] T208 [P] [SprintA] Persist session state in `logos/live/state/persistence.py`
  - Owner: Support Dev
  - Estimate: 0.75 day
  - Dependencies: T203, T207
  - Acceptance:
    - `state.json` and `state.jsonl` contain positions, orders, seed, and timestamps.
    - Restart integration test resumes from persisted state without duplicates.
  - Spec: FR-005, US1, SC-001

### Runner Demo & Artifacts

- [ ] T209 [SprintA] Emit artifact bundle writers in `logos/live/reports/artifacts.py`
  - Owner: Support Dev
  - Estimate: 0.5 day
  - Dependencies: T208
  - Acceptance:
    - Writers produce `orders.csv`, `trades.csv`, `positions.csv`, `account.csv`, `session.md` under `runs/live/sessions/<id>/`.
    - Unit tests confirm schema and deterministic filenames.
  - Spec: FR-006, US1, SC-001

- [ ] T210 [P] [SprintA] Integrate components in `logos/live/runner.py` and demo CLI
  - Owner: Mical Humphrey
  - Estimate: 1 day
  - Dependencies: T202-T209
  - Acceptance:
    - `python -m logos.live trade --paper --fixtures` completes using deterministic inputs.
    - Integration test in `tests/live/test_runner_integration.py` validates restart and guard triggers.
  - Spec: FR-004, FR-005, FR-006, US1, US2, SC-001, SC-002

## Sprint B — Adapters & Polish

### Adapters & Validator

- [ ] T301 [SprintB] Implement CCXT dry-run adapter in `logos/live/adapters/ccxt_adapter.py`
  - Owner: Support Dev
  - Estimate: 1 day
  - Dependencies: Sprint A completion
  - Acceptance:
    - Adapter validates credentials, logs redacted configuration, and never sends orders.
    - Unit tests mock CCXT responses and verify error handling.
  - Spec: FR-007, US3, SC-002

- [ ] T302 [P] [SprintB] Implement Alpaca dry-run adapter in `logos/live/adapters/alpaca_adapter.py`
  - Owner: Support Dev
  - Estimate: 1 day
  - Dependencies: T301
  - Acceptance:
    - Adapter confirms paper trading keys and surfaces actionable messages on failure.
    - Tests mock API responses and ensure no live endpoints are hit.
  - Spec: FR-007, US3

- [ ] T303 [SprintB] Update config validator in `logos/config_validate.py`
  - Owner: Mical Humphrey
  - Estimate: 0.5 day
  - Dependencies: T301, T302
  - Acceptance:
    - Validator blocks unsafe toggles, missing credentials, or live mode without acknowledgment.
    - Unit tests cover failure modes and success paths with mocked env vars.
  - Spec: FR-004, FR-007, US2

### Reporting & Documentation

- [ ] T304 [SprintB] Enhance session markdown summary in `logos/live/reports/session_md.py`
  - Owner: Support Dev
  - Estimate: 0.5 day
  - Dependencies: T209
  - Acceptance:
    - Summary includes guard activations, seed, final PnL, and path to artifacts.
    - Unit tests render markdown and assert required sections.
  - Spec: FR-006, SC-002, SC-004

- [ ] T305 [P] [SprintB] Refresh documentation (README, MANUAL, LIVE-RUNBOOK)
  - Owner: Mical Humphrey
  - Estimate: 1 day
  - Dependencies: T210, T304
  - Acceptance:
    - Updated docs describe safety checklist, deterministic workflow, restart playbook.
    - Documentation review checklist signed off.
  - Spec: Documentation & Artifact Updates, SC-004

### CI Hardening

- [ ] T306 [SprintB] Ensure offline regression suite defaults in `pyproject`/CI configs
  - Owner: Support Dev
  - Estimate: 0.5 day
  - Dependencies: T205-T210
  - Acceptance:
    - CI or local scripts set environment flags to disable network usage.
    - Smoke tests confirm adapters and feeds rely on fixtures only.
  - Spec: FR-008, SC-003

- [ ] T307 [P] [SprintB] Add risk rehearsal scripts under `scripts/live/`
  - Owner: Mical Humphrey
  - Estimate: 0.5 day
  - Dependencies: T207, T210
  - Acceptance:
    - Scripts trigger each guard and capture output logs for reviewers.
    - Docs reference scripts in safety checklist.
  - Spec: FR-004, SC-002, SC-004

## Dependencies & Execution Order

- Sprint A tasks T201-T210 complete before Sprint B starts.
- Translator (T202) precedes broker (T203) and risk wiring (T207).
- Artifact writers (T209) depend on state persistence (T208).
- Adapters (T301, T302) rely on deterministic feeds and runner integration being stable.

## Verification

- Each task includes failing-first tests; integration demos recorded in `/runs/live/sessions/`.
- Constitution gates rechecked before closing Sprint B.
