# Phase 2 quality polish helpers

.RECIPEPREFIX := >
PYTHON_BIN ?= $(shell if [ -x .venv/bin/python ]; then echo .venv/bin/python; elif command -v python3 >/dev/null 2>&1; then command -v python3; else command -v python; fi)

.PHONY: phase2-qa phase2-smoke phase2-refresh-smoke phase2-refresh-matrix phase5-smoke phase6-smoke

# Run local QA stack quickly
phase2-qa:
>@echo "== Lint/type/tests + smoke =="
>$(PYTHON_BIN) -m ruff check .
>$(PYTHON_BIN) -m black --check .
>$(PYTHON_BIN) -m mypy .
>$(PYTHON_BIN) -m pytest -q
>LOGOS_OFFLINE_ONLY=1 LIVE_DISABLE_NETWORK=1 MPLBACKEND=Agg TZ=UTC $(PYTHON_BIN) -m logos.live.regression \
>  --adapter-mode paper \
>  --label regression-smoke \
>  --seed $${SEED:-7} \
>  --dataset tests/fixtures/live/regression_default \
>  --output-dir runs/live/reg_cli

# Run the smoke regression (seed=7 by default)
phase2-smoke:
>LOGOS_OFFLINE_ONLY=1 LIVE_DISABLE_NETWORK=1 MPLBACKEND=Agg TZ=UTC $(PYTHON_BIN) -m logos.live.regression \
>  --adapter-mode paper \
>  --label regression-smoke \
>  --seed $${SEED:-7} \
>  --dataset tests/fixtures/live/regression_default \
>  --output-dir runs/live/reg_cli

# Refresh smoke baselines (idempotent, logs seed and baseline)
phase2-refresh-smoke:
>bash scripts/phase2/refresh-baselines.sh --smoke --seed $${SEED:-7}

# Refresh full regression matrix (extend as new fixture suites are added)
phase2-refresh-matrix:
>bash scripts/phase2/refresh-baselines.sh --matrix --seed $${SEED:-7}
>bash scripts/phase2/refresh-baselines.sh --matrix --seed $${SEED:-7}

# Phase 5 research smoke: walk-forward + tuning CLI runs on fixtures
phase5-smoke:
>LOGOS_OFFLINE_ONLY=1 MPLBACKEND=Agg TZ=UTC $(PYTHON_BIN) -m logos.research.walk_forward \
>  momentum AAPL 2022-01-03 2022-07-01 \
>  --interval 1d \
>  --asset-class equity \
>  --params fast=8 slow=24 \
>  --window-size 120 \
>  --train-fraction 0.6 \
>  --min-oos-sharpe -5.0 \
>  --max-oos-drawdown -1.0 \
>  --allow-synthetic \
>  --output-dir runs/research/_ci/walk_forward_smoke
>LOGOS_OFFLINE_ONLY=1 MPLBACKEND=Agg TZ=UTC $(PYTHON_BIN) -m logos.research.tune \
>  momentum AAPL 2022-01-03 2022-07-01 \
>  --interval 1d \
>  --asset-class equity \
>  --grid fast=8,12 slow=24 \
>  --oos-fraction 0.25 \
>  --min-oos-sharpe -5.0 \
>  --max-oos-drawdown -1.0 \
>  --missing-data-stride 10 \
>  --top-n 2 \
>  --allow-synthetic \
>  --output-dir runs/research/_ci/tuning_smoke

# Phase 6 portfolio risk smoke: allocator + overlay sanity check
phase6-smoke:
>LOGOS_OFFLINE_ONLY=1 MPLBACKEND=Agg TZ=UTC $(PYTHON_BIN) -m logos.portfolio.smoke