#!/usr/bin/env bash
set -euo pipefail
FRIP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/frip-uv-cache}"
export npm_config_cache="${npm_config_cache:-/tmp/frip-npm-cache}"
cd "$FRIP_ROOT"
if command -v uv >/dev/null 2>&1; then
  if [[ ! -x .venv/bin/python ]]; then uv venv --python python3 .venv; fi
  uv pip install --python .venv/bin/python --require-hashes -r backend/requirements.lock.txt
else
  if [[ ! -x .venv/bin/python ]]; then python3 -m venv .venv; fi
  .venv/bin/python -m pip install --cache-dir /tmp/frip-pip-cache --require-hashes -r backend/requirements.lock.txt
fi
(
  cd backend
  ../.venv/bin/alembic upgrade head
  if [[ "${FRIP_MODE:-synthetic}" == synthetic ]]; then ../.venv/bin/python -m app.seed; fi
)
(cd frontend && npm ci)
printf 'FRIP dependencies and migrations are prepared (synthetic mode is seeded). Run ./scripts/dev.sh\n'
