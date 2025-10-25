# CHANGELOG

## 2025-10-25 — Phase 10 Deployment & Ops

### Highlights
- Introduced docker-compose stack with services for the runner, monitoring loop, scheduled backups, and janitor cleanup (`deploy/docker-compose.yml`).
- Added operational scripts for backups, restores, janitorial retention, and monitoring (`scripts/ops/`).
- Published deployment runbook (`docs/OPS.md`) detailing compose workflows, alerting thresholds, and drill procedures.

### Known Limitations
- Monitoring relies on webhook endpoints; operators must supply the integration and rotate secrets externally.
- Backup cadence defaults to daily archives; adjust intervals for higher-frequency trading workloads if storage budget allows.

## 2025-10-25 — Phase 11 ML Augmentation (Offline, Gated)

### Highlights
- Added offline advisory modules for regime detection, volatility forecasting, meta allocation, and drift monitoring under `logos/ml/`.
- Established human-in-the-loop promotion helpers that stamp approver metadata before any advisory output can influence live systems.
- Authored the ML augmentation playbook (`docs/ML_AUGMENTATION.md`) and accompanying unit tests (`tests/unit/ml/`) to satisfy the gated rollout requirements.

### Known Limitations
- Thresholds for regime, PSI, and z-score alerts are heuristic and should be reviewed quarterly against fresh walk-forward evidence.
- Meta allocator state currently tracks approvals in-memory; persist the ledger before integrating with orchestration tooling.

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
