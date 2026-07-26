#!/usr/bin/env bash
# Run docker compose while blocking host idle/sleep so the watch loop keeps sampling ATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example and set TELEGRAM_* / RPC_URL" >&2
  exit 1
fi

COMPOSE=(docker compose up --build "$@")

if ! command -v systemd-inhibit >/dev/null 2>&1; then
  echo "systemd-inhibit not found — starting without sleep inhibition" >&2
  exec "${COMPOSE[@]}"
fi

echo "Inhibiting idle/sleep while gnomode runs (Ctrl+C to stop)…"
exec systemd-inhibit \
  --what=idle:sleep \
  --who=gnomode \
  --why="Continuous token watch autoparse" \
  --mode=block \
  "${COMPOSE[@]}"
