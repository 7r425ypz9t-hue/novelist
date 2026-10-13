#!/usr/bin/env bash
# Backup of a docker compose deployment with no host tools: pg_dump runs inside the db container and the object
# store is streamed out of the api container. Keeps KEEP_DAYS days (default 30). Usage (from the repo root):
#   scripts/compose-backup.sh /srv/kateb-backups
#   COMPOSE="docker compose -f infra/docker-compose.yml --env-file /etc/kateb.env" scripts/compose-backup.sh /backups
set -euo pipefail
DEST="${1:?destination directory}"
KEEP_DAYS="${KEEP_DAYS:-30}"
read -r -a C <<< "${COMPOSE:-docker compose -f infra/docker-compose.yml --env-file .env}"
OUT="$DEST/nis-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
trap 'echo "backup FAILED — removing incomplete $OUT" >&2; rm -rf "$OUT"' ERR
"${C[@]}" exec -T db pg_dump -U nis -d nis --format=custom --no-owner > "$OUT/db.pgdump"
"${C[@]}" exec -T api tar -C /data -czf - . > "$OUT/objects.tar.gz"
(cd "$OUT" && sha256sum db.pgdump objects.tar.gz > MANIFEST.sha256)
trap - ERR
find "$DEST" -maxdepth 1 -type d -name 'nis-*' -mtime +"$KEEP_DAYS" -print -exec rm -rf {} +
echo "backup written to $OUT (not yet verified: run scripts/compose-verify.sh $OUT)"
