#!/usr/bin/env bash
# «كاتب» on the writer's own computer — one command, one process, no Docker:
#   scripts/start.sh            → http://127.0.0.1:8000
# First run: creates .venv, installs the API, builds the control panel, creates an encryption key in
# ~/.config/kateb/master.key (outside the data folder, so a copied data folder alone cannot be read),
# then runs the readiness check (`nis doctor`) and serves. Data lives in ./var (KATEB_HOME to move it).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HOME_DIR="${KATEB_HOME:-$ROOT/var}"
KEY_FILE="${KATEB_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kateb/master.key}"
PORT="${PORT:-8000}"

command -v python3 >/dev/null || { echo "python3 (≥3.11) is required" >&2; exit 1; }
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -e "apps/api[pdf]" 2>/dev/null || pip install -q -e apps/api
if [ ! -f apps/api/nis/static/index.html ]; then
  command -v npm >/dev/null || { echo "Node.js (npm) is required once, to build the control panel" >&2; exit 1; }
  (cd apps/web && npm ci --no-audit --no-fund && npx vite build)
fi
if [ -z "${NIS_MASTER_KEY:-}" ]; then
  if [ ! -s "$KEY_FILE" ]; then
    mkdir -p "$(dirname "$KEY_FILE")" && (umask 077 && python -m nis.cli new-key > "$KEY_FILE")
    echo "encryption key created: $KEY_FILE — back it up separately; without it the manuscripts cannot be read."
  fi
  NIS_MASTER_KEY="$(cat "$KEY_FILE")"
fi
export NIS_MASTER_KEY
export NIS_DATABASE_URL="${NIS_DATABASE_URL:-sqlite:///$HOME_DIR/nis.db}" NIS_DATA_DIR="${NIS_DATA_DIR:-$HOME_DIR/data}"
mkdir -p "$HOME_DIR"
python -m nis.cli migrate >/dev/null
python -m nis.cli encrypt-existing >/dev/null   # idempotent: seals anything written before the key existed
exec python -m nis.cli serve --port "$PORT"
