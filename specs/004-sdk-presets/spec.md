# Feature Specification: Phase 4 — Strategy SDK v1 + Presets

**Feature Branch**: `[004-sdk-presets]`  
**Created**: 2025-10-24  
**Status**: Draft  
**Input**: “Ship a simple, safe Strategy SDK with explainable presets for equities/crypto/forex, runnable offline.”

## User Scenarios & Testing (mandatory)

### User Story 1 — Strategy SDK Contract (P1)
As a developer, I implement strategies via a clear interface and run them end-to-end offline.

- Independent Test:
  - A minimal example strategy implementing the interface runs in backtest and paper (fixture feed) without network.
- Acceptance:
  1. Interface includes: `fit()`, `predict()`, `generate_order_intents()`, `explain(last_ctx)->dict`.
  2. Deterministic behavior given seed and fixture inputs.
  3. No writes outside `runs/` and `logos/logs/`.

### User Story 2 — Presets (P1)
As a user, I can select one of three presets with safe defaults.

- Presets:
  - Mean Reversion (MR)
  - Momentum/Breakout (MOMO)
  - Simple Carry (CARRY; per-asset proxy where applicable)
- Independent Test:
  - Each preset backtests and runs a short paper session using fixtures and emits at least one trade.

### User Story 3 — Explainability (P1)
As a learner, I can see “why we traded” after each action.

- Independent Test:
  - `explain()` returns structured fields (e.g., signal value, thresholds, risk note) used by status/tutorial.

### User Story 4 — Sanity & Guards (P2)
As an operator, I get guardrails that prevent bad configs (NaNs, unbounded exposure).

- Independent Test:
  - Runs fail closed on NaNs/missing data; exposure caps enforced in backtests/paper.

### Edge Cases
- Empty/short datasets → no trades, clear reason in explain.
- All-NaN indicators → fail closed with actionable error.
- Parameter bounds (e.g., lookback >= 2).

## Determinism, Safety & Compliance (mandatory)

### Reproducibility & Deterministic Execution
- Fixtures only; seeds explicit; consistent outputs across runs.

### Live Trading Safety
- Paper-only paths; no change to live toggles or risk settings.

### Streamlit UI Accessibility & Performance
- N/A (no UI changes). `explain()` is for status/tutorial consumption.

### Documentation & Artifact Updates
- Add brief HOWTO (README snippet or docs/SDK_PRESETS.md).
- Artifacts: logs to `logos/logs/`, runs to `runs/`.

## Requirements (mandatory)

### Functional Requirements
- FR-001: Define Strategy SDK interface and base helpers.
- FR-002: Provide MR, MOMO, CARRY presets with YAML configs and safe defaults.
- FR-003: Implement `explain()` returning structured, minimal JSON-serializable dict.
- FR-004: Add sanity checks (NaN guard, parameter bounds, exposure cap in backtest/paper).
- FR-005: Keep CI ≤ 7 minutes; offline fixtures only.

## Success Criteria (mandatory)
- SC-001: All three presets run E2E (backtest → paper) offline; at least one trade each in fixtures.
- SC-002: `explain()` populated for last trade across presets.
- SC-003: Sanity/guard tests pass; no NaNs or unbounded exposure.
- SC-004: CI remains ≤ 7 minutes.