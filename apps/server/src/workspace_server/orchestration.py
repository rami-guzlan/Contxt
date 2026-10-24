"""Agent orchestrators on this computer (AGENTS.md 8b): the records and rules are the core's
(workspace_core/services/orchestrators.py); here each run's CLI is started.

A run's orchestrator starts on its CLI as "Run now" starts any task (runners.py): with the
app's MCP server only, so it can call orchestrators_context, orchestrators_spawn,
orchestrators_sheet_fill and orchestrators_finish. Each agent it spawns starts on its own CLI
and model the same way, with orchestrators_agent_context, outputs_save and orchestrators_report,
plus the connected tools of the person's own CLI the agent may read with. Gnomon holds no
third-party logins.

Who calls a tool is told by the run's own credential: each run gets one, made for that run
alone, so an agent cannot act as its orchestrator, nor one agent as another.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict
from workspace_core.services.orchestrators import CLIS, WORKS_BY, model_label

from .runners import RUNNERS, Runners
from .work_with_ai import WorkWithAI

MAX_WAIT = 50  # seconds orchestrators_context may wait for something new

# Starts one task on a CLI: (owner, runner, task_id, model) -> state, note, command, run_id
Launch = Callable[[Principal, str, str, str], dict[str, Any]]
# The task of the run a credential was made for, if any
Bind = Callable[[Principal], "str | None"]


class Orchestration:
    def __init__(self, ws: Any, runners: Runners) -> None:
        self.ws = ws
        self.runners = runners
        self.work = WorkWithAI(ws, runners)
        self.launch: Launch = self._launch
        self.bind: Bind = runners.contracts.task_of
        self.sleep: Callable[[float], None] = time.sleep

    @property
    def core(self) -> Any:
        return self.ws.orchestrators

    # ---------------------------------------------------------------- the page

    def project_id(self, who: Principal, project: str, *, make: bool = False) -> str | None:
        found = self.work.project(who, project, make=make)
        return found.id if found is not None else None

    def overview(self, who: Principal, project: str) -> dict[str, Any]:
        """The project's orchestrators with their latest runs, the agent tasks, and what an
        orchestrator can run on."""
        pid = self.project_id(who, project)
        return {
            "orchestrators": self.core.list(who, pid) if pid else [],
            "agent_tasks": self.core.agent_tasks(who, pid) if pid else [],
            "clis": [
                {
                    "id": cid,
                    "label": c["label"],
                    "models": [{"id": m, "label": label} for m, label in c["models"]],
                    "one_click": RUNNERS[cid].one_click,
                }
                for cid, c in CLIS.items()
            ],
            "works_by": [{"id": k, "label": v[0], "line": v[1]} for k, v in WORKS_BY.items()],
        }

    def save(
        self,
        who: Principal,
        project: str,
        spec: dict[str, Any],
        *,
        orchestrator_id: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        pid = self.project_id(who, project, make=True)
        return self.core.save(
            who,
            pid,
            spec,
            orchestrator_id=orchestrator_id,
            expected_version=expected_version,
        )

    def run(
        self,
        who: Principal,
        project: str,
        orchestrator: str,
        *,
        steer: str = "",
        trigger: str = "gnomon",
        asked_by: str = "",
    ) -> dict[str, Any]:
        """Start a run: the orchestrator's CLI starts on this computer now."""
        pid = self.project_id(who, project)
        if pid is None:
            raise Conflict("This project has no orchestrators yet.")
        found = self.core.find(who, pid, orchestrator)
        started = self.core.start(who, found["id"], steer=steer, trigger=trigger, asked_by=asked_by)
        run = started["run"]
        went = self.launch(self.ws.owner(), found["cli"], started["task_id"], found["model"])
        if went["state"] != "working":
            label = CLIS[found["cli"]]["label"]
            run = self.core.stop(
                self.ws.owner(), run["id"], f"{label} did not start: {went.get('note') or ''}"
            )
        return run

    def decide(
        self, who: Principal, run_id: str, gate_id: str, *, approve: bool, quote: str = ""
    ) -> dict[str, Any]:
        """The owner's yes or no to a gate. A yes to an agent's action starts the run that
        does it, with the tools it named."""
        owner = self.ws.owner()
        done = self.core.decide(who, owner, run_id, gate_id, approve=approve, quote=quote)
        act = done.get("act")
        if act:
            self._start_agent(owner, run_id, act["agent"], act["task_id"])
            done["run"] = self.core.run_of(who, run_id)
        return done

    # ---------------------------------------------------------------- the run's tools

    def context(self, who: Principal, run_id: str, *, wait: bool = False) -> dict[str, Any]:
        """The orchestrator's view; with `wait`, it returns once something new came back
        (a report, a gate, an agent that stopped), or after MAX_WAIT seconds."""
        caller = self.bind(who)
        found = self.core.context(who, run_id, caller)
        if not wait:
            return dict(found)
        seen = self._mark(found)
        waited = 0
        while waited < MAX_WAIT and found["status"] in ("running", "waiting"):
            if all(a["state"] in ("reported", "stopped") for a in found["agents"]):
                break
            self.sleep(1)
            waited += 1
            found = self.core.context(who, run_id, caller)
            if self._mark(found) != seen:
                break
        return dict(found)

    @staticmethod
    def _mark(found: dict[str, Any]) -> tuple[Any, ...]:
        return (
            len(found["reports"]),
            len(found["gates"]),
            tuple(a["state"] for a in found["agents"]),
        )

    def spawn(self, who: Principal, run_id: str, agent_id: str, brief: str = "") -> dict[str, Any]:
        owner = self.ws.owner()
        made = self.core.spawn(who, owner, run_id, agent_id, self.bind(who), brief=brief)
        run = self._start_agent(owner, run_id, made["agent"], made["task_id"])
        state = run["agents"].get(agent_id) or {}
        return {"task_id": made["task_id"], "state": state.get("state"), "run": run}

    def agent_context(self, who: Principal, run_id: str, agent_id: str) -> dict[str, Any]:
        return dict(self.core.agent_context(who, run_id, agent_id, self.bind(who)))

    def report(self, who: Principal, run_id: str, agent_id: str, **fields: Any) -> dict[str, Any]:
        return dict(self.core.report(who, run_id, agent_id, self.bind(who), **fields))

    def fill(self, who: Principal, run_id: str, rows: list[Any]) -> dict[str, Any]:
        return dict(self.core.fill(who, run_id, self.bind(who), rows))

    def finish(self, who: Principal, run_id: str, **fields: Any) -> dict[str, Any]:
        return dict(self.core.finish(who, run_id, self.bind(who), **fields))

    # ---------------------------------------------------------------- starting CLIs

    def _start_agent(
        self, owner: Principal, run_id: str, agent: dict[str, Any], task_id: str
    ) -> dict[str, Any]:
        went = self.launch(owner, agent["cli"], task_id, agent["model"])
        how = WORKS_BY[agent["works_by"]][0]
        command = (
            f"{CLIS[agent['cli']]['label']} · {model_label(agent['cli'], agent['model'])} · {how}"
        )
        return dict(
            self.core.spawned(
                owner,
                run_id,
                agent["id"],
                state=went["state"],
                note=str(went.get("note") or ""),
                command=command,
            )
        )

    def _launch(self, owner: Principal, cli: str, task_id: str, model: str) -> dict[str, Any]:
        """Start one task on this computer's CLI. A CLI that cannot start from here waits
        for the owner, with what to do."""
        try:
            run = self.runners.start(owner, cli, task_id, model=model if cli == "claude" else None)
        except Conflict as exc:
            return {"state": "waiting", "note": exc.message}
        if run.status == "failed":
            last = next((e for e in reversed(run.events) if e.get("kind") == "error"), None)
            return {"state": "stopped", "note": (last or {}).get("text") or "It did not start."}
        return {"state": "working", "run_id": run.id}
