"""Run a task now with an AI command-line tool on this machine.

Models normally pull their work on a schedule (the worker prompt). A person can also start one
task at once from the workspace: it launches the CLI as the task's model, streams what the CLI
does into the page, and keeps everything a run touches on a short leash:

- the CLI starts in an empty temporary folder, in restricted mode (`--restricted`: none of the
  person's own settings files, so none of their hooks), and loads only this workspace's MCP
  server (`--strict-mcp-config`)
- it may use the workspace's tools and nothing else: no built-in tools at all (`--tools ""`,
  so no shell, file access or web), and nothing needs asking (`--permission-mode dontAsk`)
- it connects with a credential made for this run alone, scoped to the task's project and
  revoked the moment the run ends (the MCP configuration holding it is deleted too)
- a run that stops before finishing leaves a blocker on the task saying why, instead of a
  claim that only expires when its lease runs out

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
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import IO, Any

from workspace_connectors.providers import SERVER_NAME
from workspace_core.clock import iso
from workspace_core.domain.policy import Principal
from workspace_core.domain.records import Actor, Task
from workspace_core.domain.schedule import zone
from workspace_core.errors import Conflict, NotFound
from workspace_core.ids import new_id
from workspace_core.workspace import Workspace

from .templates import TemplateLibrary

log = logging.getLogger(__name__)

ACTIVE = ("starting", "running")
RUN_LABEL = "Run from the workspace"  # the label of a run's own credential
LEFTOVER_MARGIN = 300  # seconds past a run's time limit after which its credential is a leftover
MAX_EVENTS = 2000
KEEP_RUNS = 30
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
SKIPPED = shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".DS_Store")
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
    )
}


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
    started_at: str = ""
    finished_at: str | None = None
    exit_code: int | None = None
    summary: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    folder: str | None = None  # where a run that makes files worked, and what it left there
    made: list[dict[str, Any]] = field(default_factory=list)

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
            {"kind": "status", "text": f"Started {model}; workspace tools {state or 'missing'}."}
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
        return [{"kind": "result", "ok": ok, "text": text.strip()}]
    return []


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
        self._procs: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._status: dict[str, tuple[float, RunnerStatus]] = {}

    # ---------------------------------------------------------------- the CLIs

    def statuses(self, who: Principal, *, refresh: bool = False) -> list[RunnerStatus]:
        who.require("workspace.admin")
        return [self.status(spec, refresh=refresh) for spec in RUNNERS.values()]

    def status(self, spec: RunnerSpec, *, refresh: bool = False) -> RunnerStatus:
        cached = self._status.get(spec.id)
        if cached and not refresh and time.monotonic() - cached[0] < 15:
            found = cached[1]
        else:
            found = detect(spec, self.resolve)
            self._status[spec.id] = (time.monotonic(), found)
        actor = self._actor(spec)
        return RunnerStatus(**{**asdict(found), "actor_id": actor.id if actor else None})

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

    def start(self, who: Principal, runner_id: str, task_id: str) -> LocalRun:
        """Run one task now with this machine's CLI, acting as the task's model."""
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
        with self._lock:
            if any(r.task_id == task_id and r.status in ACTIVE for r in self.runs.values()):
                raise Conflict("This task is already running here.")
        task = self.ws.tasks.get(who, task_id)
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
            copying = self._plan(who, str(about.get("name") or ""))
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
            "--restricted",
            "--tools",
            ",".join(FILE_TOOLS) if copying else "",
            "--mcp-config",
            config,
            "--strict-mcp-config",
            "--permission-mode",
            "dontAsk",
            "--allowedTools",
            f"mcp__{SERVER_NAME}",
            *(FILE_ALLOWED if copying else ()),
            "--no-session-persistence",
        ]
        with self._lock:
            self.runs[run.id] = run
            self._trim()
        self._add(run, "status", text=f"Starting {spec.label} as {actor.name}.")
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
        prompt = self.templates.run_prompt(self.ws.info().name, task.id)
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

    def ask(self, who: Principal, prompt: str, *, timeout: float = 180.0) -> str:
        """One answer from Claude Code on this computer, with no tools and no MCP server at
        all, so it knows only what the prompt says: one side of a comparison with and without
        the Brain, or a follow-up question in the goals interview. In an empty temporary
        folder, restricted, with no saved session."""
        who.require("workspace.admin")
        spec = RUNNERS["claude"]
        status = self.status(spec)
        command = self.resolve(spec)
        if not status.installed or not command:
            raise Conflict(f"{spec.label} is not installed on this computer: {spec.install}")
        if status.signed_in is False:
            raise Conflict(f"{spec.label} is not signed in. Sign in first: {status.sign_in}")
        folder = tempfile.mkdtemp(prefix="workspace-ask-")
        config = os.path.join(folder, "mcp.json")
        with open(config, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": {}}, handle)
        argv = [
            *command,
            "-p",
            "--output-format",
            "json",
            "--restricted",
            "--tools",
            "",
            "--mcp-config",
            config,
            "--strict-mcp-config",
            "--permission-mode",
            "dontAsk",
            "--no-session-persistence",
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
            raise Conflict(f"{spec.label} could not answer: {reason[:200]}")
        return str(found.get("result") or "").strip()

    def get(self, who: Principal, run_id: str) -> LocalRun:
        who.require("workspace.admin")
        run = self.runs.get(run_id)
        if run is None:
            raise NotFound(f"No run {run_id} on this computer.")
        return run

    def recent(self, who: Principal) -> list[LocalRun]:
        who.require("workspace.admin")
        return sorted(self.runs.values(), key=lambda r: r.started_at, reverse=True)

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
                    continue
                try:
                    events = describe(line)
                except Exception:  # one odd line never ends the watch
                    log.warning("Could not read a line of %s's output", run.id, exc_info=True)
                    events = [{"kind": "log", "text": line[:400]}]
                for event in events:
                    self._add(run, **event)
                    if event["kind"] == "result":
                        run.summary = str(event.get("text") or "")[:2000]
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
            if run.folder:
                try:
                    self._collect(run, copies or {})
                except Exception as exc:  # what it made is listed or said; the run still ends
                    log.warning("Could not list what %s made", run.id, exc_info=True)
                    self._add(run, "error", text=f"Could not list what it made: {exc}")
            results = [e for e in run.events if e["kind"] == "result"]
            ended = run.stopping or (
                "succeeded" if code == 0 and results and results[-1].get("ok") else "failed"
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
        try:
            self._event(who, "runner.finished", run, {"status": ended, "exit_code": code})
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

    def _add(self, run: LocalRun, kind: str, **fields: Any) -> None:
        with self._lock:
            seq = run.events[-1]["seq"] + 1 if run.events else 1
            run.events.append(
                {"seq": seq, "at": iso(self.ws.rt.clock.now()), "kind": kind, **fields}
            )
            if len(run.events) > MAX_EVENTS:
                del run.events[: len(run.events) - MAX_EVENTS]

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
