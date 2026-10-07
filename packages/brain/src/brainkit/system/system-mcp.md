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
`brain_health` tool. Agent tools: get_task_context, search_notes, get_note, get_skill,
get_reference, propose_note, record_focus_update, create_focus, brain_health. When a packet
lacks something, search_notes finds notes in the agent's own words and get_note opens one;
both record what the session holds, so packets do not repeat it.
