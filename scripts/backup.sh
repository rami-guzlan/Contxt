#!/bin/sh
# Back up the Docker workspace (database, files and the Brain) into ./backups on this machine.
set -eu
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="workspace-$stamp.zip"
mkdir -p backups
docker compose exec -T app workspace --env-file "" backup "/data/backups/$name" --with-brain
docker compose cp "app:/data/backups/$name" "backups/$name"
echo "backups/$name"
