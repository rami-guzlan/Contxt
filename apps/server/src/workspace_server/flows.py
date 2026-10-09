"""Workflows in the background: the server's side of services/workflows.py.

Each tick starts the workflows whose time has come (a run missed while the app was off starts
once), moves every run along, starts the next step's task with Claude Code on this computer
(one run at a time, as summaries do), runs upkeep steps through the knowledge agent, and reports
what those jobs came to. A step that waits for any connected AI stays in the queue for it.

Also here: the connectors Claude Code on this computer knows (`claude mcp list`), so a
connector step can name its tools. Contxt never reads their credentials.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from workspace_core.errors import WorkspaceError
from workspace_core.workspace import Workspace

from .knowledge_agent import AgentWork
from .runners import ACTIVE, RUNNERS, Runners, _call

log = logging.getLogger("workspace.flows")

# "hubspot: https://mcp.hubspot.com/mcp (HTTP) - ✓ Connected"
SERVER_LINE = re.compile(r"^(?P<name>[^\s:][^:]*):\s+(?P<detail>.*?)\s+-\s+(?P<state>.+)$")


def connectors(runners: Runners) -> dict[str, Any]:
    """The MCP servers Claude Code here connects to, by name, and whether each answered.
    Their tools are named mcp__<server>__<tool>."""
    spec = RUNNERS["claude"]
    command = runners.resolve(spec)
    if not command:
        return {"available": False, "servers": [], "note": f"{spec.label} is not installed here."}
    done = _call([*command, "mcp", "list"], timeout=90)
    if done is None or done.returncode != 0:
        return {
            "available": False,
            "servers": [],
            "note": f"{spec.label} did not list its connectors (`claude mcp list`).",
        }
    servers = []
    for line in done.stdout.splitlines():
        found = SERVER_LINE.match(line.strip())
        if not found or found["name"].lower().startswith("checking"):
            continue
        state = found["state"].strip()
        servers.append(
            {
                "name": found["name"].strip(),
                "detail": found["detail"].strip(),
                "connected": "✓" in state
                or ("connected" in state.lower() and "fail" not in state.lower()),
                "state": state,
            }
        )
    return {
        "available": True,
        "servers": servers,
        "note": "Name each tool in full: mcp__<server>__<tool>, like "
        "mcp__hubspot__search_crm_objects.",
    }


class WorkflowWorker:
    def __init__(
        self, ws: Workspace, runners: Runners, agent: AgentWork, interval: float = 15.0
    ) -> None:
        self.ws = ws
        self.runners = runners
        self.agent = agent
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> dict[str, Any]:
        """One pass: start what is due, move runs along, start one step here, run upkeep."""
        owner = self.ws.owner()
        started = self.ws.workflows.start_due(owner)
        todo = self.ws.workflows.advance(owner)
        for item in todo["watch"]:
            self._look_in(owner, item)
        for item in todo["upkeep"]:
            try:
                job = self.agent.start_action(owner, item["action"])
                self.ws.workflows.upkeep_started(owner, item["run_id"], item["index"], job.id)
            except WorkspaceError as exc:
                self.ws.workflows.upkeep_finished(
                    owner, item["run_id"], item["index"], ok=False, summary=str(exc)
                )
        ran = self._start_one(owner, todo["start"])
        if started:
            log.info("%d workflow run(s) started", len(started))
        return {"started": len(started), "ran": ran, "upkeep": len(todo["upkeep"])}

    def _look_in(self, owner: Any, item: dict[str, Any]) -> None:
        job = self.agent.jobs.get(str(item.get("job_id") or ""))
        if job is None:
            self.ws.workflows.upkeep_finished(
                owner,
                item["run_id"],
                item["index"],
                ok=False,
                summary="The app restarted while it ran: run the workflow again.",
            )
        elif job.status == "done":
            summary = str(job.result.get("summary") or "Done.")
            self.ws.workflows.upkeep_finished(
                owner, item["run_id"], item["index"], ok=True, summary=summary
            )
        elif job.status == "failed":
            self.ws.workflows.upkeep_finished(
                owner, item["run_id"], item["index"], ok=False, summary=job.error or "It stopped."
            )

    def _start_one(self, owner: Any, waiting: list[dict[str, Any]]) -> int:
        """Start one step's task with Claude Code here, unless a run is going already."""
        if not waiting or any(run.status in ACTIVE for run in list(self.runners.runs.values())):
            return 0
        runner = next(
            (
                status
                for status in self.runners.statuses(owner)
                if status.id == "claude" and status.installed and status.signed_in is not False
            ),
            None,
        )
        if runner is None:
            return 0  # the step waits in the queue, like any AI work without a model
        item = waiting[0]
        try:
            self.runners.start(owner, runner.id, item["task_id"])
        except WorkspaceError as exc:
            log.warning("could not start step %s of %s: %s", item["index"], item["run_id"], exc)
            return 0
        return 1

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="workflows", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("workflow worker tick failed")
            self._stop.wait(self.interval)
