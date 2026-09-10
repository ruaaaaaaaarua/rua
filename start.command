#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
if [ ! -f web/dist/index.html ]; then
  npm --prefix web ci
  npm --prefix web run build
fi
if curl --silent --fail http://127.0.0.1:8765/api/health >/dev/null; then
  open http://127.0.0.1:8765
  exit 0
fi
(
  for task_try in {1..30}; do
    if curl --silent --fail http://127.0.0.1:8765/api/health >/dev/null; then
      open http://127.0.0.1:8765
      exit 0
    fi
    sleep 1
  done
) &
exec .venv/bin/python -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765
