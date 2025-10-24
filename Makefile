# Phase 2 quality polish helpers

.PHONY: phase2-qa phase2-smoke phase2-refresh-smoke phase2-refresh-matrix

# Run local QA stack quickly
phase2-qa:
\t@echo "== Lint/type/tests + smoke =="
\truff check .
\tblack --check .
\tmypy .
\tpytest -q

# Run the smoke regression (seed=7 by default)
phase2-smoke:
\tpython -m logos.live.regression --adapter-mode paper \\
\t  --label regression-smoke --seed $${SEED:-7} \\
\t  --dataset tests/fixtures/live/regression_default \\
\t  --output-dir runs/live/reg_cli

# Refresh smoke baselines (idempotent, logs seed and baseline)
phase2-refresh-smoke:
\tbash scripts/phase2/refresh-baselines.sh --smoke --seed $${SEED:-7}

# Refresh full regression matrix (extend as new fixture suites are added)
phase2-refresh-matrix:
\tbash scripts/phase2/refresh-baselines.sh --matrix --seed $${SEED:-7}