#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
INTERVAL_SECONDS="${JOURNAL_INTERVAL_SECONDS:-600}"

cd "${PROJECT_DIR}"

while true; do
  python3 scripts/codex_gpt_journal.py --commit --push || true
  sleep "${INTERVAL_SECONDS}"
done

