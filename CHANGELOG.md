# CHANGELOG

## 2025-10-20 — Phase 9 Adapter Hardening

### Highlights
- Added hardened venue adapters for CCXT, Alpaca, and Oanda with shared retry, rate limiting, idempotent caching, and audit logging.
- Introduced adapter unit tests under `tests/unit/adapters/` covering retry semantics, idempotent safeguards, reconciliation drift detection, and cancellation flows.
- Documented the new guard rails and usage guidance in `docs/ADAPTER_HARDENING.md`, linking the module surface area to Phase 9 operational checklists.

### Known Limitations
- Venue classifiers rely on optional third-party SDKs; environments without the libraries fall back to coarse error grouping and require installation before live usage.
- The in-memory idempotent cache currently uses process-local storage; persistence across restarts will be addressed alongside orchestration state sync in a later phase.

## 2025-10-20 — Phase 2 Live Execution Readiness

### Highlights
- Documented deterministic live regression matrix (paper + CCXT + Alpaca) with canonical commands and checksums.
- Published comprehensive live runbook covering translator drills, guard simulations, recovery playbook, and baseline governance.
- Updated manual and README with safety checklist, QA command suite, artifact layout, and requirement traceability matrix (FR-001..FR-008, SC-001..SC-004).
- Captured regression artifacts in `docs/PHASE2-ARTIFACTS.md`, enabling sha256 verification for baselines and rehearsals.

### Known Limitations
- `black --check .` currently flags legacy formatting across 60+ modules; formatting remediation is tracked for Phase 3 to avoid churn during live rollout.
- `mypy .` requires installing `pandas-stubs` and `types-PyYAML`, and several live modules (paper broker, persistence) still report strict typing issues; follow-up tickets cover incremental typing.
- Adapter baselines intentionally diverge from the paper snapshot (zero fills by design); refresh requests must document rationale before updating `tests/fixtures/regression/smoke/`.
