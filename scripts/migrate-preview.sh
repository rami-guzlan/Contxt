#!/bin/sh
# Show the database migrations the next start would apply, without applying them.
set -eu
docker compose run --rm app workspace --env-file "" migrate --preview
