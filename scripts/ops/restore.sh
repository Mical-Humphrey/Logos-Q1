#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 && -z "${BACKUP_ARCHIVE:-}" ]]; then
  echo "usage: restore.sh <archive.tar.gz> [target_dir]" >&2
  exit 1
fi

ARCHIVE="${1:-${BACKUP_ARCHIVE}}"
TARGET_DIR="${2:-${RESTORE_TARGET:-$(pwd)}}"

if [[ ! -f "${ARCHIVE}" ]]; then
  echo "error: backup archive '${ARCHIVE}' not found" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

tar -xzf "${ARCHIVE}" -C "${TARGET_DIR}"

echo "restored backup into ${TARGET_DIR}"
