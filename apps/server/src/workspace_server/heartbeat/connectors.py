"""The heartbeat's connectors: found in the CLIs' own configuration, read only through tools
that only read.

Claude Code keeps its MCP servers in `~/.claude.json` (top level, and per project under
`projects`); Codex in `~/.codex/config.toml` (`[mcp_servers.<name>]`). `CLAUDE_CONFIG_DIR` and
`CODEX_HOME` move them, as they move the CLIs. A repository's own `.mcp.json` is that
repository's, not the person's: it is not read. Gnomon's own Brain and app servers are not
connectors.

What a server needs to start (its command, its environment, its address and headers) is read
from the CLI's file each time and handed to the CLI for that read alone; Gnomon keeps only a
connector's name, its kind and the names of its read-only tools, never a credential, an
environment value or a token.

Claude Code also loads the connectors of the person's Claude account (claude.ai): they live
in the account, not in a file, so Claude Code lists them itself when it starts (its first line,
read before it answers); those start off, since a read reaches the person's own account.

Read-only, provably: Gnomon itself asks the server for its tools (`tools/list`, the only
request this client can make besides starting the session) and keeps those that only read: a
`readOnlyHint` of true or, when a tool has no annotations, a name that starts with a read verb.
Either way a name with a write verb in it is never kept. A server whose tools cannot be listed
cannot be confirmed read-only, and is not read.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

READ_VERBS = frozenset(
    ("get", "list", "search", "read", "fetch", "query", "find", "view", "show", "describe")
)
WRITE_VERBS = frozenset(
    (
        "send",
        "post",
        "reply",
        "create",
        "update",
        "delete",
        "remove",
        "write",
        "publish",
        "pay",
        "charge",
        "buy",
        "transfer",
        "invite",
        "share",
        "move",
        "archive",
        "schedule",
    )
)
OWN_SERVERS = frozenset(("contxt", "contxt-app", "workspace", "gnomon"))
# Servers that drive a screen or a browser: computer use, which a beat does not read through.
COMPUTER = re.compile(r"computer[-_ ]?use|claude-in-chrome|playwright|puppeteer|browser", re.I)
PROTOCOL = "2025-06-18"
SAFE_NAME = re.compile(r"[^A-Za-z0-9_-]+")


@dataclass
class Found:
    """A connector as one CLI's file describes it. `spec` is the server's own entry, read now
    and never stored: it may hold an environment value or a header with a token."""

    id: str
    name: str
    cli: str  # claude | codex | gnomon
    how: str  # mcp | computer | folder
    found_in: str
    spec: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def server(self) -> str:
        """The server's name as the CLI's tool names carry it (`mcp__<server>__<tool>`)."""
        return self.name


def _home() -> str:
    return os.path.expanduser("~")


def claude_config() -> str:
    folder = os.environ.get("CLAUDE_CONFIG_DIR")
    return os.path.join(folder, ".claude.json") if folder else os.path.join(_home(), ".claude.json")


def codex_config() -> str:
    folder = os.environ.get("CODEX_HOME") or os.path.join(_home(), ".codex")
    return os.path.join(folder, "config.toml")


def _how(name: str, spec: dict[str, Any]) -> str:
    said = " ".join(
        [name, str(spec.get("command") or ""), *[str(a) for a in spec.get("args") or []]]
    )
    return "computer" if COMPUTER.search(said) else "mcp"


def _claude() -> list[Found]:
    path = claude_config()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    places: list[tuple[str, Any]] = [("Claude Code settings", data.get("mcpServers"))]
    for project, entry in sorted((data.get("projects") or {}).items()):
        if isinstance(entry, dict):
            places.append((f"Claude Code, project {project}", entry.get("mcpServers")))
    out: dict[str, Found] = {}
    for where, servers in places:
        if not isinstance(servers, dict):
            continue
        for name, spec in servers.items():
            if not isinstance(spec, dict) or str(name).lower() in OWN_SERVERS:
                continue
            key = f"claude:{name}"
            if key not in out:
                out[key] = Found(key, str(name), "claude", _how(name, spec), where, dict(spec))
    return list(out.values())


def _codex() -> list[Found]:
    path = codex_config()
    try:
        with open(path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    out = []
    for name, spec in (data.get("mcp_servers") or {}).items():
        if not isinstance(spec, dict) or str(name).lower() in OWN_SERVERS:
            continue
        if spec.get("enabled") is False:
            continue
        out.append(
            Found(f"codex:{name}", str(name), "codex", _how(name, spec), "Codex settings", spec)
        )
    return out


ACCOUNT = "claude.ai "  # how Claude Code names a connector of the person's Claude account


def from_account(servers: list[dict[str, Any]]) -> list[Found]:
    """The Claude account's connectors, as Claude Code listed them when it started: each with
    its status there and its tools' names (no annotations come with them, so only names that
    plainly read are kept)."""
    out = []
    for s in servers:
        name = str(s.get("name") or "")
        if not name.startswith(ACCOUNT) or name[len(ACCOUNT) :].lower() in OWN_SERVERS:
            continue
        spec = {"account": True, "status": str(s.get("status") or ""), "tools": s.get("tools")}
        out.append(
            Found(f"claude:{safe_server(name)}", name, "claude", "mcp", "Your Claude account", spec)
        )
    return out


def codex_servers() -> list[str]:
    """Every MCP server name in the Codex settings (a read turns all but one off)."""
    return [f.name for f in _codex()]


def gemini_config() -> str:
    folder = os.environ.get("GEMINI_CLI_HOME") or os.path.join(_home(), ".gemini")
    return os.path.join(folder, "settings.json")


def _gemini() -> list[Found]:
    """Gemini CLI's MCP servers (`~/.gemini/settings.json`, `mcpServers`): found for the
    connector search and its n8n suggestions; Gnomon does not read through Gemini yet."""
    try:
        with open(gemini_config(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    out = []
    for name, spec in (servers or {}).items() if isinstance(servers, dict) else []:
        if isinstance(spec, dict) and str(name).lower() not in OWN_SERVERS:
            out.append(
                Found(
                    f"gemini:{name}",
                    str(name),
                    "gemini",
                    _how(name, spec),
                    "Gemini CLI settings",
                    dict(spec),
                )
            )
    return out


def discover() -> list[Found]:
    """Every MCP server the person's CLIs are set up with, as each CLI's own file says now."""
    return [*_claude(), *_codex(), *_gemini()]


def find(connector_id: str) -> Found | None:
    """One connector's entry, read from its CLI's file now (for a read, or a listing)."""
    return next((f for f in discover() if f.id == connector_id), None)


# ---------------------------------------------------------------------- which tools only read


def words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name))
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


def read_only(tool: dict[str, Any], server: str = "") -> bool:
    """Whether a tool only reads: its annotations say so (`readOnlyHint: true`) or, with none,
    its name starts with a read verb. A name with a write verb in it never counts."""
    name = str(tool.get("name") or "")
    said = words(name)
    if not said or any(w in WRITE_VERBS for w in said):
        return False
    annotations = tool.get("annotations")
    if isinstance(annotations, dict) and "readOnlyHint" in annotations:
        return annotations.get("readOnlyHint") is True
    prefix = words(server)
    for start in range(len(prefix)):  # slack_list_channels, or Notion's notion-search under
        tail = prefix[start:]  # "claude.ai Notion": the server's name, then the verb
        if said[: len(tail)] == tail and len(said) > len(tail):
            said = said[len(tail) :]
            break
    return said[0] in READ_VERBS


def keep_read_only(tools: list[dict[str, Any]], server: str = "") -> tuple[list[str], list[str]]:
    """(the tools a beat may use, every other tool), by name."""
    names = [str(t.get("name") or "") for t in tools if t.get("name")]
    allowed = [str(t["name"]) for t in tools if t.get("name") and read_only(t, server)]
    return allowed, [n for n in names if n not in allowed]


# ---------------------------------------------------------------------- listing a server's tools


class ListingFailed(Exception):
    pass


def _request(msg_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}


INITIALIZE = {
    "protocolVersion": PROTOCOL,
    "capabilities": {},
    "clientInfo": {"name": "gnomon-heartbeat", "version": "1"},
}


def _command(spec: dict[str, Any]) -> list[str]:
    command = str(spec.get("command") or "").strip()
    if not command:
        raise ListingFailed("its settings name no command to start it")
    found = shutil.which(command) or command
    return [found, *[str(a) for a in spec.get("args") or []]]


def _env(spec: dict[str, Any]) -> dict[str, str]:
    extra = spec.get("env") or {}
    return dict(os.environ, **{str(k): str(v) for k, v in extra.items()})


def _stdio_tools(spec: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    argv = _command(spec)
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=_env(spec),
            cwd=str(spec.get("cwd") or "") or None,
        )
    except OSError as exc:
        raise ListingFailed(f"it could not be started: {exc}") from exc
    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)

    pumping = threading.Thread(target=pump, daemon=True)
    pumping.start()
    deadline = time.monotonic() + timeout

    def send(message: dict[str, Any]) -> None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(json.dumps(message) + "\n")
            proc.stdin.flush()
        except OSError as exc:
            raise ListingFailed(f"it stopped: {exc}") from exc

    def answer(msg_id: int) -> dict[str, Any]:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise ListingFailed("it did not answer in time")
            try:
                line = lines.get(timeout=left)
            except queue.Empty as exc:
                raise ListingFailed("it did not answer in time") from exc
            if line is None:
                raise ListingFailed("it stopped before listing its tools")
            try:
                found = json.loads(line)
            except ValueError:
                continue  # a log line on stdout
            if isinstance(found, dict) and found.get("id") == msg_id:
                if "error" in found:
                    raise ListingFailed(str((found.get("error") or {}).get("message") or "error"))
                return dict(found.get("result") or {})

    try:
        send(_request(1, "initialize", INITIALIZE))
        answer(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for page in range(20):
            send(_request(2 + page, "tools/list", {"cursor": cursor} if cursor else {}))
            result = answer(2 + page)
            tools.extend(t for t in result.get("tools") or [] if isinstance(t, dict))
            cursor = result.get("nextCursor") or None
            if not cursor:
                break
        return tools
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=3)
        pumping.join(timeout=3)
        if proc.stdout:
            proc.stdout.close()


def _http_tools(spec: dict[str, Any], timeout: float) -> list[dict[str, Any]]:
    url = str(spec.get("url") or "")
    if not url.startswith(("http://", "https://")):
        raise ListingFailed("its settings name no address")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": PROTOCOL,
        **{
            str(k): str(v)
            for k, v in (spec.get("headers") or spec.get("http_headers") or {}).items()
        },
    }
    session: dict[str, str] = {}

    def post(message: dict[str, Any]) -> dict[str, Any] | None:
        request = urllib.request.Request(
            url, data=json.dumps(message).encode(), headers={**headers, **session}, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.headers.get("Mcp-Session-Id"):
                    session["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
                body = response.read().decode("utf-8", "replace")
                kind = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ListingFailed("it asked to sign in") from exc
            raise ListingFailed(f"it answered {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ListingFailed(f"it could not be reached: {exc}") from exc
        if "id" not in message:
            return None
        texts = (
            [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
            if "text/event-stream" in kind
            else [body]
        )
        for text in texts:
            try:
                found = json.loads(text)
            except ValueError:
                continue
            if isinstance(found, dict) and found.get("id") == message["id"]:
                if "error" in found:
                    raise ListingFailed(str((found.get("error") or {}).get("message") or "error"))
                return dict(found.get("result") or {})
        raise ListingFailed("its answer could not be read")

    post(_request(1, "initialize", INITIALIZE))
    post({"jsonrpc": "2.0", "method": "notifications/initialized"})
    tools: list[dict[str, Any]] = []
    cursor: str | None = None
    for page in range(20):
        result = post(_request(2 + page, "tools/list", {"cursor": cursor} if cursor else {})) or {}
        tools.extend(t for t in result.get("tools") or [] if isinstance(t, dict))
        cursor = result.get("nextCursor") or None
        if not cursor:
            break
    return tools


def list_tools(found: Found, timeout: float = 20.0) -> list[dict[str, Any]]:
    """The server's tools as it lists them (`tools/list`): nothing else is asked of it."""
    spec = found.spec
    kind = str(spec.get("type") or spec.get("transport") or "").lower()
    if kind in ("http", "streamable-http", "streamable_http") or (
        not spec.get("command") and spec.get("url")
    ):
        if kind == "sse":
            raise ListingFailed("it speaks the older SSE transport, which Gnomon cannot list")
        return _http_tools(spec, timeout)
    if kind == "sse":
        raise ListingFailed("it speaks the older SSE transport, which Gnomon cannot list")
    return _stdio_tools(spec, timeout)


def safe_server(name: str) -> str:
    return SAFE_NAME.sub("_", name) or "server"
