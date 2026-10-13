#!/usr/bin/env bash
# NFR08: a backup only counts once it has been restored. Restores into a scratch location, migrates,
# and checks every revision checksum against its content. Usage: scripts/restore_verify.sh /path/nis-<stamp>
set -euo pipefail
SRC="${1:?backup directory}"
(cd "$SRC" && sha256sum -c MANIFEST.sha256)
WORK="$(mktemp -d)"
mkdir -p "$WORK/data" && tar -C "$WORK/data" -xzf "$SRC/objects.tar.gz"
if [ -f "$SRC/db.sqlite" ]; then
  cp "$SRC/db.sqlite" "$WORK/nis.db"
  export NIS_DATABASE_URL="sqlite:///$WORK/nis.db"
else
  : "${NIS_RESTORE_PG_URL:?set NIS_RESTORE_PG_URL to an EMPTY scratch database}"
  pg_restore --no-owner --dbname="${NIS_RESTORE_PG_URL/+psycopg/}" "$SRC/db.pgdump"
  export NIS_DATABASE_URL="$NIS_RESTORE_PG_URL"
fi
export NIS_DATA_DIR="$WORK/data"
python3 -m nis.cli verify-data   # every revision checksum, every source object, every encrypted row
date -u +%Y-%m-%dT%H:%M:%SZ > "$SRC/VERIFIED"
echo "restore verified in $WORK"
