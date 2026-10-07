# CLAUDE.md

@AGENTS.md

## Claude Code specifics

- Claude Code reserves the MCP server name `workspace`: that is why the app's own MCP server
  is `contxt-app` and the Brain's is `contxt`.
- To connect your Brain to Claude Code, run the one command `uv run contxt connect
  claude-code` prints. Ask before running it on someone's behalf: it changes their Claude Code
  settings.
- The app's "Run now" starts Claude Code on this computer with only the app's MCP server;
  see [docs/runners.md](docs/runners.md).
