---
id: system-mcp
title: The MCP server and how to restart it
keywords: mcp server restart relaunch reload stale connection tools claude codex
---
The brain serves AI clients over MCP on stdio: `brain mcp` (the repo's `.mcp.json`
runs exactly that). The server re-reads the vault on every request, so content changes never
need a restart. Restart it only after ENGINE code changes: the server compares the code it
loaded with the code on disk and reports itself stale.

To restart: reconnect the MCP server from the client (Claude Code: `/mcp`, then reconnect
`brain`; or restart the session). To check health first: `brain check`, or the
`gnomon_health` tool. Agent tools: gnomon_get_context, notes_search, notes_get, skills_get,
files_open, notes_propose, projects_propose_progress, projects_create, gnomon_health, agents_list,
agents_get, sheets_get, sheets_propose_update, todos_update. When a packet
lacks something, notes_search finds notes in the agent's own words and notes_get opens one;
both record what the session holds, so packets do not repeat it.
