# workspace-server

The process the web UI and AI clients talk to. It owns no business logic: every route and MCP
tool calls the `Workspace` facade from `workspace-core`.

```
contxt serve           REST API, MCP endpoint (/mcp) and the built web UI, on 127.0.0.1
contxt worker          lease expiry, due-task scheduling and file ingestion, in a loop
contxt mcp             a stdio bridge to /mcp for clients that only speak stdio
contxt add-model       give a model its own token and print its MCP setup
contxt backup          one archive with the database, files and a manifest
contxt restore         the reverse, into an empty data directory
```
