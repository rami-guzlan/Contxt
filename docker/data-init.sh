#!/bin/sh
# Hands the data volume to the user Contxt runs as (CONTXT_UID:CONTXT_GID), which
# on Linux is the owner of the host folders it mounts. Compose runs this as root in a one-shot
# container that mounts only the data volume, so no host folder is ever changed. Entries that
# already belong to that user are left alone: with unchanged ids, a start changes nothing.
set -eu
uid=${CONTXT_UID:-10001}
gid=${CONTXT_GID:-10001}
for id in "$uid" "$gid"; do
    case "$id" in
        '' | *[!0-9]*)
            echo "CONTXT_UID and CONTXT_GID must be numeric ids (see id -u, id -g);" \
                "got '$uid' and '$gid'." >&2
            exit 2
            ;;
    esac
done
# HOME for a CLI in the container (its login, npm's cache), private to that user.
mkdir -p /data/home
chmod 700 /data/home
find /data \( ! -user "$uid" -o ! -group "$gid" \) -exec chown -h "$uid:$gid" {} +
echo "/data belongs to $uid:$gid."
