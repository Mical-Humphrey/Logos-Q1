#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
DEFAULT_RUNS="${REPO_ROOT}/runs"
DEFAULT_CONFIGS="${REPO_ROOT}/configs"

EFFECTIVE_RUNS="${RUNS_DIR:-${DEFAULT_RUNS}}"
EFFECTIVE_CONFIGS="${CONFIGS_DIR:-${DEFAULT_CONFIGS}}"

ALLOW_OUTSIDE="${ALLOW_OUTSIDE_BACKUP:-1}"

resolve_abs() {
  python3 - <<'PY' "$1"
import os, sys
print(os.path.realpath(sys.argv[1]))
PY
}

RUNS_ABS="$(resolve_abs "${EFFECTIVE_RUNS}")"
CONFIGS_ABS="$(resolve_abs "${EFFECTIVE_CONFIGS}")"

for dir_path in "${RUNS_ABS}" "${CONFIGS_ABS}"; do
  if [[ ! -d "${dir_path}" ]]; then
    echo "[backup] ERROR: directory does not exist: ${dir_path}" >&2
    exit 1
  fi
done

if [[ "${ALLOW_OUTSIDE}" != "1" ]]; then
  case "${RUNS_ABS}" in
    ${REPO_ROOT}/*) ;;
    *)
      echo "[backup] ERROR: RUNS_DIR outside repo and ALLOW_OUTSIDE_BACKUP!=1: ${RUNS_ABS}" >&2
      exit 1
      ;;
  esac
  case "${CONFIGS_ABS}" in
    ${REPO_ROOT}/*) ;;
    *)
      echo "[backup] ERROR: CONFIGS_DIR outside repo and ALLOW_OUTSIDE_BACKUP!=1: ${CONFIGS_ABS}" >&2
      exit 1
      ;;
  esac
fi

if [[ "${ALLOW_OUTSIDE}" == "1" ]]; then
  for dir_path in "${RUNS_ABS}" "${CONFIGS_ABS}"; do
    case "${dir_path}" in
      ${REPO_ROOT}/*) ;;
      *) echo "[backup] NOTICE: including outside-repo path ${dir_path}" >&2 ;;
    esac
  done
fi

OUTPUT_ROOT="${OUT_DIR:-${BACKUP_DEST:-${REPO_ROOT}/backups}}"
mkdir -p "${OUTPUT_ROOT}"

RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE_PATH="${OUTPUT_ROOT}/logos_backup_${STAMP}.tar.gz"

MANIFEST_FILE="$(mktemp)"
{
  echo "stamp=${STAMP}"
  echo "repo_root=${REPO_ROOT}"
  echo "runs_abs=${RUNS_ABS}"
  echo "configs_abs=${CONFIGS_ABS}"
} >"${MANIFEST_FILE}"

echo "[backup] archiving"
echo "  runs:    ${RUNS_ABS}"
echo "  configs: ${CONFIGS_ABS}"
echo "  output:  ${ARCHIVE_PATH}"

RUNS_BASE="$(basename "${RUNS_ABS}")"
RUNS_PARENT="$(dirname "${RUNS_ABS}")"
CONFIGS_BASE="$(basename "${CONFIGS_ABS}")"
CONFIGS_PARENT="$(dirname "${CONFIGS_ABS}")"
MANIFEST_BASE="$(basename "${MANIFEST_FILE}")"
MANIFEST_PARENT="$(dirname "${MANIFEST_FILE}")"

tar_args=(
  "--warning=no-file-changed"
  "-czf" "${ARCHIVE_PATH}"
)

tar_args+=("--transform" "s|^${RUNS_BASE}/|runs/|")
tar_args+=("-C" "${RUNS_PARENT}" "${RUNS_BASE}")
tar_args+=("--transform" "s|^${CONFIGS_BASE}/|configs/|")
tar_args+=("-C" "${CONFIGS_PARENT}" "${CONFIGS_BASE}")
tar_args+=("--transform" "s|^${MANIFEST_BASE}$|manifest/manifest.txt|")
tar_args+=("-C" "${MANIFEST_PARENT}" "${MANIFEST_BASE}")

if ! tar "${tar_args[@]}"; then
  echo "[backup] ERROR: tar command failed" >&2
  rm -f "${ARCHIVE_PATH}"
  rm -f "${MANIFEST_FILE}"
  exit 1
fi

rm -f "${MANIFEST_FILE}"

echo "[backup] created ${ARCHIVE_PATH}"

if command -v find >/dev/null 2>&1; then
  find "${OUTPUT_ROOT}" -maxdepth 1 -type f -name 'logos_backup_*.tar.gz' -mtime +"${RETENTION_DAYS}" -print -delete
fi
