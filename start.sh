#!/usr/bin/env bash
# Start AssemblyVision op http://127.0.0.1:8420. Stoppen met Ctrl+C. Werkt op macOS en Linux.
#   ./start.sh                        echte camera's
#   ./start.sh --test-beelden [map]   opgeslagen beelden, zonder camera's
set -e
cd "$(dirname "$0")"

if [[ "$1" == "--test-beelden" ]]; then
  export ASSEMBLYVISION_TEST_SOURCE="${2:-$PWD/spike/scenes}"
fi

if [[ ! -d backend/.venv ]]; then
  echo "Eerste start: Python-omgeving maken..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q --upgrade pip
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

# The zip for another computer carries a built frontend, so npm is only needed to rebuild it.
stale=""
if [[ ! -f frontend/dist/index.html ]] || [[ -n $(find frontend/src frontend/index.html -newer frontend/dist/index.html) ]]; then
  stale=1
fi
if [[ -n "$stale" ]]; then
  if command -v npm > /dev/null; then
    [[ -d frontend/node_modules ]] || (cd frontend && npm install)
    (cd frontend && npm run build)
  elif [[ -f frontend/dist/index.html ]]; then
    echo "Let op: npm ontbreekt, de bestaande frontend wordt gebruikt."
  else
    echo "frontend/dist ontbreekt en npm is niet geinstalleerd. Gebruik de zip met een gebouwde frontend." >&2
    exit 1
  fi
fi

if [[ -n "$ASSEMBLYVISION_TEST_SOURCE" && "$ASSEMBLYVISION_TEST_SOURCE" == "$PWD/spike/scenes" ]]; then
  backend/.venv/bin/python spike/make_scenes.py spike/scenes
  backend/.venv/bin/python spike/turn_clip.py spike/scenes
  backend/.venv/bin/python spike/demo_clip.py spike/scenes
fi

echo "AssemblyVision: http://127.0.0.1:8420 (stoppen met Ctrl+C)"
cd backend
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8420
