"""Providers: how each model platform connects to Contxt.

Two connections, for two jobs:

- The Brain (`brain_setup`): what an AI app reads in every chat and saves what it learns to.
  It runs on the person's own computer as a local command (MCP over stdio) beside their
  Brain folder; no server and no token.
- The app's AI work (`mcp_setup`): a model that takes on the jobs the app starts, over the
  app's /mcp endpoint with its own revocable token.

A provider never runs a model. It describes the configuration the platform needs, so setup
can show one copyable step per platform.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    transport: str  # "http": the platform speaks MCP over HTTP; "stdio": it needs the bridge
    schedule_hint: str


PROVIDERS: dict[str, Provider] = {
    p.id: p
    for p in (
        Provider(
            "claude-code",
            "Claude Code",
            "http",
            "Run the worker prompt on a schedule, for example with a scheduled task or "
            "`/loop` in a long-running session.",
        ),
        Provider(
            "claude-desktop",
            "Claude Desktop",
            "stdio",
            "Run the worker prompt from a scheduled task in the app.",
        ),
        Provider(
            "codex",
            "Codex",
            "stdio",
            "Run `codex exec` with the worker prompt from cron or Task Scheduler.",
        ),
        Provider(
            "chatgpt",
            "ChatGPT",
            "http",
            "ChatGPT reaches MCP servers over public HTTPS only: use the private-server "
            "profile behind TLS, then add the worker prompt as a scheduled task.",
        ),
        Provider(
            "gemini", "Gemini CLI", "stdio", "Run the worker prompt from cron or Task Scheduler."
        ),
        Provider("cursor", "Cursor", "http", "Run the worker prompt when you start work."),
        Provider(
            "ollama",
            "Local model (Ollama)",
            "stdio",
            "Use an MCP-capable client for your local model and schedule the worker prompt.",
        ),
        Provider(
            "other",
            "Other MCP client",
            "http",
            "Any client that speaks MCP over HTTP (or stdio through the bridge).",
        ),
    )
}


# The name clients give the app's MCP server (their tools read mcp__<name>__claim_task). Not
# "workspace": Claude Code reserves that name and silently skips a server that uses it.
SERVER_NAME = "contxt-app"


def mcp_setup(
    provider_id: str, *, url: str, token: str | None = None, server_name: str = SERVER_NAME
) -> dict[str, Any]:
    """The configuration snippet(s) for one platform. `token` is only ever shown once."""
    provider = PROVIDERS.get(provider_id) or PROVIDERS["other"]
    mcp_url = url.rstrip("/") + "/mcp"
    secret = token or "<your token>"
    http_entry = {"type": "http", "url": mcp_url, "headers": {"Authorization": f"Bearer {secret}"}}
    stdio_entry = {
        "command": "contxt",
        "args": ["mcp", "--url", mcp_url],
        "env": {"CONTXT_TOKEN": secret},
    }
    setup: dict[str, Any] = {
        "provider": provider.id,
        "label": provider.label,
        "transport": provider.transport,
        "url": mcp_url,
        "schedule_hint": provider.schedule_hint,
    }
    if provider.id == "claude-code":
        setup["command"] = (
            f"claude mcp add --transport http {server_name} {mcp_url} "
            f'--header "Authorization: Bearer {secret}"'
        )
        setup["file"] = ".mcp.json"
        setup["config"] = json.dumps({"mcpServers": {server_name: http_entry}}, indent=2)
    elif provider.id == "codex":
        setup["file"] = "~/.codex/config.toml"
        setup["config"] = (
            f'[mcp_servers.{server_name}]\ncommand = "contxt"\n'
            f'args = ["mcp", "--url", "{mcp_url}"]\n'
            f'env = {{ CONTXT_TOKEN = "{secret}" }}\n'
        )
    elif provider.transport == "stdio":
        setup["file"] = "the client's MCP settings"
        setup["config"] = json.dumps({"mcpServers": {server_name: stdio_entry}}, indent=2)
    else:
        setup["file"] = "the client's MCP settings"
        setup["config"] = json.dumps({"mcpServers": {server_name: http_entry}}, indent=2)
    return setup


# ------------------------------------------------------------------------------- the Brain

# The name AI apps give the Brain's MCP server: their tools read mcp__contxt__get_task_context.
BRAIN_SERVER_NAME = "contxt"
BRAIN_CLIENTS: dict[str, str] = {
    "claude-code": "Claude Code",
    "claude-desktop": "Claude Desktop",
    "codex": "Codex",
    "cursor": "Cursor",
    "other": "Other MCP app",
}

# A model reads the Brain only when it calls get_task_context, and it forgets to most often on
# a follow-up. The Brain's own MCP instructions say to call it first, but an app may not show
# those to its model, so the person adds this line to the app's standing instructions too. It
# asks only when the tools are there: the same file is read by runs that have none (the app's
# own one-answer asks of Claude Code, say), which must not stall on a tool they cannot call.
BRAIN_INSTRUCTION = (
    "Before you answer, if the contxt tools are available, call get_task_context with my "
    "message as I wrote it. Call it again for every later message that asks for something "
    "new, passing the session_id it returned. Follow the must-holds and rules it returns: they "
    "outrank the request. When I state a lasting rule, preference, decision or fact, propose it "
    "with propose_note."
)
# Where each app keeps the instructions it follows in every conversation.
INSTRUCTION_PLACES: dict[str, str] = {
    "claude-code": "~/.claude/CLAUDE.md, your instructions for every project",
    "claude-desktop": "Settings > Profile, under personal preferences",
    "codex": "~/.codex/AGENTS.md, your instructions for every project",
    "cursor": "Cursor Settings > Rules, under User Rules",
    "other": "your app's custom or system instructions",
}


def brain_command(python: str, vault: str) -> list[str]:
    """The local command that serves one Brain over MCP: the engine's own `mcp` command."""
    return [python, "-m", "brainkit", "--vault", vault, "mcp"]


def _shell(value: str) -> str:
    """One argument as a terminal reads it (PowerShell, cmd, bash and zsh alike)."""
    plain = bool(value) and all(c.isalnum() or c in "-_./:\\=@+" for c in value)
    return value if plain else '"' + value.replace('"', '\\"') + '"'


def _toml(value: str) -> str:
    """A TOML string; a literal one ('...') keeps Windows backslashes as they are."""
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    return json.dumps(value)


def desktop_config_file(platform: str | None = None) -> str:
    platform = platform or sys.platform
    if platform.startswith("win"):
        return r"%APPDATA%\Claude\claude_desktop_config.json"
    if platform == "darwin":
        return "~/Library/Application Support/Claude/claude_desktop_config.json"
    return "~/.config/Claude/claude_desktop_config.json"


def brain_setup(
    client: str, *, python: str, vault: str, platform: str | None = None
) -> dict[str, Any]:
    """How one AI app connects to the Brain at `vault`, run by `python` (the Contxt
    environment's interpreter): a command to run once, or a block for its settings file; then
    the standing instruction that makes its model ask the Brain first, and where it goes."""
    label = BRAIN_CLIENTS.get(client, BRAIN_CLIENTS["other"])
    command = brain_command(python, vault)
    entry = {"command": command[0], "args": command[1:]}
    servers = json.dumps({"mcpServers": {BRAIN_SERVER_NAME: entry}}, indent=2)
    setup: dict[str, Any] = {
        "client": client,
        "label": label,
        "server": BRAIN_SERVER_NAME,
        "instruction": BRAIN_INSTRUCTION,
        "instruction_where": INSTRUCTION_PLACES.get(client, INSTRUCTION_PLACES["other"]),
    }
    if client == "claude-code":
        setup["command"] = f"claude mcp add --scope user {BRAIN_SERVER_NAME} -- " + " ".join(
            _shell(part) for part in command
        )
        setup["note"] = (
            "Run this once in a terminal. Every Claude Code session then has your Brain."
        )
    elif client == "claude-desktop":
        setup["file"] = desktop_config_file(platform)
        setup["config"] = servers
        setup["note"] = (
            "Add this to that file (inside its mcpServers, if it has one already), then quit "
            "Claude Desktop fully and open it again."
        )
    elif client == "codex":
        setup["file"] = "~/.codex/config.toml"
        setup["config"] = (
            f"[mcp_servers.{BRAIN_SERVER_NAME}]\n"
            f"command = {_toml(command[0])}\n"
            f"args = [{', '.join(_toml(part) for part in command[1:])}]\n"
        )
        setup["note"] = "Add this to that file, then start a new Codex session."
    elif client == "cursor":
        setup["file"] = "~/.cursor/mcp.json"
        setup["config"] = servers
        setup["note"] = "Add this to that file, then reload Cursor."
    else:
        setup["file"] = "your app's MCP settings"
        setup["config"] = servers
        setup["note"] = "Any app that runs local MCP servers takes this command and arguments."
    return setup
