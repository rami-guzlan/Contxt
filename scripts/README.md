# Scripts

Thin wrappers over the `workspace` CLI for the Docker profile. Each one is a few lines; read
it before running it.

| Script | Does |
|---|---|
| `backup.sh` | database, files and Brain into `backups/<time>.zip` on this machine |
| `restore.sh <zip>` | restores into a fresh workspace (refuses to overwrite) |
| `health.sh` | checks `/api/health` |
| `migrate-preview.sh` | shows pending migrations without applying them |
| `mcp_check.py` | exercises a stdio MCP server the way a client launches it |
| `docker-smoke.sh` | starts a throwaway stack as you and proves an export, a committed Brain change and a restore work with folders you own (CI runs it; it never reads your `.env`) |

Without Docker, call the CLI directly: `uv run contxt backup`, `contxt restore`,
`contxt migrate --preview`.
