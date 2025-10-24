# Implementation Plan: Phase 2 Quality Polish

**Branch**: `[001-quality]` | **Date**: 2025-10-24 | **Spec**: specs/001-quality/spec.md  
**Input**: Feature specification from `/specs/001-quality/spec.md`

## Summary
Finalize Phase 2 core quality by freezing the canonical seed and baseline version, automating baseline regeneration, adding a CI smoke workflow for Python 3.10/3.11 that completes under 7 minutes, and providing a single local QA command.

## Technical Context
**Language/Version**: Python 3.10, 3.11  
**Primary Dependencies**: pytest, ruff, black, mypy (dev); project runtime deps unchanged  
**Storage**: SQLite (orders store) with WAL already configured (no changes here)  
**Testing**: pytest -q using offline fixtures; regression harness invoked via `python -m logos.live.regression`  
**Target Platform**: Linux (CI), developer macOS/Linux ok  
**Project Type**: single repository (CLI tools + library)  
**Performance Goals**: CI ≤ 7 minutes (cold)  
**Constraints**: Offline only; deterministic artifacts; no network calls  
**Scale/Scope**: Smoke + matrix baselines (fixtures only)

## Constitution Check
- Reproducible & Deterministic: Seed pinned; fixtures only; commands scripted.
- Safety First (Live): No live paths touched; regression/paper only.
- Read-Only UI: N/A.
- Tests & Docs: CI adds enforcement; docs/PHASE2-ARTIFACTS.md added.
- Clear Artifact Paths: Outputs to runs/ and tests/fixtures/regression/… only.
- Accessibility/Performance: N/A.

## Project Structure
Adds:
- specs/001-quality/spec.md
- specs/001-quality/plan.md
- docs/PHASE2-ARTIFACTS.md
- scripts/phase2/refresh-baselines.sh
- .github/workflows/phase2-smoke.yml
- Makefile (or extends existing) with phase2 targets

## Implementation Steps
1. Docs: Add docs/PHASE2-ARTIFACTS.md with seed=7 and BASELINE_VERSION=phase2-v1.
2. Script: Add scripts/phase2/refresh-baselines.sh to regenerate smoke/matrix baselines deterministically.
3. Makefile: Add targets phase2-qa, phase2-smoke, phase2-refresh-smoke, phase2-refresh-matrix.
4. CI: Add .github/workflows/phase2-smoke.yml with Python 3.10/3.11 matrix; lint/type/tests; pytest -q; optional smoke step if tests don’t already cover it.
5. Final QA: Run `make phase2-qa`; if green, merge the feature.

## Done Criteria
- Docs present and accurate; CI green on PR and main; smoke regression matches baseline with seed=7; refresh script idempotent.
