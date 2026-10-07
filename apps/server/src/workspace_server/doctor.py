"""contxt check: is this Contxt ready, and if not, what to do about it.

Every line says what was checked and, when something is missing, the one command that fixes
it. A failure means Contxt cannot work as set up; a warning means it works with less (no web
app, matching by words). The connection test starts the Brain's MCP server exactly as an AI
app would and asks it for its tools.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from dataclasses import dataclass

from workspace_connectors.providers import brain_command

from . import webapp
from .settings import Settings

OK, WARN, FAIL = "ok", "warn", "fail"


@dataclass(frozen=True)
class Check:
    state: str
    what: str
    fix: str = ""


def _git() -> Check:
    if not shutil.which("git"):
        return Check(FAIL, "git is not installed", "install it from https://git-scm.com")
    done = subprocess.run(["git", "--version"], capture_output=True, text=True, check=False)
    return Check(OK, done.stdout.strip() or "git is installed")


def _brain(vault: str) -> list[Check]:
    from brainkit import gitops, health
    from brainkit.api import Brain

    if not os.path.isfile(os.path.join(vault, "brain.json")):
        return [Check(FAIL, f"no Brain at {vault}", "uv run contxt setup")]
    brain = Brain(vault, embeddings=None)
    try:
        report = brain.health().text or ""
        summary = health.status_line(brain)
        problems = _section(report, "Problems")
        warnings = _section(report, "Warnings")
        checks = []
        name = summary.split(":", 1)[0]
        if problems:
            checks.append(
                Check(
                    FAIL,
                    f"{name}: {problems[0]}",
                    f'uv run brain --vault "{vault}" check, for the full list',
                )
            )
        else:
            counts = (
                summary.split(":", 1)[1].split(", vault at")[0].strip() if ":" in summary else ""
            )
            checks.append(Check(OK, f"{name}: {counts}, no problems"))
        for warning in warnings[:3]:
            checks.append(Check(WARN, f"Brain: {warning}"))
        repo = os.path.dirname(os.path.abspath(vault))
        if gitops.owns_repo(repo):
            checks.append(Check(OK, "the Brain keeps its own history (git)"))
        else:
            checks.append(
                Check(
                    WARN,
                    "the Brain folder is not a git repository of its own, so its "
                    "changes have no history or undo",
                    f'git init "{repo}"',
                )
            )
        embedder = brain.embedder
        if embedder is not None and embedder.present():
            checks.append(Check(OK, f"matching by meaning ({embedder.model_name})"))
        else:
            checks.append(
                Check(
                    WARN,
                    "matching by words only: no local embedding model",
                    "uv run contxt models --download",
                )
            )
        return checks
    finally:
        brain.close()


def _section(report: str, title: str) -> list[str]:
    lines, inside = [], False
    for line in report.splitlines():
        if line.startswith("## "):
            inside = line.startswith(f"## {title}")
        elif inside and line.startswith("- ") and line != "- none":
            lines.append(line[2:])
    return lines


def _mcp(vault: str, timeout: float = 60) -> Check:
    """Start the Brain's MCP server as an AI app would, and ask it for its tools."""
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "contxt-check", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    stdin = "".join(json.dumps(m) + "\n" for m in messages)
    try:
        done = subprocess.run(
            brain_command(sys.executable, vault),
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return Check(FAIL, f"the Brain's MCP server did not start: {error}")
    for line in done.stdout.splitlines():
        try:
            reply = json.loads(line)
        except ValueError:
            continue
        if reply.get("id") == 2 and "result" in reply:
            tools = reply["result"].get("tools") or []
            return Check(
                OK,
                f"AI apps can connect: the Brain's MCP server answered with "
                f"{len(tools)} tools (uv run contxt connect)",
            )
    last = (done.stderr.strip().splitlines() or ["no answer"])[-1]
    return Check(FAIL, f"the Brain's MCP server did not answer: {last}")


def _web(settings: Settings) -> Check:
    where = webapp.location(settings.web_dist)
    if webapp.built(where):
        return Check(OK, f"web app built ({where})")
    return Check(
        WARN,
        "the web app is not built: the server answers, the pages do not",
        "uv run contxt web --download (or: npm install, then npm run build)",
    )


def _speech(settings: Settings) -> Check:
    from .speech import Speech

    speech = Speech(settings.speech_models)
    state = speech.status()
    if state.get("error"):
        return Check(WARN, f"speech to text: {state['error']}")
    if state.get("present"):
        return Check(OK, f"speech to text ready ({speech.model})")
    return Check(WARN, "talking is off: no local speech model", "uv run contxt models --download")


def _port(settings: Settings) -> Check:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        busy = probe.connect_ex(("127.0.0.1", settings.port)) == 0
    if not busy:
        return Check(OK, f"port {settings.port} is free for uv run contxt serve")
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{settings.port}/api/health", timeout=3
        ) as response:
            data = json.loads(response.read())
        if data.get("status") == "ok":
            return Check(
                OK,
                f"a Contxt server answers at http://127.0.0.1:{settings.port} (if it "
                "is another home's, give this one its own CONTXT_PORT in .env)",
            )
    except (OSError, ValueError):
        pass
    return Check(
        WARN,
        f"port {settings.port} is used by another program",
        "set CONTXT_PORT in .env to a free port",
    )


def run(settings: Settings) -> list[Check]:
    checks = [_git()]
    if settings.brain_vault:
        checks += _brain(settings.brain_vault)
        if checks[-1].state != FAIL:
            checks.append(_mcp(settings.brain_vault))
    else:
        checks.append(Check(FAIL, "there is no Brain here yet", "uv run contxt setup"))
    checks += [_web(settings), _speech(settings), _port(settings)]
    return checks


def render(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        line = f"  {check.state:<4}  {check.what}"
        if check.fix:
            line += f"\n        fix: {check.fix}"
        lines.append(line)
    failed = sum(c.state == FAIL for c in checks)
    warned = sum(c.state == WARN for c in checks)
    if failed:
        lines.append(
            f"Not ready: {failed} to fix" + (f", {warned} to consider." if warned else ".")
        )
    else:
        lines.append("Ready." + (f" {warned} to consider above." if warned else ""))
    return "\n".join(lines)
