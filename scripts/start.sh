#!/usr/bin/env bash
# «كاتب» on the writer's own computer — one command, one process, no Docker:
#   scripts/start.sh            → http://127.0.0.1:8000 (this computer only)
#   scripts/start.sh --lan      → also reachable from the writer's other computers (see docs/operations.md §1ب)
# First run: creates .venv, installs the API, builds the control panel, creates an encryption key in
# ~/.config/kateb/master.key (outside the data folder, so a copied data folder alone cannot be read),
# then runs the readiness check (`nis doctor`) and serves. Data lives in ./var (KATEB_HOME to move it).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
HOME_DIR="${KATEB_HOME:-$ROOT/var}"
KEY_FILE="${KATEB_KEY_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kateb/master.key}"
PORT="${PORT:-8000}"
HOST=127.0.0.1
[ "${1:-}" = "--lan" ] && HOST=0.0.0.0

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
if [ "$HOST" != 127.0.0.1 ]; then
  # Reachable by other machines: the account must already exist (the first account becomes administrator),
  # and nobody else on the network may register.
  USERS="$(python -c 'from sqlalchemy import func, select; from nis.db import SessionLocal; from nis.models import User; print(SessionLocal().scalar(select(func.count()).select_from(User)))')"
  if [ "$USERS" = "0" ]; then
    echo "أنشئ حسابك أولاً بتشغيل عادي (scripts/start.sh) ثم أعد التشغيل بـ --lan؛ لا يُفتح التطبيق للشبكة قبل وجود حسابك." >&2
    exit 1
  fi
  export NIS_ALLOW_REGISTRATION=false KATEB_LAN=1
  echo "────────────────────────────────────────────────────────────"
  echo " وضع عدة أجهزة: التسجيل مغلق، وتصل إليه أجهزتك عبر:"
  python - "$PORT" <<'PY'
import socket, sys
port = sys.argv[1]
addrs = set()
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("192.0.2.1", 9)); addrs.add(s.getsockname()[0]); s.close()
except OSError:
    pass
try:
    addrs |= {i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
except OSError:
    pass
for a in sorted(a for a in addrs if not a.startswith("127.")):
    tag = "  ← شبكة Tailscale الخاصة" if a.startswith("100.") else ""
    print(f"   http://{a}:{port}{tag}")
PY
  echo " تنبيه: الاتصال غير مشفّر داخل الشبكة. استعمله في شبكة البيت الموثوقة أو عبر شبكة خاصة مشفّرة"
  echo " (مثل Tailscale أو WireGuard)، ولا تفتح هذا المنفذ للإنترنت مباشرة."
  echo "────────────────────────────────────────────────────────────"
fi
exec python -m nis.cli serve --host "$HOST" --port "$PORT"
