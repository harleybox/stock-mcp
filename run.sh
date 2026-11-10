#!/usr/bin/env bash
# One command to run everything: backend (FastAPI) + frontend (Vite).
#   ./run.sh              -> http://localhost:5173
#   API_PORT=9000 PORT=5180 ./run.sh   (override ports)
set -euo pipefail
cd "$(dirname "$0")"
export API_PORT="${API_PORT:-8000}"

if [ ! -d .venv ]; then
  echo "==> creating Python venv"
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "==> installing frontend deps"
  (cd frontend && npm install --no-fund --no-audit)
fi

(cd backend && ../.venv/bin/uvicorn app:app --port "$API_PORT") &
BACK=$!
trap 'kill $BACK 2>/dev/null || true' EXIT INT TERM
(cd frontend && npm run dev -- --port "${PORT:-5173}")
