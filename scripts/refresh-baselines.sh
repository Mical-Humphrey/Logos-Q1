#!/usr/bin/env bash
set -euo pipefail

SEED=7
MODE="--smoke" # default
BASELINE_DIR="tests/fixtures/regression/smoke"
SMOKE_DATASET="tests/fixtures/live/regression_default"

usage() {
  echo "Usage: $0 [--smoke|--matrix] [--seed N]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) MODE="--smoke"; shift ;;
    --matrix) MODE="--matrix"; shift ;;
    --seed) SEED="${2:-}"; [[ -z "$SEED" ]] && usage; shift 2 ;;
    *) usage ;;
  esac
done

echo "[phase2] baseline refresh start: seed=${SEED} mode=${MODE}"
echo "[phase2] baseline version: phase2-v1"

# Ensure deterministic environment (no network)
export LOGOS_OFFLINE_ONLY=1

refresh_smoke() {
  echo "[phase2] regenerating smoke artifacts..."
  python -m logos.live.regression --adapter-mode paper \
    --label regression-smoke --seed "${SEED}" \
    --dataset "${SMOKE_DATASET}" \
    --output-dir runs/live/reg_cli

  # Example: copy or update baseline files if your harness does not do it automatically
  # cp -v runs/live/reg_cli/*/metrics.json "${BASELINE_DIR}/metrics.json"
  # cp -v runs/live/reg_cli/*/snapshot.json "${BASELINE_DIR}/snapshot.json"

  echo "[phase2] smoke refresh complete."
}

refresh_matrix() {
  echo "[phase2] regenerating matrix artifacts..."
  # Add more datasets/suites here as they are introduced
  python -m logos.live.regression --adapter-mode paper \
    --label regression-smoke --seed "${SEED}" \
    --dataset "${SMOKE_DATASET}" \
    --output-dir runs/live/reg_cli
  echo "[phase2] matrix refresh complete."
}

if [[ "${MODE}" == "--smoke" ]]; then
  refresh_smoke
else
  refresh_matrix
fi

echo "[phase2] done."