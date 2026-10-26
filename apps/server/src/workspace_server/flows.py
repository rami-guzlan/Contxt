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
from .library import FetchError
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
        self,
        ws: Workspace,
        runners: Runners,
        agent: AgentWork,
        interval: float = 15.0,
        library: Any = None,
    ) -> None:
        self.ws = ws
        self.runners = runners
        self.agent = agent
        self.library = library  # the Library (library.py): refresh an item, fetch a page
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> dict[str, Any]:
        """One pass: start what is due, record what finished steps used, move runs along,
        start one step here, run upkeep."""
        owner = self.ws.owner()
        started = self.ws.workflows.start_due(owner)
        self._meter(owner)
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
        for item in todo.get("ingest") or []:
            self._ingest(owner, item)
        ran = self._start_one(owner, todo["start"])
        if started:
            log.info("%d workflow run(s) started", len(started))
        return {"started": len(started), "ran": ran, "upkeep": len(todo["upkeep"])}

    def _ingest(self, owner: Any, item: dict[str, Any]) -> None:
        """An ingestion step (UX 4.7): refresh a Library item, fetch a page into the Library,
        or sweep the watched folders. What it brings in follows the capture policy."""
        run_id, index = item["run_id"], item["index"]
        try:
            if item["source"] == "folder":
                found = self.ws.rt.brain.sweep()
                summary = str(found.get("text") or "Swept the folders.")
            elif self.library is None:
                raise WorkspaceError("The Library is not running here.")
            elif item["source"] == "library":
                found = self.library.refresh(owner, item["target"], wait=True)
                summary = str(found.get("message") or found.get("status") or "Refreshed.")
            else:
                source = self.library.fetch(url=item["target"])
                filed = self.ws.brain.add_file(
                    owner,
                    filename=re.sub(r"[^a-z0-9]+", "-", source.title.lower()).strip("-")[:60]
                    + ".md",
                    data=source.markdown.encode("utf-8"),
                    title=source.title,
                    wait=True,
                    library={"library": "reference", "source_url": source.url},
                )
                summary = f"Fetched {source.title}: {filed.message}"
        except (WorkspaceError, FetchError, OSError, ValueError) as exc:  # the step fails
            self.ws.workflows.upkeep_finished(owner, run_id, index, ok=False, summary=str(exc))
            return
        self.ws.workflows.upkeep_finished(owner, run_id, index, ok=True, summary=summary)

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

    def _meter(self, owner: Any) -> None:
        """What each finished step's run used, from its CLI's report, onto the workflow run,
        so its budgets are checked before the next step starts."""
        steps = self.ws.workflows.unmetered(owner)
        if not steps:
            return
        reports: dict[str, dict[str, Any]] = {}
        for run in list(self.runners.runs.values()):
            if run.status in ACTIVE:
                continue
            result = next((e for e in reversed(run.events) if e.get("kind") == "result"), None)
            if result and result.get("usage"):
                reports[run.task_id] = result["usage"]
        for step in steps:
            usage = reports.get(step["task_id"])
            if usage is None:
                continue
            try:
                self.ws.workflows.step_used(owner, step["run_id"], step["index"], usage)
            except WorkspaceError:  # the run moved on: the next tick looks again
                continue

    def _start_one(self, owner: Any, waiting: list[dict[str, Any]]) -> int:
        """Start one step's task here on its CLI and model, unless a run is going already.
        Claude Code runs it with the app's tools; Codex and Gemini CLI answer it once."""
        if not waiting or any(run.status in ACTIVE for run in list(self.runners.runs.values())):
            return 0
        item = waiting[0]
        wanted = item.get("runner") or "claude"
        runner = next(
            (
                status
                for status in self.runners.statuses(owner)
                if status.id == wanted and status.installed and status.signed_in is not False
            ),
            None,
        )
        if runner is None:
            return 0  # the step waits in the queue, like any AI work without a model
        model = item.get("model")
        try:
            if RUNNERS[wanted].one_click:
                self.runners.start(owner, runner.id, item["task_id"], model=model)
            else:
                self.runners.answer(owner, runner.id, item["task_id"], model=model)
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
