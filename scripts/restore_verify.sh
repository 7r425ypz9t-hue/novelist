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
python3 - <<'PY'
from sqlalchemy import select, func
from nis.cli import migrate
from nis.db import SessionLocal
from nis.models import Revision, Project, SourceFile
from nis.services.manuscript import canonical_hash
from nis.storage import store
migrate()
db = SessionLocal()
bad = [r.id for r in db.scalars(select(Revision)) if canonical_hash(r.content_json) != r.checksum]
missing = [s.id for s in db.scalars(select(SourceFile)) if not (store().root / s.object_key).exists()]
print("projects:", db.scalar(select(func.count()).select_from(Project)),
      "revisions:", db.scalar(select(func.count()).select_from(Revision)),
      "checksum mismatches:", len(bad), "missing source files:", len(missing))
raise SystemExit(1 if bad or missing else 0)
PY
echo "restore verified in $WORK"
