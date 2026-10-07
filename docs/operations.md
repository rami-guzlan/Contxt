# Operations

## Profiles

| Profile | Command | Database | Exposure |
|---|---|---|---|
| Local | `docker compose up -d` | SQLite in the `contxt-data` volume | 127.0.0.1 only |
| Private server | `docker compose -f compose.yaml -f docker/compose.server.yaml up -d` | PostgreSQL | HTTPS through Caddy, on a name you control (a private network or Tailscale) |
| Development | `uv run contxt serve` and `npm run dev` | SQLite in `./data` | 127.0.0.1 only |

Both containers (`app`: API, MCP and web UI; `worker`: lease expiry and recurring due dates)
use the same image and data; a one-shot `data-init` prepares the data volume before they
start.

## Which user the containers run as

The app and the worker run as `CONTXT_UID:CONTXT_GID` from `.env`, or 10001:10001 when
those are empty. Before they start, `data-init` hands the `contxt-data` volume to that
user and exits (`docker compose logs data-init` says to whom). It is the only part that runs
as root, and it mounts that volume alone, so it never changes a folder on this machine: the
Brain repository and the exports folder (`EXPORTS_HOST_DIR`, or `docker/exports/`) must
already be writable by that user. Commands started with `docker compose exec` or
`docker compose run`, such as the sign-in link, backups and restores, run as the same user.

- **Linux**: set both to the owner of those folders, usually you (`id -u`, `id -g`).
  Otherwise Linux refuses the writes: a copy of the earlier workspace fails with `Permission
  denied: '/data/exports/...'` in `docker compose logs app`, and a Brain whose notes the engine wrote
  cannot even be read, so `/api/health` fails with a `PermissionError` under `/brain`.
- **Rootless Docker**: container root is your own unprivileged user there, so set both to `0`.
- **Docker Desktop** (Windows, macOS): leave them empty; its file sharing does not enforce
  ownership.

To switch an existing install, add or change the two lines in `.env` and run
`docker compose up -d`: `data-init` re-owns the volume's files and both containers are
recreated as the new user. `docker compose exec app id` shows who they run as.

`scripts/docker-smoke.sh` checks a host end to end, as CI does on Linux: after
`docker compose build`, it starts a throwaway stack as you with temporary folders you own,
writes a copy of the earlier workspace, commits a Brain change and restores a backup, without reading your
`.env` or touching your data.

## Upgrades

```bash
git pull && docker compose up -d --build
```

On Linux, an `.env` from before `CONTXT_UID` and `CONTXT_GID` existed needs those two
lines added ([which user the containers run as](#which-user-the-containers-run-as)).

Migrations run automatically on startup. Before an existing SQLite database is migrated, a
copy is written to `data/backups/pre-migrate-<revision>-<time>.sqlite`; to roll back, stop
the app, put that file back as `data/workspace.sqlite`, and start the previous release. See
what an upgrade would change first with `contxt migrate --preview`.

## Backup and restore

```bash
docker compose exec app contxt backup /data/backups/today.zip --with-brain
docker compose cp app:/data/backups/today.zip .
```

The archive is a plain zip: `manifest.json`, one JSON Lines file per table, the stored files
under their hashes, and with `--with-brain` the Brain vault. Rows are backend-neutral, so an
archive moves between SQLite and PostgreSQL.

What `--with-brain` keeps of the Brain's runtime folder (`.brain`), and what it leaves:

| In `.brain` | In the backup | Why |
| --- | --- | --- |
| `library/`: the original bytes of every filed document | yes | nothing else holds them; the vault keeps only the converted text |
| `staging/`: files still waiting for review | yes | they exist nowhere else until approved |
| `embeddings.sqlite`, `models/` | no | rebuilt (the models download again) |
| `sessions.sqlite`: what each AI asked and was handed | no | local history, kept for 90 days; Activity starts fresh after a restore |
| `checkpoints/`: undo points | no | local history, like the vault's git history |
| `write.lock`, sync state | no | rebuilt when the Brain next runs |

Restore into an empty data folder; it refuses to overwrite and verifies every file's hash:

```bash
contxt restore today.zip --brain-dir restored-brain
```

An earlier workspace (goals, to-dos, meetings, project memory, sheets, canvases) copies out
as files anyone can read without the app: Settings, Workspace, *Your earlier workspace*, or
`contxt export-legacy [--out DIR]`.

## Health and logs

- `GET /api/health` (no token): status, version, database revision, Brain connected.
- `docker compose logs -f app worker`
- `contxt status`: the app's AI work by status, and the proposals waiting for review.

## Connections and tokens

Each model connection has its own token (stored as a hash, shown once). Rotate by issuing a
new token in Settings, AI apps, switching the client, then revoking the old one.
Disconnecting a model revokes all its tokens and keeps its history.

## Data locations

| What | Where |
|---|---|
| Records and events | `data/workspace.sqlite` or `CONTXT_DATABASE_URL` |
| Uploaded files | `data/objects/` (content-addressed) |
| Generated owner token (when not set in `.env`) | `data/secrets/owner-token` |
| Pre-migration snapshots and default backups | `data/backups/` |
| Copies of an earlier workspace | `data/exports/` or `CONTXT_EXPORTS_DIR` |
| Long-term context | the Brain vault, in its own git repository |
