#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

SEED=7
MODE="smoke"

PYTHON_BIN="${PYTHON:-${REPO_ROOT}/.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "[phase2] unable to locate a python interpreter" >&2
    exit 1
  fi
fi

SMOKE_BASELINE="tests/fixtures/regression/smoke"
SMOKE_DATASET="tests/fixtures/live/regression_default"
SMOKE_SYMBOL="AAPL"
SMOKE_LABEL="regression-smoke"
SMOKE_OUTPUT="runs/live/reg_cli"

# Matrix scenarios: name|adapter_mode|adapter_name
# adapter_name is empty for paper mode.
MATRIX_CASES=(
  "trending_up|paper|"
  "trending_up|adapter|alpaca"
  "trending_up|adapter|ccxt"
  "trending_down|paper|"
  "trending_down|adapter|alpaca"
  "trending_down|adapter|ccxt"
  "range_bound|paper|"
  "range_bound|adapter|alpaca"
  "range_bound|adapter|ccxt"
)

symbol_for() {
  case "$1" in
    trending_up) echo "TRENDUP" ;;
    trending_down) echo "TRENDDN" ;;
    range_bound) echo "RANGE" ;;
    *)
      echo "[phase2] unknown scenario '$1'" >&2
      exit 1
      ;;
  esac
}

usage() {
  cat <<'EOF'
Usage: refresh-baselines.sh [--smoke|--matrix] [--seed N]
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --smoke) MODE="smoke"; shift ;;
    --matrix) MODE="matrix"; shift ;;
    --seed)
      SEED="${2:-}"
      [[ -z "${SEED}" ]] && usage
      shift 2
      ;;
    *) usage ;;
  esac
done

echo "[phase2] baseline refresh start: seed=${SEED} mode=${MODE}"
echo "[phase2] baseline version: phase2-v1"

export LOGOS_OFFLINE_ONLY=1
export LIVE_DISABLE_NETWORK=1
export MPLBACKEND=Agg
export TZ=UTC

run_regression_cli() {
  local baseline_dir="$1"
  local dataset_dir="$2"
  local symbol="$3"
  local label="$4"
  local adapter_mode="$5"
  local adapter_name="$6"
  local output_dir="$7"

  mkdir -p "${output_dir}"

  local args=(
    --output-dir "${output_dir}"
    --baseline "${baseline_dir}"
    --dataset "${dataset_dir}"
    --symbol "${symbol}"
    --label "${label}"
    --seed "${SEED}"
    --refresh-baseline
    --confirm-refresh
  )

  if [[ "${adapter_mode}" == "adapter" ]]; then
    args+=(--adapter-mode adapter --adapter "${adapter_name}")
  else
    args+=(--adapter-mode paper)
  fi

  "${PYTHON_BIN}" -m logos.live.regression "${args[@]}"
}

refresh_smoke() {
  echo "[phase2] regenerating smoke artifacts..."
  run_regression_cli \
    "${SMOKE_BASELINE}" \
    "${SMOKE_DATASET}" \
    "${SMOKE_SYMBOL}" \
    "${SMOKE_LABEL}" \
    "paper" \
    "" \
    "${SMOKE_OUTPUT}"
  echo "[phase2] smoke refresh complete."
}

refresh_matrix() {
  echo "[phase2] regenerating matrix artifacts..."
  for case in "${MATRIX_CASES[@]}"; do
    IFS='|' read -r scenario adapter_mode adapter_name <<<"${case}"
    local symbol
    symbol="$(symbol_for "${scenario}")"
    local dataset_dir="tests/fixtures/live/${scenario}"
    local label="phase2-${scenario}-${adapter_mode}"
    local baseline_dir="tests/baselines/phase2/${scenario}/${adapter_mode}"
    local output_dir="runs/live/phase2/${scenario}/${adapter_mode}"

    if [[ "${adapter_mode}" == "adapter" ]]; then
      label="phase2-${scenario}-adapter_${adapter_name}"
      baseline_dir="tests/baselines/phase2/${scenario}/adapter_${adapter_name}"
      output_dir="runs/live/phase2/${scenario}/adapter_${adapter_name}"
    fi

    echo "[phase2] -> scenario=${scenario} mode=${adapter_mode} adapter=${adapter_name:-none}"
    run_regression_cli \
      "${baseline_dir}" \
      "${dataset_dir}" \
      "${symbol}" \
      "${label}" \
      "${adapter_mode}" \
      "${adapter_name}" \
      "${output_dir}"
  done
  echo "[phase2] matrix refresh complete."
}

if [[ "${MODE}" == "smoke" ]]; then
  refresh_smoke
else
  refresh_matrix
fi

echo "[phase2] done."
