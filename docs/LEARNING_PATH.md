# Guided Learning Path (Phase 12)

Phase 12 introduces a structured set of quests so new operators can ramp quickly without touching live controls. The flow is intentionally linear; do not advance until each checkpoint is satisfied.

## Quest 1 — Quickstart Foundations
- Read `docs/QUICKSTART.md` and complete the CLI validation drill.
- Launch the Streamlit dashboard (`streamlit run logos/ui/streamlit/app.py`) and load a recent paper run.
- Document observations in the onboarding checklist.

## Quest 2 — Walk-Forward Exploration
- Review `docs/WALK_FORWARD.md` and replicate the sample walk-forward run.
- Use the Phase 11 advisory tools: generate a regime report and volatility envelope for the walk-forward dataset.
- Capture outputs in `runs/<timestamp>/quests/wf/` for audit.

## Quest 3 — Preset Customisation
- Choose a preset bundle (`conservative`, `balanced`, or `aggressive`) and copy it into a personal workspace.
- Modify one parameter (e.g., strategy weight) and rerun paper backtests. Record before/after metrics using the read-only dashboard.
- Log findings in the team wiki, including which preset knobs were touched and why.

## Quest 4 — Dual Strategy Alignment
- Select two uncorrelated strategies from the preset and run simultaneous paper sessions.
- Review drift reports (`logos.ml.drift`) and confirm no triggers fire; if they do, escalate to a reviewer.
- Present the combined portfolio view in the dashboard portfolio tab and capture screenshots for the readiness dossier.

## Accessibility Checklist
- Ensure colour-blind friendly palettes remain selected in Streamlit (`st.set_page_config` is preconfigured).
- Verify keyboard navigation covers the new tabs (`Portfolio`, `Strategies`, `Artifacts`).
- Provide alternative text when sharing screenshots so documentation remains accessible.

Completion of all quests satisfies SC-001 by demonstrating a guided quickstart plus preset tweak in under 15 minutes with appropriate preparatory work.
