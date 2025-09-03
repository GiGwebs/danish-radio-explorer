#!/usr/bin/env bash
set -euo pipefail

# venv-aware launcher for the Streamlit dashboard
# Location: <PROJECT_ROOT>/Scripts/run_dashboard.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"
REQ_FILE="${PROJECT_DIR}/Scripts/requirements.txt"
APP_FILE="${PROJECT_DIR}/Scripts/webapp/app.py"

if [ ! -d "${VENV_DIR}" ]; then
  echo "[dashboard] Creating virtual environment at ${VENV_DIR}"
  python3 -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip >/dev/null 2>&1 || true

# Ensure requirements (including streamlit) are installed
python -m pip install -r "${REQ_FILE}"

# Run the app
exec streamlit run "${APP_FILE}"
