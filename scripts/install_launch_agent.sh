#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLIST_ID="com.local.codex-gpt-journal"
PLIST_PATH="${HOME}/Library/LaunchAgents/${PLIST_ID}.plist"

mkdir -p "${HOME}/Library/LaunchAgents"

/usr/bin/env python3 - "$PROJECT_DIR" "$PLIST_PATH" "$PLIST_ID" <<'PY'
import plistlib
import sys
from pathlib import Path

project_dir = Path(sys.argv[1]).resolve()
plist_path = Path(sys.argv[2])
plist_id = sys.argv[3]

data = {
    "Label": plist_id,
    "ProgramArguments": [
        "/bin/bash",
        str(project_dir / "scripts" / "run_once.sh"),
    ],
    "WorkingDirectory": str(project_dir),
    "StartInterval": 600,
    "RunAtLoad": True,
    "StandardOutPath": str(project_dir / "journal-agent.out.log"),
    "StandardErrorPath": str(project_dir / "journal-agent.err.log"),
}

with plist_path.open("wb") as f:
    plistlib.dump(data, f)

print(plist_path)
PY

launchctl unload "${PLIST_PATH}" 2>/dev/null || true
launchctl load "${PLIST_PATH}"
launchctl start "${PLIST_ID}" || true

echo "Installed ${PLIST_ID}"

