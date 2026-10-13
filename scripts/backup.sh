#!/usr/bin/env bash
# Consistent backup: PostgreSQL dump (or SQLite online backup) + object storage, with a SHA-256 manifest.
# Usage: scripts/backup.sh /path/to/backups      (reads NIS_DATABASE_URL and NIS_DATA_DIR)
set -euo pipefail
DEST="${1:?destination directory}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST/nis-$STAMP"
mkdir -p "$OUT"
URL="${NIS_DATABASE_URL:?}"
if [[ "$URL" == sqlite* ]]; then
  python3 - "$URL" "$OUT/db.sqlite" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1].split("///", 1)[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
else
  pg_dump --format=custom --no-owner --dbname="${URL/+psycopg/}" --file="$OUT/db.pgdump"
fi
mkdir -p "${NIS_DATA_DIR:?}"
tar -C "$NIS_DATA_DIR" -czf "$OUT/objects.tar.gz" .
(cd "$OUT" && sha256sum * > MANIFEST.sha256)
echo "backup written to $OUT"
