#!/bin/zsh
# Start AssemblyVision op http://127.0.0.1:8420. Stoppen met Ctrl+C.
set -e
cd "${0:A:h}"

if [[ ! -d backend/.venv ]]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

if [[ ! -f frontend/dist/index.html || -n $(find frontend/src frontend/index.html -newer frontend/dist/index.html) ]]; then
  (cd frontend && npm run build)
fi

echo "AssemblyVision: http://127.0.0.1:8420 (stoppen met Ctrl+C)"
cd backend
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8420
