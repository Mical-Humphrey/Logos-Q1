# Implementation Plan: Phase 2 - Live Execution Completion

**Branch**: `001-complete-live-loop` | **Date**: 2025-10-20 | **Spec**: [docs/specs/LOGOS-SPEC-0002-phase-2-live-execution-completion.md](../specs/LOGOS-SPEC-0002-phase-2-live-execution-completion.md)
**Input**: Feature specification from `/docs/specs/LOGOS-SPEC-0002-phase-2-live-execution-completion.md`

**Note**: This plan aligns with the Phase 2 roadmap captured in `sprints.txt` and replaces prior placeholders.

## Summary

Deliver a deterministic, safety-focused paper trading loop: translate strategy signals to
`OrderIntent`s, finish the paper broker (deterministic fills, FIFO inventory, PnL), add deterministic
minute-bar feeds with freshness/retry, enforce risk guards, persist state for restart, emit the full
artifact bundle, validate CCXT/Alpaca adapters in dry-run mode, and update documentation while
keeping the regression suite offline-viable.

## Technical Context

**Language/Version**: Python 3.11 (existing project baseline)  
**Primary Dependencies**: pandas, numpy, CCXT, yfinance (mocked for tests)  
**Storage**: Local filesystem under `data/`, `runs/`, `logos/logs/`  
**Testing**: pytest with fixtures located in `tests/` and `input_data/` (being migrated to `data/`)  
**Target Platform**: Linux server / developer workstations  
**Project Type**: Single project (CLI + library)  
**Performance Goals**: Session artifact generation completes within 2 minutes of run completion  
**Constraints**: Zero external network dependency during CI; deterministic outputs for reproducible
demos  
**Scale/Scope**: Single-operator paper sessions with future path to live brokers

## Constitution Check

- **Reproducible & Deterministic by Default**: Fixtures stored under `data/cache/` will back all
  minute-bar replay; shared seeds recorded in `session.md`; CI enforces offline execution.
- **Safety First for Live Trading**: Paper-first rehearsals with guard triggers, config validator
  gating unsafe runs, and no live toggles added in this phase.
- **Read-Only Trading UI**: No UI mutations introduced; outputs remain read-only artifacts consumed by
  the existing Streamlit dashboard (not modified here).
- **Tests & Docs for Every Feature**: Each sprint includes failing-first tests and documentation
  updates for README, MANUAL, and LIVE-RUNBOOK.
- **Clear Artifact Paths**: Artifacts limited to `runs/`, caches in `data/cache/`, logs in
  `logos/logs/`; plan includes validation of `logos.paths.ensure_dirs()` usage.
- **Accessible & Fast Streamlit UI**: N/A beyond ensuring generated artifacts remain structured and
  performant for dashboard consumption; no UI changes proposed.

## Project Structure

### Documentation (this feature)

```
docs/specs/LOGOS-SPEC-0002-phase-2-live-execution-completion.md
└── checklists/requirements.md

docs/plans/phase-2-plan.md

docs/tasks/phase-2-live-execution-tasks.md (to be produced)
```

### Source Code (repository root)

```
logos/
├── cli.py
├── live/
│   ├── adapters/
│   ├── broker/
│   ├── data/
│   ├── risk/
│   ├── state/
│   └── runner.py
├── paths.py
└── strategies/

runs/
└── live/sessions/

data/
└── cache/
```

**Structure Decision**: Continue with single-repository layout; augment existing `logos.live`
packages, add deterministic fixtures under `data/cache/`, and ensure documentation resides in
`docs/`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| None | N/A | N/A |

## Sprint Breakdown

### Sprint A — Core Loop Completion (5 developer-days)

**Objective**: Complete deterministic paper execution loop covering translator, broker, feeds, risk
wiring, state persistence, and end-to-end demo.

**Scope**:
- Implement strategy-to-order translator with metadata registry and quantization.
- Finish paper broker deterministic fill engine, FIFO inventory, and PnL tracking.
- Build deterministic minute-bar feeds with cache replay, freshness tracking, and retry/backoff.
- Wire risk/circuit breakers into the runner with exhaustive unit coverage.
- Persist `state.json`/`state.jsonl`, reconcile open orders, and write artifact bundle.
- Demonstrate an end-to-end paper session using fixtures.

**Deliverables**:
- Translator, broker, feed, risk, and state modules with unit tests.
- CLI integration producing artifacts in `runs/live/sessions/<id>/` and logs in `logos/logs/`.
- Recorded demo notes validating restart and guard triggers.

**Acceptance Criteria**:
- Translator quantizes orders correctly for BTC-USD, AAPL, and DEMO assets with tests.
- Paper broker tests cover new, partial, filled, cancelled lifecycle paths and FIFO PnL.
- Feed tests replay fixtures deterministically and handle stale/partial cache cases.
- Integration run produces artifact bundle and restarts cleanly from `state.json`.
- Risk unit tests exercise notional, exposure, drawdown, stale-data, and kill-switch guards.

**Risks & Mitigations**:
- *Risk*: Fixture size slows tests -> *Mitigation*: use trimmed datasets and parameterized tests.
- *Risk*: Risk guard race conditions -> *Mitigation*: add structured events and deterministic
  ordering in tests.

**Owners**: Mical Humphrey (translator, broker), Support Dev (feeds, risk, state)  
**Estimates**: 5 developer-days (translator: 1, broker: 1.5, feeds: 1, risk: 0.75, state/artifacts: 0.75)

### Sprint B — Adapters & Polish (4 developer-days)

**Objective**: Harden adapters, documentation, and CI to close Phase 2 definition of done.

**Scope**:
- Implement CCXT and Alpaca dry-run adapters with credential validation and actionable errors.
- Document IB as a stub with clear follow-up tasks.
- Expand reporting (session markdown summaries) and ensure config validator enforces safety toggles.
- Refresh README, MANUAL, and LIVE-RUNBOOK to describe live workflow, safety checklist, recovery.
- Harden tests/CI: offline default, adapter fixtures, coverage for docs.

**Deliverables**:
- Adapter modules with dry-run validation routines and unit tests.
- Updated docs plus changelog summarizing Phase 2 completion.
- CI guidance or scripts ensuring offline regression path.

**Acceptance Criteria**:
- CCXT and Alpaca adapters confirm credentials using mocked responses and never send orders.
- Config validator blocks missing credentials or unsafe toggles and surfaces actionable errors.
- Session markdown includes summary table of guard activations and seeds.
- Documentation and runbook sections updated with safety checklist and restart steps.
- Offline regression suite passes with adapter fixtures and no network I/O.

**Risks & Mitigations**:
- *Risk*: Adapter APIs change -> *Mitigation*: abstract credential checks behind stable interface and
  freeze on recorded fixtures.
- *Risk*: Documentation drift -> *Mitigation*: pair doc updates with acceptance review checklist.

**Owners**: Support Dev (adapters, CI), Mical Humphrey (docs, validator)  
**Estimates**: 4 developer-days (adapters: 1.5, validator/reporting: 1, docs/runbook: 1, CI hardening: 0.5)

## Timeline & Dependencies

- Sprint A: Oct 21 - Oct 25, 2025
- Sprint B: Oct 27 - Oct 30, 2025
- Dependency: Translator relies on existing strategy signal outputs; adapters depend on Sprint A
  finishing deterministic feeds and risk wiring.

## Review & Sign-off

- Reviewers: Project maintainers and risk officer
- Sign-off Criteria: Sprint demos, passing offline regression suite, documentation review checklist

## Status Tracking

Progress monitored via `/sprints.txt` updates and `/runs/` artifact inspection after each rehearsal.
