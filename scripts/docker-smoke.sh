#!/bin/sh
# End-to-end check of the Docker profile as the user who runs this, with host folders that user
# owns, as on a Linux install: a copy of the earlier workspace written into EXPORTS_HOST_DIR, a
# Brain proposal and its approval committed in the git repository at BRAIN_HOST_DIR, and a
# backup restored into a fresh data volume with the note it held.
#
# CI runs it on Linux, where a container can write to a host folder only as a user the folder
# lets in (docs/setup.md). It needs the image (docker compose build), python3, git and curl.
# It uses its own project name, port and temporary folders, never reads this checkout's .env,
# and removes what it started when it ends.
set -eu

repo=$(cd "$(dirname "$0")/.." && pwd)
port=${SMOKE_PORT:-18787}
base="http://127.0.0.1:$port"
work=$(mktemp -d)

compose() {
    docker compose --project-name contxt-smoke --project-directory "$work" \
        --file "$repo/compose.yaml" "$@"
}

finish() {
    status=$?
    if [ "$status" -ne 0 ]; then
        compose logs --no-color --tail 60 app >&2 || true
    fi
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$work" 2>/dev/null || echo "Left $work: some files there are not yours." >&2
    exit "$status"
}
trap finish EXIT

say() { printf '\n== %s\n' "$*"; }
fail() {
    echo "FAILED: $*" >&2
    exit 1
}
get() { curl -sS --fail-with-body -H "Authorization: Bearer $token" "$base$1"; }
post() {
    curl -sS --fail-with-body -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" --data "$2" "$base$1"
}
field() { python3 -c "import json, sys; print(json.load(sys.stdin)$1)"; }

start() {
    compose up -d app
    tries=0
    until curl -fsS "$base/api/health" >/dev/null 2>&1; do
        tries=$((tries + 1))
        [ "$tries" -lt 45 ] || fail "the app did not answer $base/api/health."
        sleep 2
    done
    curl -fsS "$base/api/health"
    echo
    token=$(compose exec -T app contxt token | sed -n 's/.*token=//p')
    [ -n "$token" ] || fail "contxt token printed no sign-in link."
}

docker image inspect contxt:latest >/dev/null 2>&1 ||
    fail "no contxt:latest image; run docker compose build first."

say "Host folders owned by $(id -un) ($(id -u):$(id -g))"
mkdir "$work/exports" "$work/brain" "$work/scout"
# The engine's sample vault, set to commit its changes as an operator's Brain does.
PYTHONPATH="$repo/packages/brain/src:$repo/packages/brain" python3 - "$work/brain" <<'EOF'
import json
import os
import sys

from tests import fixture

path = os.path.join(fixture.build(sys.argv[1]), "brain.json")
with open(path, encoding="utf-8") as handle:
    config = json.load(handle)
config["git"] = {"auto_commit": True}
with open(path, "w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2)
EOF
git -C "$work/brain" init -q -b main
git -C "$work/brain" add -A
git -C "$work/brain" -c user.name=Smoke -c user.email=smoke@localhost commit -q -m "Sample vault"

cp "$repo/.env.example" "$work/.env"
cat >>"$work/.env" <<EOF
CONTXT_UID=$(id -u)
CONTXT_GID=$(id -g)
CONTXT_PORT=$port
BRAIN_HOST_DIR=$work/brain
EXPORTS_HOST_DIR=$work/exports
SCOUT_HOST_DIR=$work/scout
EOF

say "Start the app"
start

say "Write a copy of the earlier workspace into the host folder"
exported=$(post /api/legacy/export '{}') || fail "export: $exported"
location=$(printf '%s' "$exported" | field '["dir"]')
exported_file="$work/exports/${location#/data/exports/}/README.md"
grep -q "The earlier workspace" "$exported_file" ||
    fail "the export is not in the host folder: $exported_file"
echo "$exported_file"

say "Keep a note, to find again after the restore"
noted=$(post /api/notes '{"title":"Mount check","body":"Written by the container."}') ||
    fail "note: $noted"

say "Propose and approve a Brain change in the host repository"
proposed=$(post /api/brain/proposals '{"title":"Mount check",
    "statement":"The Contxt container can write to the Brain.",
    "evidence":"Written by scripts/docker-smoke.sh through the REST API."}') ||
    fail "Brain proposal: $proposed"
[ "$(printf '%s' "$proposed" | field '["status"]')" = pending ] ||
    fail "Brain proposal: $proposed"
proposal=$(printf '%s' "$proposed" | field '["proposal_id"]')
entry=$(printf '%s' "$proposed" | field '["entry_id"]')
decided=$(post "/api/brain/proposals/$proposal/decide" '{"approve":true}') ||
    fail "Brain approval: $decided"
[ "$(printf '%s' "$decided" | field '["status"]')" = approved ] ||
    fail "Brain approval: $decided"
git -C "$work/brain" log --format=%s -- vault/knowledge | grep -q "$entry" ||
    fail "no commit of $entry in the host repository."
git -C "$work/brain" log --format='%h %an <%ae> %s'

say "Back up to this machine, then restore into a fresh data volume"
compose exec -T app contxt --env-file "" backup /data/backups/smoke.zip --with-brain ||
    fail "backup."
compose cp app:/data/backups/smoke.zip "$work/smoke.zip" || fail "copying the backup out."
compose down --volumes
compose run --rm -T -v "$work/smoke.zip:/restore.zip:ro" app \
    contxt --env-file "" restore /restore.zip --brain-dir /data/restored-brain >/dev/null ||
    fail "restore into a fresh data volume."
start
get /api/notes | python3 -c '
import json, sys
sys.exit(all(n["title"] != "Mount check" for n in json.load(sys.stdin)))' ||
    fail "the restored data lacks the note."

say "Everything the containers wrote belongs to $(id -un)"
foreign=$(find "$work" ! -user "$(id -u)" | head -n 5)
[ -z "$foreign" ] || fail "written as another user: $foreign"

say "OK: exports, Brain commits and a restore work as $(id -un)."
