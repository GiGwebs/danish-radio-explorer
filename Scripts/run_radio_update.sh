#!/usr/bin/env bash
# Wrapper to run the radio playlist orchestrator using the local venv
# Usage examples:
#   ./Scripts/run_radio_update.sh --notify-email you@example.com
#   ./Scripts/run_radio_update.sh --force --extract-log-level DEBUG --notify-email ""

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PY_VENV="${BASE_DIR}/.venv/bin/python"
REQ_FILE="${BASE_DIR}/Scripts/requirements.txt"
MAIN_SCRIPT="${BASE_DIR}/Scripts/auto_radio_update.py"

# Create venv and install deps if missing
if [[ ! -x "${PY_VENV}" ]]; then
  echo "[run_radio_update] Creating virtual environment at ${BASE_DIR}/.venv"
  python3 -m venv "${BASE_DIR}/.venv"
  "${BASE_DIR}/.venv/bin/python" -m pip install --upgrade pip
  "${BASE_DIR}/.venv/bin/python" -m pip install -r "${REQ_FILE}"
fi

# Execute orchestrator, forwarding all CLI args
exec "${PY_VENV}" "${MAIN_SCRIPT}" "$@"
