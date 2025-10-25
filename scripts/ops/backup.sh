#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
RUNS_DIR="${RUNS_DIR:-${ROOT_DIR}/runs}"
CONFIGS_DIR="${CONFIGS_DIR:-${ROOT_DIR}/configs}"
DEST_DIR="${BACKUP_DEST:-${ROOT_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE_NAME="logos_backup_${STAMP}.tar.gz"
ARCHIVE_PATH="${DEST_DIR}/${ARCHIVE_NAME}"

mkdir -p "${DEST_DIR}"

if [[ ! -d "${RUNS_DIR}" ]]; then
  echo "warning: runs directory '${RUNS_DIR}' missing" >&2
fi
if [[ ! -d "${CONFIGS_DIR}" ]]; then
  echo "warning: configs directory '${CONFIGS_DIR}' missing" >&2
fi

pushd "${ROOT_DIR}" >/dev/null
TARGETS=()
[[ -d "${RUNS_DIR}" ]] && TARGETS+=("runs")
[[ -d "${CONFIGS_DIR}" ]] && TARGETS+=("configs")

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "nothing to back up under ${ROOT_DIR}" >&2
  exit 0
fi

tar --warning=no-file-changed -czf "${ARCHIVE_PATH}" "${TARGETS[@]}"
popd >/dev/null

echo "created backup ${ARCHIVE_PATH}"

if command -v find >/dev/null 2>&1; then
  find "${DEST_DIR}" -maxdepth 1 -type f -name 'logos_backup_*.tar.gz' -mtime +"${RETENTION_DAYS}" -print -delete
fi
