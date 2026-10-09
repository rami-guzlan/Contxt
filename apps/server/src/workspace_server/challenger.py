"""The external challenger: once a week, while the owner has it on, one run of Claude Code
argues against the beliefs that matter most (dissent.targets: the most used, the longest since
checked, the baselines).

It never runs until the owner turns it on (`challenger` in the Brain's policy). Its runs use a
profile of their own: the workspace's tools plus reading the web (WebSearch, WebFetch), no
files and no shell (runners.CHALLENGER_TOOLS), under a run contract like any other. Its task is
blind: each belief comes only as a claim under test, and the task's packet carries no Brain
context that would hand the claims over as true (services/packets.py). What it finds comes back
as challenges (`propose_challenge`), which wait for the owner.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta

from workspace_core.clock import iso, parse_iso
from workspace_core.errors import WorkspaceError
from workspace_core.workspace import Workspace

from .runners import ACTIVE, RUNNERS, Runners

log = logging.getLogger("workspace.challenger")

WEEK = timedelta(days=7)
TEMPLATE = "challenge"
TITLE = "Challenge this week's beliefs"
PURPOSE = (
    "Look for current evidence that any of these claims is wrong or out of date, so the owner "
    "can see it before an AI relies on them."
)


def instructions(targets: list[dict]) -> str:
    """The challenger's brief: the claims, each only as a claim under test."""
    claims = "\n".join(
        f"{n}. Claim under test (id `{t['id']}`): {t['claim']}" for n, t in enumerate(targets, 1)
    )
    return (
        "Test each claim below on its merits. Treat it only as a claim someone made, never as "
        "true: look for current evidence against it (search the web when it helps), and for "
        "evidence that it still holds.\n\n"
        f"{claims}\n\n"
        "When you find evidence that a claim is wrong or out of date, call propose_challenge "
        "with its id, what the evidence says instead, the evidence quoted, and its source (a "
        "link and its date). When you find none, propose nothing for it. Never publish, send "
        "or change anything else. Finish with complete_task, saying which claims you checked "
        "and what you found."
    )


class ChallengerWorker:
    def __init__(self, ws: Workspace, runners: Runners, interval: float = 600.0) -> None:
        self.ws = ws
        self.runners = runners
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def due(self) -> bool:
        """On, and no challenger task in the last week."""
        if not self.ws.rt.brain.policies().get("challenger"):
            return False
        since = self.ws.rt.clock.now() - WEEK
        owner = self.ws.owner()
        for task in self.ws.tasks.list(owner, include_archived=True, limit=200):
            if task.template == TEMPLATE and parse_iso(task.created_at) >= since:
                return False
        return True

    def run_once(self) -> bool:
        """Start this week's run when it is due and Claude Code can take it. False when there
        was nothing to do."""
        if not self.due():
            return False
        if any(run.status in ACTIVE for run in list(self.runners.runs.values())):
            return False
        status = self.runners.status(RUNNERS["claude"])
        if not status.installed or status.signed_in is False or not status.actor_id:
            log.info("the challenger waits for Claude Code to be installed and connected")
            return False
        targets = self.ws.rt.brain.challenge_targets(3)
        if not targets:
            return False
        owner = self.ws.owner()
        task = self.ws.tasks.create(
            owner,
            title=TITLE,
            purpose=PURPOSE,
            instructions=instructions(targets),
            assignee_id=status.actor_id,
            schedule={"kind": "manual"},
            output_contract={"artifacts": [], "tool": "propose_challenge"},
            review_policy="auto",
            template=TEMPLATE,
            provenance={
                "challenger": {
                    "targets": [t["id"] for t in targets],
                    "at": iso(self.ws.rt.clock.now()),
                }
            },
        )
        task = self.ws.tasks.mark_ready(owner, task.id)
        try:
            self.runners.start(owner, "claude", task.id)
        except WorkspaceError as exc:
            log.warning("could not start the challenger: %s", exc)
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="challenger", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("challenger tick failed")
            self._stop.wait(self.interval)
