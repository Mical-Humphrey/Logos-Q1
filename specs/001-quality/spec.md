# Feature Specification: Phase 2 Quality Polish

**Feature Branch**: `[001-quality]`  
**Created**: 2025-10-24  
**Status**: Draft  
**Input**: User description: "Finalize Phase 2 core quality: seed/baseline lock, baseline refresh automation, smoke CI, and a final QA pass."

## User Scenarios & Testing (mandatory)

### User Story 1 — Canonical Seed & Baseline Freeze (Priority: P1)
As a maintainer, I want a canonical seed and baseline version documented and enforced so regression comparisons are deterministic.

- Independent Test: Running the smoke regression with the documented seed and flags passes with zero diffs and emits BASELINE_VERSION=phase2-v1.
- Acceptance:
  1. Given BASELINE_VERSION=phase2-v1 and seed=7, when I run the smoke command, then artifacts match the committed baseline.
  2. Given no network access, when I run the smoke command, then it succeeds using fixtures only.

### User Story 2 — One-command Baseline Refresh (Priority: P1)
As a maintainer, I want a single script to refresh smoke and full matrix baselines so updates are consistent and auditable.

- Independent Test: Running scripts/phase2/refresh-baselines.sh updates all target baseline files and exits 0; a second run is a no-op.

### User Story 3 — CI Smoke Workflow (Priority: P1)
As a maintainer, I want CI to run lint/type/tests and the smoke regression on Python 3.10/3.11 within 7 minutes.

- Independent Test: The workflow completes < 7 minutes and fails the PR on any regression diff or lint/type/test failure.

### User Story 4 — Final QA Stack (Priority: P2)
As a maintainer, I want a single Makefile target to run the full Phase 2 QA stack locally.

- Independent Test: `make phase2-qa` runs ruff, black --check, mypy, pytest -q, and the smoke regression, returning non-zero on any failure.

### Edge Cases
- Seed change requires full baseline refresh; script must guard and clearly log the seed in use.
- Workflow must be offline-deterministic; no network data downloads permitted.
- Retention and quarantine must not touch active session directories.

## Determinism, Safety & Compliance (mandatory)

### Reproducibility & Deterministic Execution
- All commands run offline using fixtures. Seed is explicit (default 7). Regression harness invoked with fixed label and dataset path.

### Live Trading Safety
- Out of scope for this feature (no live changes). Paper/default-only paths validated via regression harness.

### Streamlit UI Accessibility & Performance
- N/A for this feature.

### Documentation & Artifact Updates
- Update docs/PHASE2-ARTIFACTS.md with seed, baseline version, commands, and expected outputs.

## Requirements (mandatory)

### Functional Requirements
- FR-001: Document and enforce the canonical Phase 2 seed and baseline version.
- FR-002: Provide a single script to refresh smoke and matrix baselines deterministically.
- FR-003: Provide a CI workflow that runs lint/type/tests and the smoke regression on Python 3.10/3.11 under 7 minutes.
- FR-004: Provide Makefile targets to run the Phase 2 QA stack and regression commands locally.
- FR-005: Ensure retention/quarantine exclude active session directories; verify via tests or documented constraints.

## Success Criteria (mandatory)
- SC-001: `make phase2-qa` returns 0 locally; CI workflow is green on main.
- SC-002: Smoke regression matches baseline on seed=7 with no diffs.
- SC-003: Baseline refresh script is idempotent and logs seed and baseline version.
- SC-004: Total CI time ≤ 7 minutes using offline fixtures.