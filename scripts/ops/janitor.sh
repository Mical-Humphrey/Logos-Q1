#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/../.. && pwd)"
RUNS_DIR="${RUNS_DIR:-${ROOT_DIR}/runs}"
LOGS_DIR="${LOGS_DIR:-${ROOT_DIR}/logos/logs}"
KEEP_DAYS="${JANITOR_KEEP_DAYS:-14}"
LOG_KEEP_DAYS="${JANITOR_LOG_RETENTION_DAYS:-30}"

if [[ -d "${RUNS_DIR}" ]]; then
  find "${RUNS_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime +"${KEEP_DAYS}" -print -exec rm -rf {} +
fi

if [[ -d "${LOGS_DIR}" ]]; then
  find "${LOGS_DIR}" -type f -mtime +"${LOG_KEEP_DAYS}" -print -delete
fi
