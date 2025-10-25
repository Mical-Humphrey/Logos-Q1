<!--
Sync Impact Report
Version change: 0.0.0 → 1.0.0
Modified principles:
- (new) Reproducible & Deterministic by Default
- (new) Safety First for Live Trading
- (new) Read-Only Trading UI
- (new) Tests & Docs for Every Feature
- (new) Clear Artifact Paths
- (new) Accessible & Fast Streamlit UI
Added sections:
- Core Principles (populated)
- Operating Constraints
- Delivery Alignment
Removed sections:
- None
Templates requiring updates:
- ✅ .specify/templates/plan-template.md
- ✅ .specify/templates/spec-template.md
- ✅ .specify/templates/tasks-template.md
Follow-up TODOs:
- none
-->
# Logos-Q1 Constitution

## Core Principles

### Reproducible & Deterministic by Default
- Tests, research notebooks, and command workflows MUST execute without network access; use fixtures under `input_data/` or recorded responses checked into `input_data/cache/`.
- Any stochastic process MUST fix seeds through shared helpers and persist the chosen seeds in run metadata.
- Backtest and live runners MUST accept explicit configuration for data sources to ensure consistent replays.
**Rationale**: Deterministic pipelines keep education and regression results trustworthy and prevent hidden external dependencies from breaking CI or onboarding experiences.

### Safety First for Live Trading
- All strategy changes MUST pass paper trading via `python -m logos.live trade` without `--live` before any real-order attempt.
- Live mode submission MUST require `MODE=live`, `--live`, the acknowledgement `--i-understand "place-live-orders"`, and a documented risk checklist in the PR description; real order dispatch additionally requires `--send-orders`.
- Brokers, risk guards, and kill switches configured in `.env` MUST be validated through `python -m logos.config_validate` prior to live execution.
**Rationale**: Paper-first rehearsals and explicit acknowledgements reduce the risk of accidental capital deployment and keep the educational mission aligned with responsible trading.

### Read-Only Trading UI
- The Streamlit dashboard under `logos/ui/streamlit/` MUST never emit order placement actions, REST calls, or broker credentials.
- UI contributions MUST keep all widgets read-only or analytical; any proposed order control requires a constitution amendment.
- Dashboard data refresh MUST rely on the artifact stores (`runs/`, `logos/logs/`) rather than live broker endpoints.
**Rationale**: Keeping the UI observational enforces a hard separation between monitoring and execution, preventing accidental clicks from dispatching orders.

### Tests & Docs for Every Feature
- Each feature branch MUST land automated tests that exercise the new logic or regressions; acceptable forms include unit, integration, or CLI contract tests.
- Documentation updates (README excerpts, docs HTML sources, or user-facing markdown) MUST accompany behavior changes or new capabilities.
- Pull requests lacking both tests and documentation MUST link an approved waiver granted via governance.
**Rationale**: Tests guard determinism and safety; documentation keeps the learning and operational intent current for students and operators.

### Clear Artifact Paths
- Runtime code MUST write cache files to `data/cache/`, generated datasets to `input_data/`, run outputs to `runs/`, and logs to `logos/logs/`.
- New tools MUST call `logos.paths.ensure_dirs()` before writing artifacts.
- Environment configuration MUST declare any additional artifact roots and obtain approval before use.
**Rationale**: Predictable directories simplify reproducibility, cleanup, and UI ingestion for analytics dashboards.

### Accessible & Fast Streamlit UI
- Dashboard pages MUST meet keyboard navigation and screen-reader compatibility using Streamlit accessibility primitives.
- Initial page load MUST render meaningful content within 2 seconds on the reference development laptop; longer loads require documented profiling.
- Heavy computations MUST use caching or background jobs so the UI remains responsive and read-only.
**Rationale**: Accessibility keeps the educational dashboard inclusive, while performance prevents monitoring blind spots during live operations.

## Operating Constraints

- Configuration changes MUST document their impact on deterministic runs and be paired with updated defaults in `logos/config.py` when appropriate.
- Long-running jobs and schedulers MUST export metrics or summaries into `runs/` so the Streamlit dashboard reflects the latest state.
- Any external integrations (brokers, market data) MUST provide sandbox or replay modes before production credentials are accepted.
- Secrets management MUST stay outside of the repository; `.env.example` serves as the canonical template, and secrets MUST be injected at runtime.

## Delivery Alignment

- Feature plans MUST include a Constitution Check section proving compliance with each principle before implementation begins.
- Specs MUST enumerate deterministic test scenarios, documentation deliverables, and Streamlit accessibility considerations.
- Tasks MUST explicitly cover required tests, documentation updates, and artifact path validation before closing a user story.
- Release notes and runbooks MUST reference the artifact directories and safety workflows when communicating changes.

## Governance

- Amendments require consensus approval from project maintainers plus documentation of the rationale and expected impact in the PR summary.
- Versioning follows semantic rules: major for breaking governance changes, minor for new principles or obligations, patch for clarifications.
- Ratification history and amendment dates MUST remain in this file; each change MUST update the Sync Impact Report.
- Compliance reviews occur during PR approval; reviewers MUST block merges lacking Constitution Check evidence or violating any principle.
- Emergency waivers for live issues expire within 7 days and MUST be documented with mitigation steps.

**Version**: 1.0.0 | **Ratified**: 2025-10-20 | **Last Amended**: 2025-10-20
