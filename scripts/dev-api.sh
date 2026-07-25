#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r backend/requirements.txt
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"

# Load .env if present
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

exec uvicorn app.main:app --app-dir backend --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --reload
