"""The background worker: the server's clock.

Each tick expires runs whose lease ran out (their tasks go back in the queue), wakes recurring
tasks whose next occurrence has arrived, hands AI work that waited for a model to the one
that can now take it, applies the Brain's scheduled revisions whose time has come, and, when
the owner chose a model for the knowledge agent, has it write how newly approved entries are
asked for (a few at a time; general-retrieval plan 3.1). The
bus also expires and wakes lazily when a model asks for work, so a missed tick never loses
anything.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from workspace_core.workspace import Workspace

log = logging.getLogger("workspace.worker")
GOAL_CHECK_SECONDS = 600  # how often the worker looks for goal checks that are due
ENRICH_SECONDS = 300  # how often it looks for entries waiting to be enriched
ENRICH_BATCH = 10  # entries enriched per look, so a backfill never floods the model
LEARN_SECONDS = 3600  # how often it teaches searched-for entries how they were asked for


@dataclass
class Tick:
    expired: int
    woke: int
    assigned: int = 0


class Worker:
    _enrich_job: Any

    def _enrich(self, system: Any) -> None:
        """Have the chosen model write how waiting entries are asked for: only when the owner
        chose a model (each entry is one call on it), one batch at a time."""
        running = self._enrich_job is not None and self._enrich_job.status in (
            "waiting",
            "running",
        )
        if self.agent is None or running or not self.ws.agent.chosen_model():
            return
        try:
            if not self.ws.rt.brain.enrichment_pending(1):
                return
            self._enrich_job = self.agent.start_enrich(system, limit=ENRICH_BATCH)
        except Exception:  # no model answering now: the next look tries again
            log.warning("entries could not be enriched", exc_info=True)

    def __init__(self, ws: Workspace, interval: float = 15.0, agent: Any = None) -> None:
        self.ws = ws
        self.agent = agent  # the knowledge agent's work (AgentWork), for enrichment
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._goals_at = 0.0  # when goal checks last looked for what is due
        self._enrich_at = 0.0  # when it last looked for entries to enrich
        self._learn_at = 0.0  # when it last learned from what conversations searched for
        self._enrich_job = None

    def tick(self) -> Tick:
        expired = self.ws.bus.expire_leases()
        woke = self.ws.bus.schedule_due()
        system = self.ws.system()
        assigned = self.ws.distill.assign_waiting(system)
        try:
            scheduled = self.ws.rt.brain.apply_scheduled()
        except Exception:  # a Brain that cannot write now: the next tick tries again
            log.warning("scheduled revisions could not be applied", exc_info=True)
            scheduled = {"applied": []}
        if scheduled.get("applied"):
            log.info("%d scheduled revision(s) went in", len(scheduled["applied"]))
        if time.monotonic() - self._goals_at >= GOAL_CHECK_SECONDS:
            # Goal checks are code only; each runs on its own cadence, so this finds few.
            self._goals_at = time.monotonic()
            try:
                checked = self.ws.goals.run_checks(system)
            except Exception:  # a check that cannot run now: the next look tries again
                log.warning("goal checks could not run", exc_info=True)
                checked = []
            if checked:
                log.info("%d goal check(s) ran", len(checked))
        if time.monotonic() - self._learn_at >= LEARN_SECONDS:
            self._learn_at = time.monotonic()
            try:  # code only: no model is asked
                learned = self.ws.rt.brain.learn_from_use()
            except Exception:  # a Brain that cannot write now: the next look tries again
                log.warning("could not learn from use", exc_info=True)
                learned = {}
            if learned.get("learned") or learned.get("suggested"):
                log.info(
                    "learned how %d entr(ies) are asked for; %d wait for the owner",
                    len(learned.get("learned") or []),
                    len(learned.get("suggested") or []),
                )
        if time.monotonic() - self._enrich_at >= ENRICH_SECONDS:
            self._enrich_at = time.monotonic()
            self._enrich(system)
        if expired or woke or assigned:
            log.info(
                "expired %d lease(s), %d task(s) came due, %d waiting request(s) assigned",
                len(expired),
                len(woke),
                len(assigned),
            )
        return Tick(expired=len(expired), woke=len(woke), assigned=len(assigned))

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("worker tick failed")
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self.run, name="workspace-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 5)
