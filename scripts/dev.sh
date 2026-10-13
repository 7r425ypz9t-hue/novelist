#!/usr/bin/env bash
# One-command local development: API on :8000 (SQLite) + Vite on :5173 with hot reload.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -e "apps/api[dev]"
(cd apps/web && [ -d node_modules ] || npm ci --no-audit --no-fund)
export NIS_DATABASE_URL="${NIS_DATABASE_URL:-sqlite:///$ROOT/var/nis.db}" NIS_DATA_DIR="${NIS_DATA_DIR:-$ROOT/var/data}"
python -m nis.cli migrate
[ "${1:-}" = "--demo" ] && python -m nis.cli demo
trap 'kill 0' EXIT
(cd apps/api && uvicorn nis.main:app --reload --port 8000) &
(cd apps/web && npx vite --port 5173) &
wait
