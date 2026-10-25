"""What each CLI keeps on the person, for a memory read: its memory files and what the person
said in its recent chats. Gnomon gathers them itself, read-only, from the files each CLI
writes; never its sign-in, settings or anything else in its folder. The CLI then turns them
into context packets for the Brain (the heartbeat's judge places those, through governance).

- Claude Code (`CLAUDE_CONFIG_DIR`, else `~/.claude`): `CLAUDE.md`, each project's
  `memory/*.md`, and the person's turns in each session's `projects/*/*.jsonl` (the desktop
  app's sessions too) and in `history.jsonl` (what was typed in the terminal).
- Codex (`CODEX_HOME`, else `~/.codex`): `AGENTS.md`, and the person's messages in
  `sessions/**/rollout-*.jsonl`.
- Gemini CLI (`GEMINI_CLI_HOME`, else `~/.gemini`): `GEMINI.md`, and the person's messages
  in `tmp/*/logs.json`.
"""

from __future__ import annotations

import glob
import json
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..runners import mask

CLIS = ("claude", "codex", "gemini")
# The CLI's other apps on the same account, whose memory its read asks it for.
SURFACES = {
    "claude": "Claude (claude.ai, the desktop and mobile apps)",
    "codex": "ChatGPT (chatgpt.com, the desktop and mobile apps)",
    "gemini": "Gemini (gemini.google.com and the Gemini app)",
}
MEMORY_CHARS = 6000  # characters of one memory file
SAID_CHARS = 800  # characters of one message
FIRST_BUDGET = 60000  # characters a first read (onboarding) gathers
LATER_BUDGET = 20000  # characters a later read gathers
MAX_FILES = 400  # chat files a read opens, newest first
# What a CLI adds to a person's turn that the person did not write.
NOT_SAID = re.compile(
    r"^\s*(<environment_context>|<user_instructions>|<system-reminder>|<command-|<local-command"
    r"|Caveat: |# AGENTS\.md|\[Request interrupted|This session is being continued)",
)
REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


@dataclass
class Gathered:
    memory: list[tuple[str, str]] = field(default_factory=list)  # (where, text)
    said: list[tuple[str, str, str]] = field(default_factory=list)  # (at, project, text)
    read_at: str = ""  # when it was gathered: the next read starts here

    def empty(self) -> bool:
        return not self.memory and not self.said


def home(cli: str) -> str:
    """Where the CLI keeps its own files on this computer."""
    user = os.path.expanduser("~")
    if cli == "claude":
        return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(user, ".claude")
    if cli == "codex":
        return os.environ.get("CODEX_HOME") or os.path.join(user, ".codex")
    return os.environ.get("GEMINI_CLI_HOME") or os.path.join(user, ".gemini")


def present(cli: str) -> bool:
    return os.path.isdir(home(cli))


def _iso(value: Any) -> str:
    """An ISO 8601 UTC time from milliseconds, seconds or an ISO string; "" when unreadable."""
    try:
        if isinstance(value, (int, float)):
            seconds = value / 1000 if value > 1e11 else value
            return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        text = str(value or "").strip()
        if not text:
            return ""
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError, OverflowError):
        return ""


def _text(raw: Any, limit: int) -> str:
    text = REMINDER.sub("", str(raw or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return mask(text[:limit])


def _read(path: str, limit: int) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _newest_first(paths: list[str]) -> list[str]:
    def when(path: str) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    return sorted(paths, key=when, reverse=True)[:MAX_FILES]


def _memory_files(cli: str, root: str) -> list[str]:
    if cli == "claude":
        own = [os.path.join(root, "CLAUDE.md")]
        return own + sorted(glob.glob(os.path.join(root, "projects", "*", "memory", "*.md")))
    if cli == "codex":
        return [os.path.join(root, "AGENTS.md")]
    return [os.path.join(root, "GEMINI.md")]


def _project(path: str) -> str:
    """A short name for a Claude Code project folder (`C--dev-site` → `site`)."""
    return re.split(r"[-\\/]", path.rstrip("\\/"))[-1] if path else ""


def _claude_said(root: str) -> list[tuple[str, str, str]]:
    out = []
    for line in _read(os.path.join(root, "history.jsonl"), 50_000_000).splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("display"):
            out.append(
                (
                    _iso(entry.get("timestamp")),
                    _project(str(entry.get("project") or "")),
                    str(entry["display"]),
                )
            )
    for path in _newest_first(glob.glob(os.path.join(root, "projects", "*", "*.jsonl"))):
        for line in _read(path, 50_000_000).splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict) or entry.get("type") != "user":
                continue
            # A tool's result, a turn Claude Code added, a subagent's or a summary: not said.
            if entry.get("isMeta") or entry.get("isSidechain") or entry.get("isCompactSummary"):
                continue
            if "toolUseResult" in entry:
                continue
            content = (entry.get("message") or {}).get("content")
            if isinstance(content, list):
                content = " ".join(
                    str(p.get("text") or "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                )
            if content:
                out.append(
                    (
                        _iso(entry.get("timestamp")),
                        os.path.basename(str(entry.get("cwd") or "").rstrip("\\/")),
                        str(content),
                    )
                )
    return out


def _codex_said(root: str) -> list[tuple[str, str, str]]:
    out = []
    files = glob.glob(os.path.join(root, "sessions", "**", "rollout-*.jsonl"), recursive=True)
    for path in _newest_first(files):
        project = ""
        for line in _read(path, 20_000_000).splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            payload = entry.get("payload") if isinstance(entry, dict) else None
            if not isinstance(payload, dict):
                continue
            if entry.get("type") == "session_meta":
                project = os.path.basename(str(payload.get("cwd") or "").rstrip("\\/"))
            if payload.get("type") != "message" or payload.get("role") != "user":
                continue
            parts = payload.get("content") or []
            text = (
                " ".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
                if isinstance(parts, list)
                else str(parts)
            )
            out.append((_iso(entry.get("timestamp")), project, text))
    return out


def _gemini_said(root: str) -> list[tuple[str, str, str]]:
    out = []
    for path in _newest_first(glob.glob(os.path.join(root, "tmp", "*", "logs.json"))):
        try:
            entries = json.loads(_read(path, 20_000_000) or "[]")
        except ValueError:
            continue
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, dict) and entry.get("type") == "user" and entry.get("message"):
                out.append((_iso(entry.get("timestamp")), "", str(entry["message"])))
    return out


def gather(cli: str, since: str | None = None) -> Gathered:
    """What `cli` keeps on the person: its memory files (changed since `since`, or all on a
    first read) and what the person said in its chats after `since`, newest first, within a
    budget. Secrets are masked; a message a CLI added to the turn is left out."""
    root = home(cli)
    found = Gathered(read_at=_iso(datetime.now(UTC).isoformat()))
    if not os.path.isdir(root):
        return found
    budget = LATER_BUDGET if since else FIRST_BUDGET
    files = budget // 2  # memory files take at most half: the chats get the rest
    for path in _memory_files(cli, root):
        if not os.path.isfile(path):
            continue
        if since and _iso(os.path.getmtime(path)) <= since:
            continue
        text = mask(_read(path, MEMORY_CHARS).strip())[: max(files, 0)]
        if text:
            found.memory.append((os.path.relpath(path, root), text))
            files -= len(text)
            budget -= len(text)
    said = {"claude": _claude_said, "codex": _codex_said, "gemini": _gemini_said}[cli](root)
    said.sort(key=lambda s: s[0], reverse=True)
    seen: set[str] = set()
    for at, project, raw in said:
        if not at or (since and at <= since):
            continue
        if NOT_SAID.match(str(raw)):
            continue
        text = _text(raw, SAID_CHARS)
        if len(text) < 12 or text in seen:  # "yes", "go ahead": nothing to keep
            continue
        if budget - len(text) < 0:
            break
        seen.add(text)
        found.said.append((at, project, text))
        budget -= len(text)
    return found
