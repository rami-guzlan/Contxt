#!/bin/sh
# Restore a backup into a fresh Docker workspace. Refuses if the workspace already has data.
#   scripts/restore.sh backups/workspace-20260928T090000Z.zip
set -eu
archive=${1:?usage: scripts/restore.sh <backup.zip>}
docker compose stop app worker 2>/dev/null || true
docker compose run --rm -v "$(pwd)/$archive:/restore.zip:ro" app \
  workspace --env-file "" restore /restore.zip --brain-dir /data/restored-brain
docker compose up -d
