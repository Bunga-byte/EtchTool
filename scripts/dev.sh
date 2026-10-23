#!/usr/bin/env bash
set -euo pipefail
FRIP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FRIP_ROOT"
if [[ ! -x .venv/bin/python || ! -d frontend/node_modules ]]; then
  printf 'Run ./scripts/setup.sh first.\n' >&2
  exit 1
fi
export npm_config_cache="${npm_config_cache:-/tmp/frip-npm-cache}"
FRIP_PIDS=()
cleanup() {
  if ((${#FRIP_PIDS[@]})); then
    kill "${FRIP_PIDS[@]}" 2>/dev/null || true
    wait "${FRIP_PIDS[@]}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
(
  cd backend
  ../.venv/bin/alembic upgrade head
  if [[ "${FRIP_MODE:-synthetic}" == synthetic ]]; then ../.venv/bin/python -m app.seed; fi
  exec ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
FRIP_PIDS+=("$!")
(
  cd frontend
  exec npm run dev -- --host 127.0.0.1
) &
FRIP_PIDS+=("$!")
printf 'FRIP local services starting; synthetic dataset only. Ctrl-C stops these processes.\n'
wait -n "${FRIP_PIDS[@]}"
