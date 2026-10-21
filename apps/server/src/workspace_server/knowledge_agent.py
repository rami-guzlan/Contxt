"""The knowledge agent's model work, in the background.

An action, or one turn of the side panel's conversation, asks the model the owner chose
(models.py); the workspace's agent (workspace_core/services/agent.py) builds every prompt and
reads every answer. One model call runs at a time, so a row of clicks queues instead of
starting several CLIs at once. Jobs are kept in memory until the server stops; what an action
made (its record, its suggestions in Catch up and its questions) is kept by the workspace.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from workspace_core.clock import iso
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed, WorkspaceError
from workspace_core.ids import new_id
from workspace_core.services import agent_loop
from workspace_core.services.agent import ACTIONS, MAX_MESSAGE
from workspace_core.workspace import Workspace

from .models import ModelChoice, Models
from .runners import mask

log = logging.getLogger(__name__)

KEEP = 40  # jobs kept in memory


@dataclass
class AgentJob:
    id: str
    kind: str  # action | chat | agent-prompt | compose-improve (Work)
    model: str
    model_label: str
    started_at: str
    action: str | None = None
    message: str = ""
    status: str = "waiting"  # waiting | running | done | failed
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentWork:
    def __init__(self, ws: Workspace, models: Models) -> None:
        self.ws = ws
        self.models = models
        self.jobs: dict[str, AgentJob] = {}
        self._lock = threading.Lock()
        self._turn = threading.Lock()  # one model call at a time

    def _model(self, who: Principal, wanted: str | None) -> ModelChoice:
        """The model this work runs on (Release 1 plan, M08). With none chosen, the first
        one that can answer here is kept as the choice, so a later failure stops the work
        instead of moving it to another provider. A model that cannot answer is never
        replaced: the work stops and says so."""
        chosen = str(wanted or self.ws.agent.chosen_model() or "")
        if not chosen:
            chosen = self.models.default()
            self.ws.agent.configure(who, model=chosen)
        try:
            return self.models.choose(chosen)
        except Conflict as exc:
            raise Conflict(
                f"{exc} The knowledge agent does not switch to another provider on its own: "
                "fix this one, or choose another in its settings."
            ) from exc

    def _keep(self, job: AgentJob) -> None:
        with self._lock:
            self.jobs[job.id] = job
            for old in sorted(self.jobs.values(), key=lambda j: j.started_at)[:-KEEP]:
                self.jobs.pop(old.id, None)

    def start_action(self, who: Principal, action: str, *, model: str | None = None) -> AgentJob:
        """Run one upkeep action through the chosen model, in the background."""
        who.require("workspace.admin")
        if action not in ACTIONS:
            raise ValidationFailed(f"An action is one of {', '.join(ACTIONS)}.", field="action")
        choice = self._model(who, model)
        job = AgentJob(
            id=new_id("ajob", self.ws.rt.clock.now()),
            kind="action",
            action=action,
            model=choice.id,
            model_label=choice.label,
            started_at=iso(self.ws.rt.clock.now()),
        )
        self._keep(job)
        threading.Thread(
            target=self._run_action, args=(who, job, choice), daemon=True, name="agent-action"
        ).start()
        return job

    def start_enrich(
        self, who: Principal, *, model: str | None = None, limit: int | None = None
    ) -> AgentJob:
        """Write how each waiting entry is asked for (general-retrieval plan 3.1), one model
        call per entry, in the background."""
        who.require("workspace.admin")
        choice = self._model(who, model)
        job = AgentJob(
            id=new_id("ajob", self.ws.rt.clock.now()),
            kind="enrich",
            model=choice.id,
            model_label=choice.label,
            started_at=iso(self.ws.rt.clock.now()),
        )
        self._keep(job)
        threading.Thread(
            target=self._run_enrich,
            args=(who, job, choice, limit),
            daemon=True,
            name="agent-enrich",
        ).start()
        return job

    def _run_enrich(
        self, who: Principal, job: AgentJob, choice: ModelChoice, limit: int | None
    ) -> None:
        try:
            waiting = self.ws.rt.brain.enrichment_pending(limit)
            job.status = "running"
            done, failed, misses = 0, [], 0
            for item in waiting:
                try:
                    with self._turn:
                        answer = self.models.ask(
                            who, choice, item["prompt"], json_only=True, job="enrich"
                        )
                    found = self.ws.brain.enrich_note(
                        who, item["id"], answer, model=choice.id, expected_version=item["version"]
                    )
                except WorkspaceError as exc:
                    found = {"ok": False, "text": str(exc)}
                if found.get("ok"):
                    done, misses = done + 1, 0
                else:
                    failed.append({"id": item["id"], "why": found.get("text") or ""})
                    misses += 1
                    if misses >= 3:  # the model is not answering: stop, say so
                        break
            job.result = {
                "enriched": done,
                "failed": failed,
                "left": len(self.ws.rt.brain.enrichment_pending()),
            }
            job.status = "done" if done or not failed else "failed"
            if job.status == "failed":
                job.error = f"The model's answers could not be used: {failed[-1]['why']}"
        except WorkspaceError as exc:
            job.status, job.error = "failed", str(exc)
        except Exception as exc:  # a job never takes the server down
            log.warning("writing how entries are asked for failed", exc_info=True)
            job.status, job.error = "failed", f"It stopped: {exc}"
        finally:
            job.finished_at = iso(self.ws.rt.clock.now())

    def start_chat(
        self,
        who: Principal,
        message: str,
        history: list[dict[str, Any]] | None = None,
        *,
        model: str | None = None,
    ) -> AgentJob:
        """One turn of the conversation, in the background."""
        who.require("workspace.admin")
        text = str(message or "").strip()
        if not text:
            raise ValidationFailed("Say something to the agent.", field="message")
        if len(text) > MAX_MESSAGE:
            raise ValidationFailed(
                f"Keep a message under {MAX_MESSAGE:,} characters.", field="message"
            )
        choice = self._model(who, model)
        job = AgentJob(
            id=new_id("ajob", self.ws.rt.clock.now()),
            kind="chat",
            model=choice.id,
            model_label=choice.label,
            message=text,
            started_at=iso(self.ws.rt.clock.now()),
        )
        self._keep(job)
        threading.Thread(
            target=self._run_chat,
            args=(who, job, choice, list(history or [])),
            daemon=True,
            name="agent-chat",
        ).start()
        return job

    def start_work(
        self,
        who: Principal,
        kind: str,
        build: Any,
        read: Any,
        *,
        model: str | None = None,
        json_only: bool = True,
        message: str = "",
    ) -> AgentJob:
        """One model call for another part of Work (writing an agent's prompt, improving a
        prompt in Compose), in the background through the model the owner chose: `build()`
        makes the prompt, `read(answer)` turns the answer into the job's result."""
        choice = self._model(who, model)
        prompt = build()  # a refusal (a missing procedure, a bad form) is the caller's error
        job = AgentJob(
            id=new_id("ajob", self.ws.rt.clock.now()),
            kind=kind,
            model=choice.id,
            model_label=choice.label,
            message=message,
            started_at=iso(self.ws.rt.clock.now()),
        )
        self._keep(job)
        threading.Thread(
            target=self._run_work,
            args=(who, job, choice, prompt, read, json_only),
            daemon=True,
            name=f"work-{kind}",
        ).start()
        return job

    def _run_work(
        self,
        who: Principal,
        job: AgentJob,
        choice: ModelChoice,
        prompt: str,
        read: Any,
        json_only: bool,
    ) -> None:
        try:
            with self._turn:
                job.status = "running"
                answer = self.models.ask(who, choice, prompt, json_only=json_only)
            job.result = read(answer)
            job.status = "done"
        except WorkspaceError as exc:
            job.status, job.error = "failed", str(exc)
        except Exception as exc:  # a job never takes the server down
            log.warning("a Work job failed", exc_info=True)
            job.status, job.error = "failed", f"It stopped: {exc}"
        finally:
            job.finished_at = iso(self.ws.rt.clock.now())

    def get(self, who: Principal, job_id: str) -> AgentJob:
        who.require("brain.read")
        with self._lock:
            job = self.jobs.get(job_id)
        if job is None:
            raise NotFound("That run of the agent is not here (the app restarted?).", id=job_id)
        return job

    def recent(self, who: Principal) -> list[AgentJob]:
        who.require("brain.read")
        with self._lock:
            return sorted(self.jobs.values(), key=lambda j: j.started_at, reverse=True)

    # ---------------------------------------------------------------- in the background

    def _run_action(self, who: Principal, job: AgentJob, choice: ModelChoice) -> None:
        assert job.action is not None
        try:
            prompt, gathered = self.ws.agent.action_prompt(who, job.action, brief=choice.brief)
            answer, seconds = "", None
            run = None
            if prompt:
                with self._turn:
                    job.status = "running"
                    began = time.monotonic()
                    # The code-run loop (BL 17.3): one bounded question a step, code checks
                    # each answer and runs the tool it names; findings end the job.
                    run = agent_loop.run(
                        prompt,
                        lambda text: self.models.ask(who, choice, text, json_only=True),
                        self.ws.rt.brain.agent_tool,
                        action=job.action,
                        mask=mask,
                    )
                    seconds = time.monotonic() - began
                answer = json.dumps(run.findings) if run.findings is not None else ""
            job.result = self.ws.agent.apply_action(
                who, job.action, gathered, answer, model=choice.id, seconds=seconds
            )
            if run is not None:
                record = dict(run.record(), model=choice.id, seconds=seconds)
                self.ws.rt.brain.record_agent_run(job.id, job.action, run.ending, record)
                job.result["steps"] = len(run.steps)
                job.result["ending"] = run.ending
                if run.ending == "hand-up":
                    job.result.setdefault("notes", []).append(
                        f"The agent handed this job up: {run.why}. Run it with a larger model "
                        "or Claude Code, or look at the candidates yourself."
                    )
            job.status = "done"
        except WorkspaceError as exc:
            job.status, job.error = "failed", str(exc)
        except Exception as exc:  # a job never takes the server down
            log.warning("the knowledge agent's action failed", exc_info=True)
            job.status, job.error = "failed", f"It stopped: {exc}"
        finally:
            job.finished_at = iso(self.ws.rt.clock.now())

    def _run_chat(
        self, who: Principal, job: AgentJob, choice: ModelChoice, history: list[dict[str, Any]]
    ) -> None:
        try:
            prompt = self.ws.agent.chat_prompt(who, job.message, history, brief=choice.brief)
            with self._turn:
                job.status = "running"
                answer = self.models.ask(who, choice, prompt)
            job.result = self.ws.agent.read_chat(answer)
            job.status = "done"
        except WorkspaceError as exc:
            job.status, job.error = "failed", str(exc)
        except Exception as exc:  # a job never takes the server down
            log.warning("the knowledge agent's answer failed", exc_info=True)
            job.status, job.error = "failed", f"It stopped: {exc}"
        finally:
            job.finished_at = iso(self.ws.rt.clock.now())
