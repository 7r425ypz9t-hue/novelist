#!/usr/bin/env bash
# NFR08 for compose deployments: a backup counts only once restored. Restores into a SCRATCH database inside the
# db container and a scratch folder inside the api container, runs `nis verify-data` there, then drops both.
# On success writes VERIFIED next to the manifest (read by `nis doctor`). Usage: scripts/compose-verify.sh DIR
set -euo pipefail
SRC="$(cd "${1:?backup directory}" && pwd)"
read -r -a C <<< "${COMPOSE:-docker compose -f infra/docker-compose.yml --env-file .env}"
(cd "$SRC" && sha256sum -c --quiet MANIFEST.sha256)
DB="nis_verify_$(date +%s)"
cleanup() {
  "${C[@]}" exec -T db dropdb -U nis --if-exists "$DB" || true
  "${C[@]}" exec -T api rm -rf /tmp/nis-verify || true
}
trap cleanup EXIT
"${C[@]}" exec -T db createdb -U nis "$DB"
"${C[@]}" exec -T db pg_restore -U nis -d "$DB" --no-owner < "$SRC/db.pgdump"
"${C[@]}" exec -T api mkdir -p /tmp/nis-verify
"${C[@]}" exec -T api tar -C /tmp/nis-verify -xzf - < "$SRC/objects.tar.gz"
# same server, same NIS_MASTER_KEY; only the database name and data folder point at the scratch copies
"${C[@]}" exec -T api sh -c "NIS_DATABASE_URL=\"\${NIS_DATABASE_URL%/*}/$DB\" NIS_DATA_DIR=/tmp/nis-verify python -m nis.cli verify-data"
date -u +%Y-%m-%dT%H:%M:%SZ > "$SRC/VERIFIED"
echo "restore verified: $SRC"
