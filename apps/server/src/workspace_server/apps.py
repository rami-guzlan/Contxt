"""The AI apps on this computer, and connecting each to the Brain for the person.

Found: Claude Code and Codex by their commands, Claude Desktop and Cursor by their settings
folders. Connected: the Brain's server is in the app's own settings. "Add it for me" writes it
there, only when the person says yes in the app (the request carries `confirm`):

- Claude Code: `claude mcp add --scope user contxt -- <the Brain's command>`;
- Claude Desktop and Cursor: the server added to the app's JSON settings file;
- Codex: the server's block added to `~/.codex/config.toml`.

A settings file is copied beside itself before anything changes it, and a file that is not
valid JSON is left alone (the person adds the block by hand). Nothing else in it changes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from workspace_connectors.providers import BRAIN_SERVER_NAME, brain_command, brain_setup
from workspace_core.clock import iso
from workspace_core.errors import Conflict, ValidationFailed

APPS = ("claude-code", "claude-desktop", "cursor", "codex")
LABELS = {
    "claude-code": "Claude Code",
    "claude-desktop": "Claude Desktop",
    "cursor": "Cursor",
    "codex": "Codex",
}


@dataclass(frozen=True)
class Places:
    """Where each app keeps its settings on this computer (the home folder and, on Windows,
    the roaming app data folder), and how to find a command."""

    home: str
    appdata: str | None
    platform: str
    which: Callable[[str], str | None] = shutil.which

    @classmethod
    def here(cls) -> Places:
        return cls(
            home=os.path.expanduser("~"), appdata=os.environ.get("APPDATA"), platform=sys.platform
        )

    def desktop_file(self) -> str:
        if self.platform.startswith("win"):
            return os.path.join(self.appdata or self.home, "Claude", "claude_desktop_config.json")
        if self.platform == "darwin":
            return os.path.join(
                self.home, "Library", "Application Support", "Claude", "claude_desktop_config.json"
            )
        return os.path.join(self.home, ".config", "Claude", "claude_desktop_config.json")

    def cursor_file(self) -> str:
        return os.path.join(self.home, ".cursor", "mcp.json")

    def codex_file(self) -> str:
        return os.path.join(self.home, ".codex", "config.toml")


def _run(argv: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _json(path: str) -> dict[str, Any] | None:
    """A JSON settings file's content: {} when it does not exist, None when it is not JSON."""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def status(places: Places, run: Callable[..., Any] = _run) -> list[dict[str, Any]]:
    """Each app: found on this computer, and whether the Brain is in its settings."""
    out = []
    for app in APPS:
        found = connected = False
        if app == "claude-code":
            command = places.which("claude")
            found = bool(command)
            if command:
                done = run([command, "mcp", "get", BRAIN_SERVER_NAME])
                connected = bool(done and done.returncode == 0)
        elif app in ("claude-desktop", "cursor"):
            path = places.desktop_file() if app == "claude-desktop" else places.cursor_file()
            found = os.path.isdir(os.path.dirname(path))
            data = _json(path) or {}
            connected = BRAIN_SERVER_NAME in (data.get("mcpServers") or {})
        else:
            path = places.codex_file()
            found = bool(places.which("codex")) or os.path.isdir(os.path.dirname(path))
            try:
                with open(path, encoding="utf-8") as handle:
                    connected = f"[mcp_servers.{BRAIN_SERVER_NAME}]" in handle.read()
            except OSError:
                connected = False
        out.append({"client": app, "label": LABELS[app], "found": found, "connected": connected})
    return out


def _backup(path: str, moment: str) -> str | None:
    if not os.path.isfile(path):
        return None
    copy = f"{path}.contxt-backup-{moment.replace(':', '').replace('-', '')[:15]}"
    shutil.copy2(path, copy)
    return copy


def connect(
    app: str,
    *,
    vault: str,
    python: str,
    places: Places,
    moment: Any,
    run: Callable[..., Any] = _run,
) -> dict[str, Any]:
    """Put the Brain in one app's settings. Returns what was done and where the backup is."""
    if app not in APPS:
        raise ValidationFailed(f"Connect one of {', '.join(APPS)}.", field="client")
    command = brain_command(python, vault)
    stamp = iso(moment)
    if app == "claude-code":
        found = places.which("claude")
        if not found:
            raise Conflict("Claude Code is not installed on this computer.")
        done = run([found, "mcp", "get", BRAIN_SERVER_NAME])
        if done and done.returncode == 0:
            return {"client": app, "connected": True, "changed": False, "backup": None}
        added = run([found, "mcp", "add", "--scope", "user", BRAIN_SERVER_NAME, "--", *command])
        if not added or added.returncode != 0:
            why = (added.stderr or added.stdout).strip() if added else "it did not start"
            raise Conflict(f"Claude Code could not add it: {why[:300]}")
        return {"client": app, "connected": True, "changed": True, "backup": None}
    if app in ("claude-desktop", "cursor"):
        path = places.desktop_file() if app == "claude-desktop" else places.cursor_file()
        data = _json(path)
        if data is None:
            raise Conflict(
                f"{LABELS[app]}'s settings file is not valid JSON, so it was left alone. Add "
                "the block by hand."
            )
        servers = dict(data.get("mcpServers") or {})
        entry = {"command": command[0], "args": command[1:]}
        if servers.get(BRAIN_SERVER_NAME) == entry:
            return {"client": app, "connected": True, "changed": False, "backup": None}
        backup = _backup(path, stamp)
        servers[BRAIN_SERVER_NAME] = entry
        data["mcpServers"] = servers
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".contxt-new"
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
        return {"client": app, "connected": True, "changed": True, "backup": backup}
    path = places.codex_file()
    try:
        with open(path, encoding="utf-8") as handle:
            current = handle.read()
    except OSError:
        current = ""
    if f"[mcp_servers.{BRAIN_SERVER_NAME}]" in current:
        return {"client": app, "connected": True, "changed": False, "backup": None}
    block = brain_setup("codex", python=python, vault=vault)["config"]
    backup = _backup(path, stamp)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(("\n" if current and not current.endswith("\n") else "") + "\n" + block)
    return {"client": app, "connected": True, "changed": True, "backup": backup}
