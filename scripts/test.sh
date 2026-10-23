#!/usr/bin/env bash
set -euo pipefail
FRIP_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export npm_config_cache="${npm_config_cache:-/tmp/frip-npm-cache}"
cd "$FRIP_ROOT/backend"
../.venv/bin/python -m pytest -q
cd "$FRIP_ROOT/frontend"
npm test -- --run
npm run build
