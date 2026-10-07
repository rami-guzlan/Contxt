#!/bin/sh
# Exit 0 when Contxt answers its health check.
set -eu
url=${CONTXT_URL:-http://127.0.0.1:${CONTXT_PORT:-8787}}
curl -fsS "$url/api/health"
echo
