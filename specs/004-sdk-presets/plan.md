# Implementation Plan: Phase 4 — Strategy SDK v1 + Presets

**Branch**: `[004-sdk-presets]` | **Date**: 2025-10-24 | **Spec**: specs/004-sdk-presets/spec.md  
**Input**: Feature specification from `/specs/004-sdk-presets/spec.md`

## Summary
Deliver a stable Strategy SDK interface plus three safe, explainable presets (MR, MOMO, CARRY) that run offline in backtest and paper using fixtures.

## Technical Context
**Language/Version**: Python 3.10, 3.11  
**Primary Dependencies**: numpy, pandas (existing)  
**Storage**: unchanged (SQLite/WAL for orders when in paper)  
**Testing**: pytest -q; contract/unit tests; offline fixtures only  
**Target Platform**: Linux CI; Windows optional  
**Project Type**: library + CLI runners  
**Performance Goals**: CI ≤ 7 minutes  
**Constraints**: Offline-only; seed fixed via shared helpers; no new artifact roots

## Non-goals (explicit)
- No new asset classes, allocators, or risk overlays.
- No live trading behavior changes.
- No tuning/auto-retaining in this phase.

## DoR / DoD
- DoR: Spec approved; fixtures available; seed fixed; CI budget confirmed.
- DoD: Presets run E2E offline; explain() present; guards pass; docs updated; CI green.

## Implementation Steps

1) SDK interface and base helpers
- Add `logos/strategy/sdk.py` with abstract/base classes:
  - Methods: `fit(df)`, `predict(df)->signals`, `generate_order_intents(signals)->intents`, `explain(ctx)->dict`.
  - Helpers: rolling calc utils, NaN guard, bounds validation.

2) Preset strategies with configs
- Add `logos/strategies/mean_reversion.py`, `momentum.py`, `carry.py`.
- Add configs under `configs/presets/{mr.yaml,momo.yaml,carry.yaml}` with safe defaults (timeframe, lookbacks, thresholds, caps).

3) Explain contract
- Standardize explain payload keys (e.g., `reason`, `signal`, `thresholds`, `risk_note`, `params`).
- Emit small JSON-serializable dict; write only via existing runners’ artifact/log surfaces (no new paths).

4) Sanity & guard tests
- Unit tests for:
  - NaN handling → fail closed with clear message.
  - Parameter bounds (e.g., lookback >= 2).
  - Exposure cap respected in backtest/paper runs (simple cap).
- Contract test: presence/shape of `explain()` output.

5) Backtest + paper (fixture) smoke
- Ensure each preset produces ≥1 trade with existing fixture feeds.
- Keep runtime small to stay within CI budget.

6) Docs
- docs/SDK_PRESETS.md: quick HOWTO, preset summaries, config knobs.

## CI / SLO
- Lint/type/tests only; no network; total ≤ 7 min.

## Done Criteria
- Three presets E2E offline.
- explain() populated.
- Guards green.
- CI green; docs landed.

## Structure
- New:
  - `logos/strategy/sdk.py`
  - `logos/strategies/{mean_reversion.py,momentum.py,carry.py}`
  - `configs/presets/{mr.yaml,momo.yaml,carry.yaml}`
  - `docs/SDK_PRESETS.md`
- Tests:
  - `tests/unit/strategy/test_sdk_contract.py`
  - `tests/unit/strategy/test_presets_explain.py`
  - `tests/unit/strategy/test_presets_guards.py`