"""Run a task now with an AI command-line tool on this machine.

Models normally pull their work on a schedule (the worker prompt). A person can also start one
task at once from the workspace: it launches the CLI as the task's model, streams what the CLI
does into the page, and keeps everything a run touches on a short leash:

- the CLI starts in an empty temporary folder, in restricted mode (`--restricted`: none of the
  person's own settings files, so none of their hooks; an older Claude Code loads project
  settings only, which that folder lacks), and loads only this workspace's MCP server
  (`--strict-mcp-config`)
- a login that fails an answer, though Claude Code says it is signed in, shows it signed out
  with how to sign in again, until the person signs in or checks again
- it may use the workspace's tools and nothing else: no built-in tools at all (`--tools ""`,
  so no shell, file access or web), and nothing needs asking (`--permission-mode dontAsk`)
- it connects with a credential made for this run alone, scoped to the task's project and
  revoked the moment the run ends (the MCP configuration holding it is deleted too)
- a run that stops before finishing leaves a blocker on the task saying why, instead of a
  claim that only expires when its lease runs out
- it carries a contract (anchoring.py): its prompt opens with it, Claude Code's hooks from a
  settings file made for the run keep it in scope and bring it back as the run goes, the
  app's MCP replies repeat its line, and what the hooks did goes into the run's record

A run of a skill that makes files (a PDF, a deck) works in a folder of its own under the
outputs folder instead: it holds copies of the skill's files and of the skills it depends on,
and the CLI may read and write files there and run Python (`python ...`), still with no web.
The copies go when the run ends; what the run made stays, listed on the skill's page.

The workspace never handles a sign-in. The CLI keeps its own login; when it is signed out, the
workspace says so and can open a terminal where the person signs in.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import timedelta
from typing import IO, Any

from workspace_connectors.providers import SERVER_NAME
from workspace_core.clock import iso
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Actor, Task
from workspace_core.domain.schedule import zone
from workspace_core.errors import Conflict, NotFound, WorkspaceError
from workspace_core.ids import new_id
from workspace_core.services.workflows import TOOL
from workspace_core.workspace import Workspace

from . import anchoring
from .templates import TemplateLibrary

INGESTION = ("distill", "reconcile", "merge", "digest")  # see workspace_core distill.INGESTION

log = logging.getLogger(__name__)

ACTIVE = ("starting", "running")
RUN_LABEL = "Run from the workspace"  # the label of a run's own credential
LEFTOVER_MARGIN = 300  # seconds past a run's time limit after which its credential is a leftover
MAX_EVENTS = 2000
KEEP_RUNS = 30  # in memory; every run's stream is also kept on disk (STREAMS)
KEEP_STREAMS = 200  # runs whose streams stay on disk, newest first
STREAMS = "runs"  # the folder in the data folder that holds them
# What never reaches a stream, on screen or on disk: credentials a run may print or read.
SECRETS = (
    re.compile(r"\b(wst|sk|pk|rk|ghp|gho|ghs|github_pat|xox[abpr])[-_][A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"(?i)\b(bearer)(\s+)[A-Za-z0-9._~+/\-]{12,}=*"),
    re.compile(r"(?i)\b(token|api[-_]?key|password|passwd|secret)(\s*[:=]\s*)[^\s\"',;]{6,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def mask(text: str) -> str:
    """The text with anything that looks like a credential replaced by a marker."""
    out = str(text)
    for pattern in SECRETS:
        out = pattern.sub(_masked, out)
    return out


def _masked(found: re.Match[str]) -> str:
    groups = found.groups()
    if (
        len(groups) >= 2
        and groups[1] is not None
        and groups[0]
        and not groups[0].startswith(("wst", "sk", "pk", "rk", "gh", "github", "xox"))
    ):
        return f"{groups[0]}{groups[1]}[masked]"  # keep the label, drop the value
    return "[masked]"


def _masked_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: mask(v) if isinstance(v, str) else v for k, v in fields.items()}


# What a run that makes files may use besides the workspace's tools: files in its own folder
# (restricted mode keeps them there) and Python.
FILE_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "Bash")
FILE_ALLOWED = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash(python:*)",
    "Bash(python3:*)",
    "Bash(py:*)",
)
# What the external challenger may use besides the workspace's tools: reading the web, and
# nothing else (no files, no shell). Only its runs (task template "challenge") get these.
CHALLENGER_TOOLS = ("WebSearch", "WebFetch")
SKIPPED = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".DS_Store")
# Added to Claude Code's own instructions when it answers with no tools at all: those describe
# tools, and without this line it writes out calls it cannot make instead of the answer.
NO_TOOLS = "You have no tools in this conversation. Reply once, with the finished answer only."
# A connector read's whole system prompt, in place of Claude Code's own (about 3,000 tokens,
# about coding, sent again on every turn of a read).
READ_SYSTEM = (
    "You read a person's connected apps for them, read-only, with only the tools you are "
    "given: never send, post, reply, create, change, delete or pay for anything. Do what the "
    "request says, then reply once, with the JSON it asks for and nothing else."
)
# After an answer run's packet: its brief names the app's tools, which this run does not have.
ANSWER_ONLY = (
    "This run has no tools: leave aside any call named above. Reply once with the whole result "
    "as Markdown and nothing else. It is saved to the project's Outputs and the run is closed "
    "for you."
)
# In a run's folder while it runs: its task and what was copied in, so a folder a stopped server
# left behind can still be tidied (the copies removed, what it made listed with its task).
MARKER = ".run.json"


@dataclass(frozen=True)
class RunnerSpec:
    id: str
    label: str
    provider: str  # the provider of the model a run acts as (see workspace_connectors)
    executable: str
    install: str
    sign_in: tuple[str, ...]
    one_click: bool  # started from the workspace; otherwise run from a copied prompt


RUNNERS: dict[str, RunnerSpec] = {
    spec.id: spec
    for spec in (
        RunnerSpec(
            id="claude",
            label="Claude Code",
            provider="claude-code",
            executable="claude",
            install="npm install -g @anthropic-ai/claude-code",
            sign_in=("auth", "login"),
            one_click=True,
        ),
        RunnerSpec(
            id="codex",
            label="ChatGPT (Codex CLI)",
            provider="codex",
            executable="codex",
            install="npm install -g @openai/codex",
            sign_in=("login",),
            one_click=False,
        ),
        # Gemini CLI signs in on its first run (Login with Google), so signing in opens it.
        RunnerSpec(
            id="gemini",
            label="Gemini CLI",
            provider="gemini",
            executable="gemini",
            install="npm install -g @google/gemini-cli",
            sign_in=(),
            one_click=False,
        ),
    )
}

# Codex and Gemini CLI have tools of their own and no switch that takes them all away, so a
# one-answer ask runs them in an empty folder, without the person's MCP servers, and says this
# first. (Claude Code takes NO_TOOLS as its system prompt, and has no tools at all.)
ANSWER_ONLY = (
    "Answer from this prompt alone: run no commands, open no files, call no tools. Reply "
    "once, with the finished answer only."
)
# What Gemini CLI prints on stdout beside its answer.
GEMINI_NOISE = ("Loaded cached credentials.",)
# How a Claude Code keeps the person's own settings files, and so their hooks, out of what the
# app starts: `--restricted` where it has it; before that, loading project settings only, which
# the run's own folder does not have. Read from the CLI's help, once per command.
# Starts of Claude Code to wait out the account's connectors loading, a pause apart. A real
# Drive read loaded in about one start of three or four; with only the read connector loaded a
# start is cheap.
READ_BUDGET_USD = 0.02  # at most this a connector read; a typical one costs under a cent
ACCOUNT_TRIES = 3  # each start waits for the account's connectors to connect
ACCOUNT_PAUSE = 2.0  # seconds between starts
# A listing loads every connector, to learn their tools: fewer starts.
LIST_TRIES = 4
READ_TURNS = 4  # a connector read: one listing, one step of opens, the answer, one spare
MCP_OUTPUT_TOKENS = 8000  # at most, per tool answer in a connector read
ACCOUNT_LINE = re.compile(r"^(claude\.ai [^:\n]+):", re.M)  # in `claude mcp list`
SERVER_LINE = re.compile(r"^([^\s:][^:\n]*):\s", re.M)  # every server `claude mcp list` names
FENCES = (
    ("--restricted", ("--restricted",)),
    ("--setting-sources", ("--setting-sources", "project")),
)
# A login that no longer works: Claude Code still says it is signed in (`auth status`), but
# every answer fails to authenticate.
# The same for Codex and Gemini CLI: a login that has run out, or a key that no longer works.
OTHER_AUTH = re.compile(
    r"\b401\b|unauthori[sz]ed|not logged in|please log ?in|login (?:is )?required|"
    r"api key not valid|invalid_api_key|credentials (?:have )?expired",
    re.I,
)
AUTH_FAILED = re.compile(
    r"authentication_error|failed to authenticate|oauth access token is invalid|invalid api key",
    re.I,
)


def fence(help_text: str) -> list[str] | None:
    """The options that keep the person's settings out, for the Claude Code whose help this
    is; None when it has neither."""
    return next((list(argv) for flag, argv in FENCES if flag in help_text), None)


def error_line(*texts: str) -> str:
    """What went wrong, from what a CLI printed: the line that names the error, not the last
    frame of a stack trace."""
    lines = [
        line.strip()
        for text in texts
        for line in str(text or "").splitlines()
        if line.strip() and not line.strip().startswith("at ")
    ]
    named = [line for line in lines if "error" in line.lower() and "occurred" not in line.lower()]
    return (named or lines or ["it stopped"])[0][:200]


def gemini_signed_in() -> bool | None:
    """Gemini CLI is signed in when it keeps a Google login or a key is set; else it cannot be
    told without starting it, which may ask the person to sign in."""
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return True
    saved = os.path.join(os.path.expanduser("~"), ".gemini", "oauth_creds.json")
    return True if os.path.isfile(saved) else None


@dataclass(frozen=True)
class RunnerStatus:
    id: str
    label: str
    provider: str
    one_click: bool
    installed: bool
    version: str | None
    signed_in: bool | None  # None: could not tell
    install: str
    sign_in: str
    actor_id: str | None = None  # the model its runs act as, once there is one
    detail: str = ""


@dataclass
class LocalRun:
    id: str
    runner: str
    task_id: str
    task_title: str
    actor_id: str
    started_by: str
    status: str = "starting"  # starting | running | succeeded | failed | cancelled | timed_out
    # why a run being stopped will end (cancelled | timed_out); it stays running until the
    # process has exited and everything about it is recorded
    stopping: str | None = None
    tools_failed: bool = False  # the app's tools did not connect: nothing could be done
    started_at: str = ""
    finished_at: str | None = None
    exit_code: int | None = None
    summary: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    folder: str | None = None  # where a run that makes files worked, and what it left there
    made: list[dict[str, Any]] = field(default_factory=list)
    contract: dict[str, Any] | None = None  # what it was for and held to (anchoring.py)
    checks: dict[str, Any] | None = None  # re-anchors, blocked calls, the finishing check

    def to_dict(self, after: int = 0) -> dict[str, Any]:
        data = asdict(self)
        data["events"] = [e for e in self.events if e["seq"] > after]
        return data


Resolve = Callable[[RunnerSpec], "list[str] | None"]


def resolve_on_path(spec: RunnerSpec) -> list[str] | None:
    path = shutil.which(spec.executable)
    return [path] if path else None


def _quiet() -> dict[str, Any]:
    """No console window on Windows; its own process group, so the whole tree can stop."""
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        return {"creationflags": flags}
    return {"start_new_session": True}


def _call(argv: list[str], timeout: float = 30) -> subprocess.CompletedProcess[str] | None:
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
            **_quiet(),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def detect(spec: RunnerSpec, resolve: Resolve = resolve_on_path) -> RunnerStatus:
    """Whether the CLI is installed and signed in, without touching its credentials."""
    command = resolve(spec)
    sign_in = " ".join((spec.executable, *spec.sign_in))
    base: dict[str, Any] = {
        "id": spec.id,
        "label": spec.label,
        "provider": spec.provider,
        "one_click": spec.one_click,
        "install": spec.install,
        "sign_in": sign_in,
    }
    if not command:
        return RunnerStatus(
            **base,
            installed=False,
            version=None,
            signed_in=None,
            detail=f"{spec.label} is not installed on this computer.",
        )
    probe = _call([*command, "--version"])
    version = (probe.stdout.strip().splitlines() or [""])[0] if probe and probe.stdout else None
    signed_in: bool | None = None
    if spec.id == "claude":
        status = _call([*command, "auth", "status", "--json"])
        try:
            signed_in = bool(json.loads(status.stdout).get("loggedIn")) if status else None
        except (ValueError, AttributeError):
            signed_in = None
    elif spec.id == "codex":
        status = _call([*command, "login", "status"])
        signed_in = status.returncode == 0 if status else None
    elif spec.id == "gemini":
        signed_in = gemini_signed_in()
    detail = {
        True: "Signed in and ready.",
        False: f"Not signed in. Sign in with `{sign_in}`.",
        None: "Installed; could not tell whether it is signed in.",
    }[signed_in]
    return RunnerStatus(**base, installed=True, version=version, signed_in=signed_in, detail=detail)


def terminal_command(argv: list[str], title: str) -> list[str] | None:
    """A command that opens a visible terminal running `argv`, or None where there is none."""
    if os.name == "nt":
        return ["cmd", "/c", "start", title, "cmd", "/k", *argv]
    if sys.platform == "darwin":
        script = shlex.join(argv).replace("\\", "\\\\").replace('"', '\\"')
        return [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script "{script}"',
            "-e",
            'tell application "Terminal" to activate',
        ]
    for terminal, flag in (
        ("x-terminal-emulator", "-e"),
        ("gnome-terminal", "--"),
        ("konsole", "-e"),
        ("xterm", "-e"),
    ):
        found = shutil.which(terminal)
        if found:
            return [found, flag, *argv]
    return None


def describe(line: str) -> list[dict[str, Any]]:
    """What one line of Claude Code's stream-json output means, for a person watching. Any
    shape is read: content given as plain text or as parts, a tool's result holding an image it
    looked at; what this does not understand becomes nothing, never an error."""
    try:
        message = json.loads(line)
    except ValueError:
        return [{"kind": "log", "text": line}] if line.strip() else []
    if not isinstance(message, dict):
        return []
    kind = message.get("type")
    if kind == "system" and message.get("subtype") == "init":
        servers = [s for s in message.get("mcp_servers") or [] if isinstance(s, dict)]
        state = next((s.get("status") for s in servers if s.get("name") == SERVER_NAME), None)
        model = message.get("model") or "the model"
        return [
            {
                "kind": "status",
                "text": f"Started {model}; workspace tools {state or 'missing'}.",
                "tools": state or "missing",
            }
        ]
    body = message.get("message")
    content = body.get("content") if isinstance(body, dict) else None
    if isinstance(content, str):  # a message given as plain text
        content = [{"type": "text", "text": content}]
    blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    if kind == "assistant":
        out: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") == "text" and str(block.get("text") or "").strip():
                out.append({"kind": "text", "text": str(block["text"]).strip()})
            elif block.get("type") == "tool_use":
                name = str(block.get("name") or "").removeprefix(f"mcp__{SERVER_NAME}__")
                out.append({"kind": "tool", "name": name, "text": _brief(block.get("input"))})
        return out
    if kind == "user":
        out = []
        for block in blocks:
            if block.get("type") == "tool_result":
                text = " ".join(_text_of(block.get("content")).split())
                out.append(
                    {"kind": "tool_result", "ok": not block.get("is_error"), "text": text[:400]}
                )
        return out
    if kind == "result":
        ok = message.get("subtype") == "success" and not message.get("is_error")
        text = str(message.get("result") or message.get("subtype") or "")
        event: dict[str, Any] = {"kind": "result", "ok": ok, "text": text.strip()}
        spent = usage_of(message)
        if spent is not None:
            event["usage"] = spent
        return [event]
    return []


def usage_of(message: dict[str, Any]) -> dict[str, Any] | None:
    """What Claude Code says a run or an answer used, from its final message: the model, the
    tokens in, out, read from the cache and written to it, and what it cost. None when it says
    nothing."""
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    models = message.get("modelUsage")
    model = "claude"
    if isinstance(models, dict) and models:
        model = max(
            models,
            key=lambda name: (
                float((models.get(name) or {}).get("costUSD") or 0)
                if isinstance(models.get(name), dict)
                else 0.0
            ),
        )
    cost = message.get("total_cost_usd")
    return {
        "model": str(model),
        "tokens_in": int(usage.get("input_tokens") or 0),
        "tokens_out": int(usage.get("output_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "cost": float(cost) if isinstance(cost, int | float) else None,
        "ms": int(message.get("duration_ms") or 0) or None,
    }


def codex_usage(stream: str) -> dict[str, Any] | None:
    """What `codex exec --json` says a turn used (its `usage` lines, added up), or None when
    it says nothing."""
    tokens_in = tokens_out = cached = 0
    said = False
    for line in stream.splitlines():
        try:
            found = json.loads(line)
        except ValueError:
            continue
        usage = found.get("usage") if isinstance(found, dict) else None
        if not isinstance(usage, dict):
            continue
        said = True
        tokens_in += int(usage.get("input_tokens") or 0)
        tokens_out += int(usage.get("output_tokens") or 0)
        cached += int(usage.get("cached_input_tokens") or 0)
    if not said:
        return None
    return {
        "model": "codex",
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cache_read": cached,
        "cache_write": 0,
        "cost": None,
        "ms": None,
    }


def _text_of(content: Any) -> str:
    """A tool result's text: given as a string, or as parts (text, or an image it looked at)."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    parts = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict):
            parts.append(
                "[an image]" if part.get("type") == "image" else str(part.get("text") or "")
            )
    return " ".join(p for p in parts if p)


def _brief(arguments: Any) -> str:
    if not isinstance(arguments, dict):
        return ""
    for key in ("title", "summary", "task_id", "query", "item_id", "entry_id", "type"):
        if arguments.get(key):
            return " ".join(str(arguments[key]).split())[:140]
    return ""


class Runners:
    """The CLIs on this machine and the runs started from the workspace."""

    def __init__(
        self,
        ws: Workspace,
        templates: TemplateLibrary,
        *,
        base_url: str,
        timeout: float = 1200.0,
        resolve: Resolve = resolve_on_path,
        popen: Callable[..., Any] = subprocess.Popen,
        outputs: str | None = None,
    ) -> None:
        self.ws = ws
        self.templates = templates
        self.base_url = base_url.rstrip("/")
        # where runs that make files get their folders (the exports folder)
        self.outputs = outputs or os.path.join(ws.data_dir, "exports")
        self.timeout = timeout
        self.resolve = resolve
        self.popen = popen
        self.runs: dict[str, LocalRun] = {}
        self.streams = os.path.join(ws.data_dir, STREAMS)
        self.contracts = anchoring.Contracts()  # the app's MCP replies repeat each run's line
        self._procs: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._status: dict[str, tuple[float, RunnerStatus]] = {}
        self._fences: dict[tuple[str, ...], list[str] | None] = {}  # per command, from its help
        self._expired: set[str] = set()  # CLIs whose login failed an answer

    # ---------------------------------------------------------------- the CLIs

    def statuses(self, who: Principal, *, refresh: bool = False) -> list[RunnerStatus]:
        """Each CLI's state. `refresh` is the person checking again: it also forgets a login
        found not to work, in case they signed in since."""
        who.require("workspace.admin")
        if refresh:
            self._expired.clear()
        return [self.status(spec, refresh=refresh) for spec in RUNNERS.values()]

    def status(self, spec: RunnerSpec, *, refresh: bool = False) -> RunnerStatus:
        cached = self._status.get(spec.id)
        if cached and not refresh and time.monotonic() - cached[0] < 15:
            found = cached[1]
        else:
            found = detect(spec, self.resolve)
            self._status[spec.id] = (time.monotonic(), found)
        if spec.id in self._expired and found.installed:
            # It says it is signed in, but its login failed an answer: signed out until the
            # person signs in again (or checks again).
            found = replace(
                found,
                signed_in=False,
                detail=f"Its login no longer works: sign in again with `{found.sign_in}`.",
            )
        actor = self._actor(spec)
        return RunnerStatus(**{**asdict(found), "actor_id": actor.id if actor else None})

    def _fence(self, spec: RunnerSpec, command: list[str]) -> list[str]:
        """How this Claude Code keeps the person's own settings out of what the app starts
        (FENCES), read once from its help; refused, with how to update it, when it has no way."""
        key = tuple(command)
        if key not in self._fences:
            found = _call([*command, "--help"])
            self._fences[key] = fence(found.stdout if found and found.stdout else "")
        argv = self._fences[key]
        if argv is None:
            raise Conflict(
                f"This {spec.label} cannot keep your own settings and hooks out of the app's "
                f"runs: update it ({spec.install})."
            )
        return argv

    def _login_failed(self, spec: RunnerSpec) -> str:
        """Mark the CLI signed out after an answer failed to authenticate; what to tell."""
        self._expired.add(spec.id)
        sign_in = " ".join((spec.executable, *spec.sign_in))
        return f"{spec.label}'s login no longer works: sign in again with `{sign_in}`."

    def sign_in(self, who: Principal, runner_id: str) -> dict[str, Any]:
        """Open a terminal where the person signs in; the CLI keeps the login, never us."""
        who.require("workspace.admin")
        spec = self._spec(runner_id)
        command = self.resolve(spec)
        text = " ".join((spec.executable, *spec.sign_in))
        opener = (
            terminal_command([*command, *spec.sign_in], f"Sign in to {spec.label}")
            if command
            else None
        )
        if opener is None:
            return {"opened": False, "command": text}
        try:
            self.popen(opener, stdin=subprocess.DEVNULL)
        except OSError:
            return {"opened": False, "command": text}
        self._status.pop(spec.id, None)
        self._expired.discard(spec.id)
        return {"opened": True, "command": text}

    # ---------------------------------------------------------------- runs

    def sweep(self) -> int:
        """Revoke run credentials no run can still hold. A run's credential is revoked when
        the run ends; one whose server stopped mid-run (closed, crashed) stays behind. No run
        outlives its time limit, so a run credential older than that is a leftover: safe to
        revoke even while another server process on the same workspace is running."""
        owner = self.ws.owner()
        cutoff = iso(self.ws.rt.clock.now() - timedelta(seconds=self.timeout + LEFTOVER_MARGIN))
        revoked = 0
        for actor in self.ws.actors.list(owner, include_disabled=True):
            if actor.kind != "model":
                continue
            for credential in self.ws.actors.credentials(owner, actor.id):
                label = str(credential.label or "")
                if credential.revoked_at or not label.startswith(f"{RUN_LABEL} ("):
                    continue
                if credential.created_at > cutoff:
                    continue
                self.ws.actors.revoke(owner, credential.id)
                revoked += 1
        self._tidy(owner)
        return revoked

    def _tidy(self, owner: Principal) -> None:
        """Finish the folders of runs a stopped server left behind: the copies go, and what
        each made is listed with its task (an empty one goes)."""
        root = os.path.join(self.outputs, "skill-runs")
        if not os.path.isdir(root):
            return
        live = {r.folder for r in self.runs.values() if r.status in ACTIVE and r.folder}
        oldest = time.time() - (self.timeout + LEFTOVER_MARGIN)
        for name in os.listdir(root):
            folder = os.path.join(root, name)
            marker = os.path.join(folder, MARKER)
            if folder in live or not os.path.isfile(marker) or os.path.getmtime(marker) > oldest:
                continue
            try:
                with open(marker, encoding="utf-8") as handle:
                    info = json.load(handle)
                copies = {str(k): set(v) for k, v in dict(info.get("copies") or {}).items()}
                made = _gather(folder, copies)
                if made:
                    self.ws.skills.record_files(
                        owner, str(info["task_id"]), folder=folder, files=made
                    )
                else:
                    shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                log.warning("Could not tidy the run folder %s", folder, exc_info=True)

    def start(
        self, who: Principal, runner_id: str, task_id: str, *, model: str | None = None
    ) -> LocalRun:
        """Run one task now with this machine's CLI, acting as the task's model; `model` is
        the CLI's own name for the model to use (an orchestrator's agent picks one)."""
        who.require("workspace.admin")
        self.sweep()
        spec = self._spec(runner_id)
        if not spec.one_click:
            raise Conflict(
                f"{spec.label} runs from a copied prompt for now: copy the task's prompt into it."
            )
        status = self.status(spec, refresh=True)
        command = self.resolve(spec)
        if not status.installed or not command:
            raise Conflict(f"{spec.label} is not installed on this computer: {spec.install}")
        if status.signed_in is False:
            raise Conflict(f"{spec.label} is not signed in. Sign in first: {status.sign_in}")
        fenced = self._fence(spec, command)  # before anything is made for the run
        with self._lock:
            if any(r.task_id == task_id and r.status in ACTIVE for r in self.runs.values()):
                raise Conflict("This task is already running here.")
        task = self.ws.tasks.get(who, task_id)
        if model is None and spec.id == "claude" and task.template in INGESTION:
            model = self.ws.distill.settings(who).get("model")  # reading what came in: Haiku
        actor, task = self._assignee(who, spec, task)
        if task.status != "ready":
            raise Conflict(
                f"The task is {task.status.replace('_', ' ')}: only a ready task can run."
            )
        if task.next_due_at and task.next_due_at > iso(self.ws.rt.clock.now()):
            raise Conflict(f"The task is not due until {task.next_due_at}.")
        about = dict(task.provenance.get("skill") or {})
        copying: list[tuple[str, str]] = []
        if task.template == "skill" and about.get("files"):
            names = [str(n) for n in about.get("names") or [] if n]
            copying = (
                self._plan_many(who, names)
                if len(names) > 1
                else self._plan(who, str(about.get("name") or ""))
            )
        web = CHALLENGER_TOOLS if task.template == "challenge" else ()
        # A workflow's connector step: its run may also call these tools of the person's own
        # MCP servers (named in full, read-only unless they said otherwise), so for this run
        # alone Claude Code loads those servers too.
        connector = [
            str(t) for t in (about.get("connector") or {}).get("tools") or [] if TOOL.match(str(t))
        ]
        task_id = task.id

        run = LocalRun(
            id=new_id("lrun", self.ws.rt.clock.now()),
            runner=spec.id,
            task_id=task.id,
            task_title=task.title,
            actor_id=actor.id,
            started_by=who.actor_id,
            started_at=iso(self.ws.rt.clock.now()),
        )
        connection = self.ws.actors.issue_token(
            who,
            actor.id,
            label=f"{RUN_LABEL} ({run.id})",
            projects=[task.project_id] if task.project_id else None,
        )
        folder = tempfile.mkdtemp(prefix="workspace-run-")
        config = os.path.join(folder, "mcp.json")
        with open(config, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "mcpServers": {
                        SERVER_NAME: {
                            "type": "http",
                            "url": f"{self.base_url}/mcp",
                            "headers": {"Authorization": f"Bearer {connection.token}"},
                        }
                    }
                },
                handle,
            )
        os.chmod(config, 0o600)
        argv = [
            *command,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            *fenced,
            *(["--model", model] if model else []),
            "--tools",
            ",".join(FILE_TOOLS) if copying else ",".join(web),
            "--mcp-config",
            config,
            *([] if connector else ["--strict-mcp-config"]),
            "--permission-mode",
            "dontAsk",
            "--allowedTools",
            f"mcp__{SERVER_NAME}",
            *(FILE_ALLOWED if copying else web),
            *connector,
            "--no-session-persistence",
        ]
        with self._lock:
            self.runs[run.id] = run
            self._trim()
        self._keep(run)
        self._prune_streams()
        self._add(run, "status", text=f"Starting {spec.label} as {actor.name}.")
        if connector:
            self._add(
                run,
                "status",
                text="It may also use these tools of your own connectors: " + ", ".join(connector),
            )
        copies: dict[str, set[str]] = {}
        try:
            if copying:
                run.folder, copies = self._prepare(str(about.get("name")), copying, task_id)
                self._add(
                    run,
                    "status",
                    text=f"It works in {run.folder} with file and Python tools; what it makes "
                    "stays there.",
                )
            run.contract = anchoring.build(
                self.ws,
                task,
                run_id=run.id,
                minutes=int(self.timeout // 60),
                folder=run.folder,
                tools=[*(FILE_TOOLS if copying else web), *connector],
            )
            argv += ["--settings", anchoring.write(run.contract, folder)]
            self.contracts.register(connection.credential.id, run.contract)
            proc = self.popen(
                argv,
                cwd=run.folder or folder,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **_quiet(),
            )
        except OSError as exc:
            self._cleanup(who, run, connection.credential.id, folder)
            if run.folder:
                shutil.rmtree(run.folder, ignore_errors=True)
                run.folder = None
            run.status, run.finished_at = "failed", iso(self.ws.rt.clock.now())
            self._add(run, "error", text=f"Could not start {spec.label}: {exc}")
            return run
        self._procs[run.id] = proc
        run.status = "running"
        self._event(who, "runner.started", run, {"runner": spec.id})
        opening = anchoring.prompt_block(run.contract) + "\n" if run.contract else ""
        prompt = opening + self.templates.run_prompt(self.ws.info().name, task.id)
        threading.Thread(target=self._feed, args=(proc, prompt), daemon=True).start()
        errors = threading.Thread(target=self._read, args=(run, proc.stderr, "stderr"), daemon=True)
        errors.start()
        threading.Thread(
            target=self._watch,
            args=(who, run, proc, connection.token, connection.credential.id, folder, errors),
            kwargs={"copies": copies},
            daemon=True,
        ).start()
        timer = threading.Timer(self.timeout, self._stop, args=(run.id, "timed_out"))
        timer.daemon = True
        timer.start()
        return run

    def ask(
        self,
        who: Principal,
        prompt: str,
        *,
        timeout: float = 180.0,
        job: str = "ask",
        runner: str = "claude",
        model: str | None = None,
    ) -> str:
        """One answer from a CLI on this computer (Claude Code unless `runner` names Codex or
        Gemini CLI), knowing only what the prompt says: one side of a comparison with and
        without the Brain, a follow-up question in the goals interview, a step of the
        knowledge agent. In an empty temporary folder that goes afterwards, with none of the
        person's MCP servers and no saved session. `model` is one the CLI offers (blank: its
        own default). What it used is counted under `job` (a check, a comparison, the
        knowledge agent) in the Brain's cost report."""
        return str(
            self.ask_measured(who, prompt, timeout=timeout, job=job, runner=runner, model=model)[
                "answer"
            ]
        )

    def ask_measured(
        self,
        who: Principal,
        prompt: str,
        *,
        timeout: float = 180.0,
        job: str = "ask",
        runner: str = "claude",
        model: str | None = None,
    ) -> dict[str, Any]:
        """`ask`, with what the call used: {"answer", "model", "tokens_in", "tokens_out",
        "cost", "ms", "measured"}. Claude Code reports its usage; Codex and Gemini CLI do not
        in this mode, so their tokens are estimated from the text and priced from the table
        (`measured` false)."""
        if runner != "claude":
            answer, spent = self._ask_other(who, self._spec(runner), prompt, timeout, job, model)
            return {"answer": answer, **spent}
        started = time.monotonic()
        found = self.ask_json(who, prompt, timeout=timeout, model=model)
        reported = usage_of(found)
        if reported is not None:
            self.count_usage(job, reported)
        answer = str(found.get("result") or "").strip()
        used = dict(
            reported
            or {
                "model": "claude",
                "tokens_in": len(prompt) // 4,
                "tokens_out": len(answer) // 4,
                "cost": None,
            }
        )
        if not used.get("ms"):
            used["ms"] = int((time.monotonic() - started) * 1000) or None
        used["measured"] = reported is not None
        return {"answer": answer, **used}

    def _ready(self, spec: RunnerSpec) -> list[str]:
        """The CLI's command, once it is here and not signed out."""
        status = self.status(spec)
        command = self.resolve(spec)
        if not status.installed or not command:
            raise Conflict(f"{spec.label} is not installed on this computer: {spec.install}")
        if status.signed_in is False:
            raise Conflict(f"{spec.label} is not signed in. Sign in first: {status.sign_in}")
        return command

    def _ask_other(
        self,
        who: Principal,
        spec: RunnerSpec,
        prompt: str,
        timeout: float,
        job: str,
        model: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """`ask` of Codex (`codex exec`: read-only sandbox, no MCP servers, the last message
        kept in a file) or Gemini CLI (no MCP servers, no extensions, the prompt on stdin,
        which version 0.1 reads only when no `-p` is given)."""
        who.require("workspace.admin")
        command = self._ready(spec)
        folder = tempfile.mkdtemp(prefix="workspace-ask-")
        last = os.path.join(folder, "answer.txt")
        named = ["--model", model] if model else []
        if spec.id == "codex":
            argv = [
                *command,
                "exec",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "-c",
                "mcp_servers={}",
                "--output-last-message",
                last,
                *named,
                "-",
            ]
        else:
            argv = [
                *command,
                "--allowed-mcp-server-names",
                "none",
                "--extensions",
                "none",
                *named,
            ]
        started = time.monotonic()
        try:
            try:
                proc = self.popen(
                    argv,
                    cwd=folder,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **_quiet(),
                )
            except OSError as exc:
                raise Conflict(f"Could not start {spec.label}: {exc}") from exc
            try:
                out, err = proc.communicate(f"{ANSWER_ONLY}\n\n{prompt}", timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill(proc)
                raise Conflict(f"{spec.label} took too long to answer.") from exc
            if proc.returncode:
                said = f"{err}\n{out}"
                if AUTH_FAILED.search(said) or OTHER_AUTH.search(said):
                    raise Conflict(self._login_failed(spec))
                raise Conflict(f"{spec.label} could not answer: {error_line(err, out)}")
            if spec.id == "codex":
                try:
                    with open(last, encoding="utf-8") as handle:
                        answer = handle.read()
                except OSError as exc:
                    raise Conflict(f"{spec.label} gave no answer.") from exc
            else:
                answer = "\n".join(
                    line for line in (out or "").splitlines() if line.strip() not in GEMINI_NOISE
                )
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        # Neither says what it used in this mode: the call is counted, its tokens estimated
        # from the text (characters / 4) and priced from the table, if it knows the model.
        spent = {
            "model": f"{spec.id}:{model}" if model else spec.id,
            "tokens_in": len(prompt) // 4,
            "tokens_out": len(answer) // 4,
            "ms": int((time.monotonic() - started) * 1000) or None,
            "measured": False,
        }
        self.count_usage(job, spent)
        return answer.strip(), {**spent, "cost": None}

    def ask_json(
        self, who: Principal, prompt: str, *, timeout: float = 180.0, model: str | None = None
    ) -> dict[str, Any]:
        """`ask` of Claude Code, returning its whole final message (the answer in `result`,
        and `usage`) without counting it anywhere."""
        who.require("workspace.admin")
        spec = RUNNERS["claude"]
        command = self._ready(spec)
        fenced = self._fence(spec, command)
        folder = tempfile.mkdtemp(prefix="workspace-ask-")
        config = os.path.join(folder, "mcp.json")
        with open(config, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": {}}, handle)
        argv = [
            *command,
            "-p",
            "--output-format",
            "json",
            *fenced,
            "--tools",
            "",
            "--mcp-config",
            config,
            "--strict-mcp-config",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
            "--system-prompt",
            NO_TOOLS,
            *(["--model", model] if model else []),
        ]
        try:
            try:
                proc = self.popen(
                    argv,
                    cwd=folder,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    **_quiet(),
                )
            except OSError as exc:
                raise Conflict(f"Could not start {spec.label}: {exc}") from exc
            try:
                out, _err = proc.communicate(prompt, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill(proc)
                raise Conflict(f"{spec.label} took too long to answer.") from exc
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        try:
            found = json.loads(out or "{}")
        except ValueError as exc:
            raise Conflict(f"{spec.label} gave an answer that could not be read.") from exc
        if not isinstance(found, dict) or found.get("is_error"):
            reason = (
                str((found or {}).get("result") or "it stopped")
                if isinstance(found, dict)
                else "it stopped"
            )
            if AUTH_FAILED.search(reason):
                raise Conflict(self._login_failed(spec))
            raise Conflict(f"{spec.label} could not answer: {reason[:200]}")
        self._expired.discard(spec.id)
        return found

    def ask_with_brain(
        self,
        who: Principal,
        prompt: str,
        *,
        brain: list[str],
        timeout: float = 240.0,
        model: str | None = None,
    ) -> dict[str, Any]:
        """One answer from Claude Code with the Brain's MCP server and nothing else: no
        built-in tools, none of the person's own MCP servers or connectors, the prompt on
        stdin (a Windows launcher cuts a long argument short). Returns its final message."""
        who.require("workspace.admin")
        spec = RUNNERS["claude"]
        command = self._ready(spec)
        fenced = self._fence(spec, command)
        folder = tempfile.mkdtemp(prefix="workspace-ask-")
        config = os.path.join(folder, "mcp.json")
        with open(config, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": {"contxt": {"command": brain[0], "args": brain[1:]}}}, handle)
        argv = [
            *command,
            "-p",
            "--output-format",
            "json",
            *fenced,
            "--tools",
            "",
            "--mcp-config",
            config,
            "--strict-mcp-config",
            "--allowedTools",
            "mcp__contxt",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
            *(["--model", model] if model else []),
        ]
        env = dict(os.environ, MCP_TIMEOUT="60000", ENABLE_CLAUDEAI_MCP_SERVERS="false")
        try:
            try:
                proc = self.popen(
                    argv,
                    cwd=folder,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    env=env,
                    **_quiet(),
                )
            except OSError as exc:
                raise Conflict(f"Could not start {spec.label}: {exc}") from exc
            try:
                out, err = proc.communicate(prompt, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _kill(proc)
                raise Conflict(f"{spec.label} took too long to answer.") from exc
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        try:
            found = json.loads(out or "{}")
        except ValueError as exc:
            raise Conflict(
                f"{spec.label} gave an answer that could not be read: {error_line(err, out)}"
            ) from exc
        if not isinstance(found, dict) or found.get("is_error"):
            reason = (
                str(found.get("result") or "it stopped")
                if isinstance(found, dict)
                else "it stopped"
            )
            if AUTH_FAILED.search(reason):
                raise Conflict(self._login_failed(spec))
            raise Conflict(f"{spec.label} could not answer: {reason[:200]}")
        self._expired.discard(spec.id)
        return found

    def account_servers(self, who: Principal, timeout: float = 90.0) -> list[dict[str, Any]]:
        """The MCP servers a signed-in Claude Code loads from the person's Claude account
        (claude.ai connectors), each with its status and its tools' names. They live in the
        account, not in a settings file, so they come from Claude Code itself: `claude mcp
        list` names them, and the first line Claude Code writes when it starts (its init
        message) gives their tools; the run is stopped there, before it answers. They load in
        the background, so a start that missed some is tried again (LIST_TRIES)."""
        who.require("workspace.admin")
        spec_of = self._spec("claude")
        command = self._ready(spec_of)
        expected = self._account_names(command)
        best: dict[str, Any] = {}
        for _ in range(LIST_TRIES if expected else 1):
            init = self._account_start(spec_of, command, "Reply OK.", timeout)[0]
            named = {
                str(s.get("name")) for s in init.get("mcp_servers") or [] if isinstance(s, dict)
            }
            if len(named & expected) >= len(set(best.get("named") or ()) & expected):
                best = {**init, "named": named}
            if expected <= named:
                break
        if best.get("subtype") != "init":
            raise Conflict(f"{spec_of.label} did not say which connectors your account has.")
        tools = _mcp_tools(best)
        found = []
        for server in best.get("mcp_servers") or []:
            if isinstance(server, dict):
                name = str(server.get("name") or "")
                found.append(
                    {
                        "name": name,
                        "status": str(server.get("status") or ""),
                        "tools": sorted(tools.get(_safe(name), [])),
                    }
                )
        for name in sorted(expected - set(best.get("named") or ())):
            found.append({"name": name, "status": "pending", "tools": []})
        return found

    def _account_names(self, command: list[str]) -> set[str]:
        """The account's connectors by name, as `claude mcp list` prints them."""
        return {n for n in self._mcp_names(command) if ACCOUNT_LINE.match(n + ":")}

    def _mcp_names(self, command: list[str]) -> set[str]:
        """Every MCP server Claude Code would load here, by name: the account's connectors
        and the person's own (user and project scope), as `claude mcp list` prints them."""
        try:
            proc = self.popen(
                [*command, "mcp", "list"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_account_env(),
                **_quiet(),
            )
            out, _ = proc.communicate(timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            return set()
        return {m.group(1).strip() for m in SERVER_LINE.finditer(out or "")}

    def _account_start(
        self,
        spec: RunnerSpec,
        command: list[str],
        prompt: str,
        timeout: float,
        extra: list[str] | None = None,
        until_result: bool = False,
        servers: list[str] | None = None,
        need_all: bool = True,
    ) -> list[dict[str, Any]]:
        """Start Claude Code with the account's connectors and read what it writes: its init
        message only, or (`until_result`) through to its result, unless the init shows that
        one of `servers` (with `need_all` off: every one of them) has not loaded, when it is
        stopped there."""
        folder = tempfile.mkdtemp(prefix="workspace-account-")
        argv = [
            *command,
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            # No fence here: Claude Code loads the account's connectors only with every
            # setting source (--restricted and --setting-sources both leave them out). No other
            # tool runs: none built in, only those allowed, and nobody to ask.
            "--tools",
            "",
            *(extra or ["--max-turns", "1"]),
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
        ]
        try:
            proc = self.popen(
                argv,
                cwd=folder,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=_account_env(),
                **_quiet(),
            )
        except OSError as exc:
            shutil.rmtree(folder, ignore_errors=True)
            raise Conflict(f"Could not start {spec.label}: {exc}") from exc

        def stop(messages: list[dict[str, Any]]) -> bool:
            last = messages[-1]
            if not until_result:
                return True
            if last.get("subtype") == "init" and servers:
                ready = _mcp_tools(last)
                missing = [s for s in servers if not ready.get(s)]
                # Not loaded: stopped before it answers, to try again.
                return bool(missing) if need_all else len(missing) == len(servers)
            return last.get("type") == "result"

        try:
            return _messages(proc, prompt, timeout, stop) or [{}]
        finally:
            _kill(proc)
            shutil.rmtree(folder, ignore_errors=True)

    def read_through(
        self,
        who: Principal,
        runner: str,
        *,
        server: str,
        spec: dict[str, Any],
        allowed: list[str],
        refused: list[str],
        prompt: str,
        timeout: float = 240.0,
        model: str | None = None,
    ) -> dict[str, Any]:
        """One read-only read of one connector by the CLI that has it (the heartbeat): the CLI
        gets that one MCP server and may call exactly the `allowed` tools, which Gnomon listed
        and found to only read; every other tool of the server is refused by name too, and
        with no one to ask (headless), nothing else can run. No built-in tools. The server's
        entry (which may hold a token) goes into a file made for this read and deleted after
        it. Returns {"text": the answer, "usage": what the CLI said it used, or None}."""
        if runner == "claude":
            return self.read_many(
                who,
                servers={server: spec},
                allowed={server: allowed},
                refused={server: refused},
                prompt=prompt,
                timeout=timeout,
                model=model,
            )
        who.require("workspace.admin")
        if not allowed:
            raise Conflict("No tool of this connector only reads: it is not read.")
        spec_of = self._spec(runner)
        command = self._ready(spec_of)
        folder = tempfile.mkdtemp(prefix="workspace-beat-")
        try:
            if spec_of.id == "codex":
                return self._read_codex(spec_of, command, folder, server, allowed, prompt, timeout)
            raise Conflict(f"Gnomon does not read connectors through {spec_of.label} yet.")
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def read_many(
        self,
        who: Principal,
        *,
        servers: dict[str, dict[str, Any]],
        allowed: dict[str, list[str]],
        refused: dict[str, list[str]],
        prompt: str,
        timeout: float = 300.0,
        model: str | None = None,
    ) -> dict[str, Any]:
        """One read-only read of several connectors in one Claude Code run (the heartbeat
        reads every due connector at once, so Claude Code starts, and loads its tools, once).
        It may call exactly the `allowed` tools of each server, which Gnomon found to only
        read; every other tool of those servers is refused by name too; no built-in tools and
        nobody to ask. Connectors from Claude Code's settings files go into a file made for
        this read (deleted after it, as it may hold a token) and nothing else loads; the
        Claude account's connectors (`account`) load with the account instead, and the run
        waits for them. Returns {"text", "usage", "loaded": the servers that loaded, or None}."""
        who.require("workspace.admin")
        servers = {s: e for s, e in servers.items() if allowed.get(s)}
        if not servers:
            raise Conflict("No tool of these connectors only reads: they are not read.")
        spec_of = self._spec("claude")
        command = self._ready(spec_of)
        limits = [
            # The ingest model (Haiku unless the owner chose): unnamed, it is the account's
            # default, often the costliest.
            *(["--model", model] if model else []),
            "--system-prompt",
            READ_SYSTEM,
            "--max-turns",
            str(READ_TURNS),
            "--max-budget-usd",
            str(round(READ_BUDGET_USD * len(servers), 2)),  # one budget for each connector read
            "--allowedTools",
            *[f"mcp__{s}__{tool}" for s in servers for tool in allowed[s]],
        ]
        no = [f"mcp__{s}__{tool}" for s in servers for tool in refused.get(s) or []]
        if no:
            limits += ["--disallowedTools", *no]
        accounts = {bool(e.get("account")) for e in servers.values()}
        if accounts == {True}:
            return self._read_account(spec_of, command, list(servers), limits, prompt, timeout)
        if True in accounts:
            raise Conflict("The account's connectors and the settings' connectors read apart.")
        folder = tempfile.mkdtemp(prefix="workspace-beat-")
        try:
            return self._read_claude(spec_of, command, folder, servers, limits, prompt, timeout)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _read_account(
        self,
        spec: RunnerSpec,
        command: list[str],
        servers: list[str],
        limits: list[str],
        prompt: str,
        timeout: float,
    ) -> dict[str, Any]:
        """One read of connectors of the person's Claude account. Every other MCP server
        Claude Code would load is refused whole, so only these connectors' tools are in its
        prompt (all of an account's connectors at once outgrew the model's context). Tried
        again while one has not loaded yet (they load in the background); the last try reads
        with those that loaded, and never answers when none of them did."""
        others = sorted({_safe(n) for n in self._mcp_names(command)} - set(servers))
        extra = [
            *limits,
            *(["--disallowedTools", *[f"mcp__{s}" for s in others]] if others else []),
        ]
        for attempt in range(ACCOUNT_TRIES):
            if attempt:
                time.sleep(ACCOUNT_PAUSE)
            messages = self._account_start(
                spec,
                command,
                prompt,
                timeout,
                extra=extra,
                until_result=True,
                servers=servers,
                need_all=attempt < ACCOUNT_TRIES - 1,
            )
            result = messages[-1]
            if result.get("type") == "result":
                break
        else:
            raise Conflict(f"{spec.label} could not load these connectors from your account.")
        init = next((m for m in messages if m.get("subtype") == "init"), {})
        loaded = sorted(s for s in servers if _mcp_tools(init).get(s))
        _out_of_turns(spec, result)
        if result.get("is_error"):
            reason = str(result.get("result") or "it stopped")
            if AUTH_FAILED.search(reason):
                raise Conflict(self._login_failed(spec))
            raise Conflict(f"{spec.label} could not read: {reason[:200]}")
        self._expired.discard(spec.id)
        return {
            "text": str(result.get("result") or ""),
            "usage": usage_of(result),
            "loaded": loaded,
        }

    def _read_claude(
        self,
        spec: RunnerSpec,
        command: list[str],
        folder: str,
        servers: dict[str, dict[str, Any]],
        limits: list[str],
        prompt: str,
        timeout: float,
    ) -> dict[str, Any]:
        fenced = self._fence(spec, command)
        config = os.path.join(folder, "mcp.json")
        with open(config, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": servers}, handle)
        argv = [
            *command,
            "-p",
            "--output-format",
            "json",
            *fenced,
            "--tools",
            "",
            "--mcp-config",
            config,
            "--strict-mcp-config",
            *limits,
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
        ]
        env = dict(os.environ, MCP_TIMEOUT="60000", ENABLE_CLAUDEAI_MCP_SERVERS="false")
        try:
            proc = self.popen(
                argv,
                cwd=folder,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                **_quiet(),
            )
        except OSError as exc:
            raise Conflict(f"Could not start {spec.label}: {exc}") from exc
        try:
            out, err = proc.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill(proc)
            raise Conflict(f"{spec.label} took too long to read.") from exc
        try:
            found = json.loads(out or "{}")
        except ValueError as exc:
            raise Conflict(
                f"{spec.label} gave an answer that could not be read: {error_line(err, out)}"
            ) from exc
        if isinstance(found, dict):
            _out_of_turns(spec, found)
        if not isinstance(found, dict) or found.get("is_error"):
            reason = (
                str(found.get("result") or "it stopped") if isinstance(found, dict) else "stopped"
            )
            if AUTH_FAILED.search(reason):
                raise Conflict(self._login_failed(spec))
            raise Conflict(f"{spec.label} could not read: {reason[:200]}")
        self._expired.discard(spec.id)
        return {"text": str(found.get("result") or ""), "usage": usage_of(found), "loaded": None}

    def _read_codex(
        self,
        spec: RunnerSpec,
        command: list[str],
        folder: str,
        server: str,
        allowed: list[str],
        prompt: str,
        timeout: float,
    ) -> dict[str, Any]:
        """Codex reads with its own settings (where the server and its sign-in live), with
        every other MCP server turned off, this one's tools limited to `allowed`, and its
        sandbox read-only."""
        from .heartbeat.connectors import codex_servers

        last = os.path.join(folder, "answer.txt")
        others = [
            arg
            for name in codex_servers()
            if name != server
            for arg in ("-c", f"mcp_servers.{name}.enabled=false")
        ]
        argv = [
            *command,
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--json",
            "-c",
            f"mcp_servers.{server}.enabled_tools={json.dumps(allowed)}",
            *others,
            "--output-last-message",
            last,
            "-",
        ]
        try:
            proc = self.popen(
                argv,
                cwd=folder,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                **_quiet(),
            )
        except OSError as exc:
            raise Conflict(f"Could not start {spec.label}: {exc}") from exc
        try:
            out, err = proc.communicate(prompt, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill(proc)
            raise Conflict(f"{spec.label} took too long to read.") from exc
        if proc.returncode:
            said = f"{err}\n{out}"
            if AUTH_FAILED.search(said) or OTHER_AUTH.search(said):
                raise Conflict(self._login_failed(spec))
            raise Conflict(f"{spec.label} could not read: {error_line(err, out)}")
        try:
            with open(last, encoding="utf-8") as handle:
                answer = handle.read()
        except OSError as exc:
            raise Conflict(f"{spec.label} gave no answer.") from exc
        return {"text": answer, "usage": codex_usage(out or "")}

    def get(self, who: Principal, run_id: str) -> LocalRun:
        who.require("workspace.admin")
        run = self.runs.get(run_id) or self._load(run_id)
        if run is None:
            raise NotFound(f"No run {run_id} on this computer.")
        return run

    def recent(self, who: Principal, *, limit: int = KEEP_RUNS) -> list[LocalRun]:
        """Runs here now and lately, newest first: those in memory, then those kept on disk."""
        who.require("workspace.admin")
        found = dict(self.runs)
        for run_id in self._kept()[: max(0, limit)]:
            if run_id not in found:
                loaded = self._load(run_id, events=False)
                if loaded is not None:
                    found[run_id] = loaded
        return sorted(found.values(), key=lambda r: r.started_at, reverse=True)[:limit]

    def packet(self, who: Principal, run_id: str) -> dict[str, Any]:
        """The brief a run was given: its packet as it was when the run claimed its work."""
        run = self.get(who, run_id)
        try:
            found = self.ws.bus.packet(who, task_id=run.task_id)
        except (NotFound, Conflict):
            return {"text": "", "available": False}
        from .mcp import render

        try:  # what the run's model was handed: redacted when the preset says so
            hidden = bool(self.ws.rt.brain.policies().get("redact_cloud", True))
        except (OSError, ValueError, RuntimeError, KeyError):
            hidden = True
        return {"text": mask(render.packet(found, redacting=hidden)), "available": True}

    # ---------------------------------------------------------------- the streams on disk

    def _stream_path(self, run_id: str, ext: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", run_id)
        return os.path.join(self.streams, f"{safe}.{ext}")

    def _keep(self, run: LocalRun) -> None:
        """The run's record (without its events) beside its stream."""
        try:
            os.makedirs(self.streams, exist_ok=True)
            record = {k: v for k, v in asdict(run).items() if k != "events"}
            path = self._stream_path(run.id, "json")
            with open(path + ".tmp", "w", encoding="utf-8") as handle:
                json.dump(record, handle, default=str)
            os.replace(path + ".tmp", path)
        except OSError:
            log.warning("Could not keep the record of %s", run.id, exc_info=True)

    def _kept(self) -> list[str]:
        """Run ids kept on disk, newest first."""
        try:
            names = [n for n in os.listdir(self.streams) if n.endswith(".json")]
        except OSError:
            return []
        paths = [os.path.join(self.streams, n) for n in names]
        paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return [os.path.basename(p)[: -len(".json")] for p in paths]

    def _load(self, run_id: str, *, events: bool = True) -> LocalRun | None:
        try:
            with open(self._stream_path(run_id, "json"), encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, ValueError):
            return None
        names = {f.name for f in LocalRun.__dataclass_fields__.values()}
        run = LocalRun(**{k: v for k, v in record.items() if k in names and k != "events"})
        if run.status in ACTIVE and run.id not in self.runs:
            run.status, run.stopping = "failed", None  # the app stopped while it ran
        if events:
            try:
                with open(self._stream_path(run_id, "jsonl"), encoding="utf-8") as handle:
                    run.events = [json.loads(line) for line in handle if line.strip()]
            except (OSError, ValueError):
                run.events = []
        return run

    def _prune_streams(self) -> None:
        for run_id in self._kept()[KEEP_STREAMS:]:
            if run_id in self.runs:
                continue
            for ext in ("json", "jsonl"):
                try:
                    os.remove(self._stream_path(run_id, ext))
                except OSError:
                    pass

    def cancel(self, who: Principal, run_id: str) -> LocalRun:
        run = self.get(who, run_id)
        self._stop(run_id, "cancelled")
        return run

    def close(self) -> None:
        for run_id, run in list(self.runs.items()):
            if run.status in ACTIVE:
                self._stop(run_id, "cancelled")

    # ---------------------------------------------------------------- internals

    def _spec(self, runner_id: str) -> RunnerSpec:
        spec = RUNNERS.get(runner_id)
        if spec is None:
            raise NotFound(f"No runner {runner_id!r}; try one of {', '.join(RUNNERS)}.")
        return spec

    def _actor(self, spec: RunnerSpec) -> Actor | None:
        """The model this CLI's runs act as: the one most recently seen with its provider."""
        models = [
            a
            for a in self.ws.actors.list(self.ws.owner())
            if a.kind == "model" and a.provider == spec.provider and not a.disabled_at
        ]
        models.sort(key=lambda a: (a.last_seen_at or "", a.created_at), reverse=True)
        return models[0] if models else None

    def answer(
        self,
        who: Principal,
        runner_id: str,
        task_id: str,
        *,
        model: str | None = None,
        timeout: float = 900.0,
    ) -> LocalRun:
        """Run one task on a CLI that answers once with no tools (Codex, Gemini CLI). As that
        CLI's model, the run claims the task, sends its packet, saves the answer to Outputs and
        closes, as a CLI does through the app's tools. It runs in the background."""
        who.require("workspace.admin")
        spec = self._spec(runner_id)
        actor, task = self._assignee(who, spec, self.ws.tasks.get(who, task_id))
        if task.status != "ready":
            raise Conflict(
                f"The task is {task.status.replace('_', ' ')}: only a ready task can run."
            )
        run = LocalRun(
            id=new_id("lrun", self.ws.rt.clock.now()),
            runner=spec.id,
            task_id=task.id,
            task_title=task.title,
            actor_id=actor.id,
            started_by=who.actor_id,
            started_at=iso(self.ws.rt.clock.now()),
        )
        with self._lock:
            self.runs[run.id] = run
            self._trim()
        self._keep(run)
        self._add(run, "status", text=f"Asking {spec.label}: it answers once, with no tools.")
        threading.Thread(
            target=self._answer,
            args=(who, spec, run, model, timeout),
            daemon=True,
            name="answer-run",
        ).start()
        return run

    def _answer(
        self, who: Principal, spec: RunnerSpec, run: LocalRun, model: str | None, timeout: float
    ) -> None:
        from .mcp import render
        from .mcp.tools import redacting

        run.status = "running"
        connection = claimed = None
        try:
            # A model acts only through a credential: this run's own, revoked when it ends.
            task = self.ws.tasks.get(who, run.task_id)
            connection = self.ws.actors.issue_token(
                who,
                run.actor_id,
                label=f"{RUN_LABEL} ({run.id})",
                projects=[task.project_id] if task.project_id else None,
            )
            agent = self.ws.actors.authenticate(connection.token)
            claimed = self.ws.bus.claim(agent, run.task_id)
            brief = render.packet(claimed.packet, redacting=redacting(self.ws, agent))
            found = self.ask_measured(
                who,
                f"{brief}\n\n{ANSWER_ONLY}",
                timeout=timeout,
                job="work",
                runner=spec.id,
                model=model,
            )
            text = str(found.get("answer") or "").strip()
            if not text:
                raise Conflict(f"{spec.label} gave no answer.")
            saved = self.ws.skills.save_result(
                agent, run_id=claimed.run.id, title=run.task_title, text=text
            )
            summary = f"Saved \u201c{saved['title']}\u201d to Outputs."
            self.ws.bus.complete(agent, claimed.run.id, summary=summary)
            usage = {
                k: found.get(k)
                for k in ("model", "tokens_in", "tokens_out", "cost", "ms", "measured")
            }
            self._add(run, "result", text=summary, usage=usage)
            run.status, run.summary = "succeeded", summary
        except Exception as exc:  # the CLI, its sign-in, the save: the run fails and says why
            log.warning("answer run %s failed", run.id, exc_info=True)
            why = str(getattr(exc, "message", "") or exc) or f"{spec.label} stopped."
            if claimed is not None:
                try:
                    self.ws.bus.complete(agent, claimed.run.id, summary=why, outcome="failed")
                except WorkspaceError:  # the run may have ended already
                    log.warning("answer run %s could not be closed", run.id, exc_info=True)
            self._add(run, "status", text=why)
            run.status, run.summary = "failed", why
        finally:
            if connection is not None:
                self.ws.actors.revoke(who, connection.credential.id)
        run.finished_at = iso(self.ws.rt.clock.now())
        self._keep(run)

    def _assignee(self, who: Principal, spec: RunnerSpec, task: Task) -> tuple[Actor, Task]:
        """The model the run acts as. An unassigned task (a request waiting for a model) goes
        to this CLI's model, made on first use; another model's task stays theirs."""
        if task.assignee_id:
            actor = self.ws.actors.get(who, task.assignee_id)
            if actor.kind != "model" or actor.provider != spec.provider:
                raise Conflict(
                    f"This task is assigned to {actor.name}. Assign it to a {spec.label} model "
                    "to run it here."
                )
            return actor, task
        found = self._actor(spec)
        if found is None:
            # Runs bring their own short-lived credentials. The first one stays only so the
            # model counts as able to take work; its token is never shown, so no one can use it.
            found = self.ws.actors.connect_model(
                who,
                name=f"{spec.label} (this computer)",
                provider=spec.provider,
                label="Kept for runs from this computer; its token was never shown",
            ).actor
        actor = found
        task = self.ws.tasks.update(who, task.id, assignee_id=actor.id)
        if task.status == "draft":
            task = self.ws.tasks.mark_ready(who, task.id)
        return actor, task

    def _feed(self, proc: Any, prompt: str) -> None:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except (OSError, ValueError):
            pass

    def _read(self, run: LocalRun, stream: IO[str] | None, source: str) -> None:
        if stream is None:
            return
        try:
            for line in stream:
                line = line.rstrip("\n")
                if source == "stderr":
                    if line.strip():
                        self._add(run, "stderr", text=line[:1000])
                        if AUTH_FAILED.search(line):
                            self._add(run, "status", text=self._login_failed(RUNNERS[run.runner]))
                    continue
                try:
                    events = describe(line)
                except Exception:  # one odd line never ends the watch
                    log.warning("Could not read a line of %s's output", run.id, exc_info=True)
                    events = [{"kind": "log", "text": line[:400]}]
                for event in events:
                    tools = event.pop("tools", None)
                    self._add(run, **event)
                    if tools not in (None, "connected"):
                        # Claude Code goes on without a server that did not connect, and would
                        # report a run that could do nothing as finished: stop it here.
                        run.tools_failed = True
                        self._add(
                            run,
                            "error",
                            text=(
                                f"The app's tools did not connect ({tools}), so this run could "
                                f"do nothing. Check that the app answers at {self.base_url}/mcp "
                                "and run it again."
                            ),
                        )
                        proc = self._procs.get(run.id)
                        if proc is not None:
                            _kill(proc)
                    if event["kind"] == "result":
                        run.summary = str(event.get("text") or "")[:2000]
                        if event.get("usage"):
                            self.count_usage("run", event["usage"], run.id)
                        if not event.get("ok") and AUTH_FAILED.search(run.summary):
                            run.summary = self._login_failed(RUNNERS[run.runner])
                            self._add(run, "status", text=run.summary)
        except (OSError, ValueError):
            pass  # the pipe closed under us (a stopped run)
        finally:
            stream.close()

    def _watch(
        self,
        who: Principal,
        run: LocalRun,
        proc: Any,
        token: str,
        credential_id: str,
        folder: str,
        errors: threading.Thread | None = None,
        copies: dict[str, set[str]] | None = None,
    ) -> None:
        """Follow a run to its end. Whoever watches it sees it running until everything about
        its end is recorded (its last error lines, the task's blocker, the files it made, the
        final event), and only then its final status. Whatever breaks on the way, the run
        still ends: its process stopped, its credential revoked, its status final."""
        code: int | None = None
        ended = "failed"
        try:
            self._read(run, proc.stdout, "stdout")
            code = proc.wait()
            if errors is not None:
                errors.join(timeout=10)  # its last lines on stderr belong to this run's story
            if run.contract is not None:
                run.checks = anchoring.read_events(folder)
                self._add(run, "checks", checks=run.checks, text=anchoring.summary(run.checks))
            if run.folder:
                try:
                    self._collect(run, copies or {})
                except Exception as exc:  # what it made is listed or said; the run still ends
                    log.warning("Could not list what %s made", run.id, exc_info=True)
                    self._add(run, "error", text=f"Could not list what it made: {exc}")
            results = [e for e in run.events if e["kind"] == "result"]
            ended = run.stopping or (
                "succeeded"
                if code == 0 and results and results[-1].get("ok") and not run.tools_failed
                else "failed"
            )
            self._settle(run, token, ended)
        except Exception as exc:
            log.warning("Watching %s broke", run.id, exc_info=True)
            self._add(run, "error", text=f"Watching the run broke: {exc}")
            _kill(proc)
        finally:
            try:
                self._cleanup(who, run, credential_id, folder)
            finally:
                run.exit_code = code
                self._add(run, "done", ok=ended == "succeeded", text=_ending(ended, code))
                run.finished_at = iso(self.ws.rt.clock.now())
                run.status = ended  # last: a finished run is complete when anyone sees it finished
                self._procs.pop(run.id, None)
                self._keep(run)
        try:
            self._event(
                who,
                "runner.finished",
                run,
                {"status": ended, "exit_code": code, "checks": run.checks},
            )
        except Exception:
            log.warning("Could not record the end of %s", run.id, exc_info=True)

    def _settle(self, run: LocalRun, token: str, ended: str) -> None:
        """A run that stopped before finishing leaves a blocker on the task, saying why."""
        owner = self.ws.owner()
        task = self.ws.tasks.get(owner, run.task_id)
        if not task.current_run_id or task.status not in ("claimed", "in_progress"):
            return
        current = next(
            (r for r in self.ws.tasks.runs(owner, task.id) if r.id == task.current_run_id), None
        )
        if current is None or current.actor_id != run.actor_id:
            return
        principal = self.ws.actors.authenticate(token)
        why = {
            "cancelled": "a person stopped it",
            "timed_out": "it ran past its time limit",
        }.get(ended, run.summary or f"it exited with code {run.exit_code}")
        self.ws.bus.append(
            principal,
            current.id,
            type="blocker",
            message=f"{RUNNERS[run.runner].label} stopped before finishing: {why}.",
        )

    def _plan(self, who: Principal, name: str) -> list[tuple[str, str]]:
        """What a run that makes files works with: the skill's folder (copied to ./skill) and
        those of the skills it depends on (each copied to a folder named after it)."""
        skill = self.ws.skills.find(who, name)
        source = self.ws.rt.brain.skill_folder(skill.name)
        if source is None:
            raise Conflict(
                f"The files of the skill {skill.name} are not on this computer, so it cannot "
                "make files here."
            )
        plan = [("skill", source)]
        for dep in skill.depends_on:
            found = self.ws.rt.brain.skill_folder(dep)
            if found and dep not in {into for into, _ in plan}:
                plan.append((dep, found))
        return plan

    def _plan_many(self, who: Principal, names: list[str]) -> list[tuple[str, str]]:
        """A run of several skills that makes files: each skill's folder (copied to a folder
        named after it) and those of the skills they depend on."""
        plan: list[tuple[str, str]] = []
        for name in names:
            skill = self.ws.skills.find(who, name)
            source = self.ws.rt.brain.skill_folder(skill.name)
            if source is None:
                raise Conflict(
                    f"The files of the skill {skill.name} are not on this computer, so it "
                    "cannot make files here."
                )
            for into, found in [(skill.name, source)] + [
                (dep, self.ws.rt.brain.skill_folder(dep)) for dep in skill.depends_on
            ]:
                if found and into not in {i for i, _ in plan}:
                    plan.append((into, found))
        return plan

    def _prepare(
        self, name: str, plan: list[tuple[str, str]], task_id: str
    ) -> tuple[str, dict[str, set[str]]]:
        """A new folder of its own under the outputs folder, holding the copies."""
        # dated as the person reads the date, in the workspace's timezone
        stamp = (
            self.ws.rt.clock.now().astimezone(zone(self.ws.info().timezone)).strftime("%Y-%m-%d")
        )
        base = os.path.join(self.outputs, "skill-runs", f"{stamp}-{name}")
        workdir, number = base, 1
        while os.path.exists(workdir):
            number += 1
            workdir = f"{base}-{number}"
        os.makedirs(workdir)
        copies: dict[str, set[str]] = {}
        try:
            for into, source in plan:
                target = os.path.join(workdir, into)
                shutil.copytree(source, target, ignore=SKIPPED)
                copies[into] = {os.path.relpath(p, target) for p in _files(target)}
            with open(os.path.join(workdir, MARKER), "w", encoding="utf-8") as handle:
                json.dump(
                    {"task_id": task_id, "copies": {k: sorted(v) for k, v in copies.items()}},
                    handle,
                )
        except OSError:
            shutil.rmtree(workdir, ignore_errors=True)
            raise
        return workdir, copies

    def _collect(self, run: LocalRun, copies: dict[str, set[str]]) -> None:
        """Keep what a run made. A file it left inside a copy of a skill moves out beside the
        rest; the copies go; the task records what is left in the folder."""
        workdir = str(run.folder)
        made = _gather(workdir, copies)
        run.made = made
        if not made:
            shutil.rmtree(workdir, ignore_errors=True)
            run.folder = None
            self._add(run, "files", files=[], text="It made no files.")
            return
        self.ws.skills.record_files(self.ws.owner(), run.task_id, folder=workdir, files=made)
        names = ", ".join(str(f["name"]) for f in made[:8]) + (" and more" if len(made) > 8 else "")
        self._add(
            run,
            "files",
            files=made,
            folder=workdir,
            text=f"Made {len(made)} file{'s' if len(made) != 1 else ''}: {names}.",
        )

    def _cleanup(self, who: Principal, run: LocalRun, credential_id: str, folder: str) -> None:
        self.contracts.forget(credential_id)
        try:
            self.ws.actors.revoke(who, credential_id)
        finally:
            shutil.rmtree(folder, ignore_errors=True)

    def _stop(self, run_id: str, status: str) -> None:
        run = self.runs.get(run_id)
        proc = self._procs.get(run_id)
        if run is None or run.status not in ACTIVE or run.stopping:
            return
        run.stopping = status
        self._add(
            run,
            "status",
            text="Stopping: "
            + ("a person stopped it." if status == "cancelled" else "time is up."),
        )
        if proc is not None:
            _kill(proc)

    def count_usage(self, job: str, usage: dict[str, Any], ref: str = "") -> None:
        """Count a call's tokens and cost in the Brain's ledger (the jobs line of the cost
        report)."""
        figures = {k: v for k, v in usage.items() if k != "model"}
        self.ws.rt.brain.record_model_call(
            job, str(usage.get("model") or "claude"), ref=ref, **figures
        )

    def _add(self, run: LocalRun, kind: str, **fields: Any) -> None:
        """One step of the run's stream, its credentials masked, kept in memory and on disk."""
        with self._lock:
            seq = run.events[-1]["seq"] + 1 if run.events else 1
            event = {
                "seq": seq,
                "at": iso(self.ws.rt.clock.now()),
                "kind": kind,
                **_masked_fields(fields),
            }
            run.events.append(event)
            if len(run.events) > MAX_EVENTS:
                del run.events[: len(run.events) - MAX_EVENTS]
            try:
                os.makedirs(self.streams, exist_ok=True)
                with open(self._stream_path(run.id, "jsonl"), "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, default=str) + "\n")
            except OSError:
                log.warning("Could not keep a step of %s", run.id, exc_info=True)

    def _trim(self) -> None:
        finished = [r for r in self.runs.values() if r.status not in ACTIVE]
        for old in sorted(finished, key=lambda r: r.started_at)[
            : max(0, len(self.runs) - KEEP_RUNS)
        ]:
            self.runs.pop(old.id, None)

    def _event(self, who: Principal, kind: str, run: LocalRun, data: dict[str, Any]) -> None:
        task = self.ws.tasks.get(who, run.task_id)
        with self.ws.rt.write() as tx:
            tx.emit(
                kind,
                actor_id=who.actor_id,
                subject_type="task",
                subject_id=run.task_id,
                project_id=task.project_id,
                data={"local_run": run.id, "model": run.actor_id, **data},
            )


def _out_of_turns(spec: RunnerSpec, result: dict[str, Any]) -> None:
    """A read that reached its turn cap or its budget ends with no answer: a failure, never
    an empty read."""
    cap = {
        "error_max_turns": f"its {READ_TURNS}-turn cap",
        "error_max_budget_usd": f"its ${READ_BUDGET_USD:.2f} budget",
    }.get(str(result.get("subtype")))
    if cap:
        raise Conflict(
            f"{spec.label} reached {cap} before answering, so nothing was read. It is tried "
            "again on the next beat."
        )


def _account_env() -> dict[str, str]:
    """What a headless Claude Code needs to load the Claude account's connectors: it leaves
    them out unless asked, and starts without them unless told to wait until they connect."""
    env = dict(
        os.environ,
        MCP_TIMEOUT="60000",
        ENABLE_CLAUDEAI_MCP_SERVERS="true",
        MCP_CONNECTION_NONBLOCKING="false",
    )
    # One tool's answer (a whole Drive file, a long thread) is cut to this many tokens, so a
    # read cannot outgrow the model's context ("Prompt is too long").
    env.setdefault("MAX_MCP_OUTPUT_TOKENS", str(MCP_OUTPUT_TOKENS))
    return env


def _messages(
    proc: Any, prompt: str, timeout: float, stop: Callable[[list[dict[str, Any]]], bool]
) -> list[dict[str, Any]]:
    """The JSON lines a CLI writes (stream-json), until `stop` says so or `timeout` passes."""
    got: list[dict[str, Any]] = []

    def read() -> None:
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
            for line in proc.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if isinstance(message, dict):
                    got.append(message)
                    if stop(got):
                        return
        except (OSError, ValueError):
            pass

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    reader.join(timeout)
    return list(got)


def _mcp_tools(init: dict[str, Any]) -> dict[str, list[str]]:
    """{server, as tool names carry it: [its tools]} from Claude Code's init message."""
    tools: dict[str, list[str]] = {}
    for name in init.get("tools") or []:
        if isinstance(name, str) and name.startswith("mcp__") and name.count("__") >= 2:
            _, server, tool = name.split("__", 2)
            tools.setdefault(server, []).append(tool)
    return tools


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name) or "server"


def _kill(proc: Any) -> None:
    """Stop a CLI and everything it started."""
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
                **_quiet(),
            )
        else:  # its own process group (start_new_session): stop the whole tree
            os.killpg(proc.pid, signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


def _gather(workdir: str, copies: dict[str, set[str]]) -> list[dict[str, Any]]:
    """What a run left in its folder. A file it made inside a copy of a skill moves out beside
    the rest; the copies and the marker go."""
    for into, copied in copies.items():
        base = os.path.join(workdir, into)
        for path in _files(base):
            if os.path.relpath(path, base) not in copied:
                shutil.move(path, _free(os.path.join(workdir, os.path.basename(path))))
        shutil.rmtree(base, ignore_errors=True)
    try:
        os.remove(os.path.join(workdir, MARKER))
    except FileNotFoundError:
        pass
    return [
        {"name": os.path.relpath(path, workdir).replace(os.sep, "/"), "size": os.path.getsize(path)}
        for path in sorted(_files(workdir))
    ]


def _files(root: str) -> list[str]:
    """Every file under a folder, leaving out hidden ones and Python's caches."""
    found = []
    for here, folders, names in os.walk(root):
        folders[:] = [f for f in folders if not f.startswith(".") and f != "__pycache__"]
        found += [os.path.join(here, n) for n in names if not n.startswith(".")]
    return found


def _free(path: str) -> str:
    """The path, or the first "name (2).ext" beside it that is not taken."""
    stem, ext = os.path.splitext(path)
    number = 1
    while os.path.exists(path):
        number += 1
        path = f"{stem} ({number}){ext}"
    return path


def _ending(status: str, exit_code: int | None) -> str:
    return {
        "succeeded": "Finished.",
        "failed": f"Stopped with an error (exit code {exit_code}).",
        "cancelled": "Stopped by a person.",
        "timed_out": "Stopped: it ran past its time limit.",
    }.get(status, status)
