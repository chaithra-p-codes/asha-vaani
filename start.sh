#!/usr/bin/env bash
# ASHA Vaani one-command start (Linux / macOS). Requires Python 3.10+.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then "$PY" -m venv .venv; fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r backend/requirements.txt
python scripts/setup/generate_keys.py
if [ ! -f frontend/dist/index.html ]; then
  echo "Building frontend (needs Node 18+)..."; (cd frontend && npm install && npm run build)
fi
echo "Open http://localhost:8000 on this computer (phones need HTTPS: see README 'Test on a phone')."
cd backend && exec uvicorn app.main:app --host "${ASHA_HOST:-0.0.0.0}" --port "${ASHA_PORT:-8000}"
