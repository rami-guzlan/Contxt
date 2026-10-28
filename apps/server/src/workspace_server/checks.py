"""Check 3 of the baseline check, in the background: the owner's own AI reads what may
disagree, side by side (services/adjudicate.py).

Each turn takes the oldest batch the Brain says is unread (a waiting proposal and up to eight
notes, or a note that went in on its own lately), asks Claude Code on this computer once,
with no tools and no MCP server, and keeps the verdicts in the Brain's ledger. It runs only
while the owner's policy allows it (`model_checks`, on by default) and Claude Code is
installed and signed in; without it, checks 1 and 2 stand alone and the cards say no AI has
read the pair yet. At most DAILY_PAIRS pairs a day; a batch whose answer could not be read
waits an hour before it is asked again.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading

from workspace_core.errors import WorkspaceError
from workspace_core.services import adjudicate
from workspace_core.workspace import Workspace

from .runners import ACTIVE, RUNNERS, Runners

log = logging.getLogger("workspace.checks")

DAILY_PAIRS = 60
# The model that reads the pairs: on the 80 labeled pairs (scripts/safeguards_eval.py) Sonnet
# named the relation in 77, Haiku in 69 and the default (Opus) in 79, at half Opus's price.
MODEL = "sonnet"
RETRY = dt.timedelta(hours=1)


class CheckWorker:
    def __init__(self, ws: Workspace, runners: Runners, interval: float = 20.0) -> None:
        self.ws = ws
        self.runners = runners
        self.interval = max(1.0, float(interval))
        self.asked: dict[str, int] = {}  # pairs asked, by day
        self.failed: dict[str, dt.datetime] = {}  # subject: when it may be asked again
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Read one batch. False when there was nothing to do now: checks are off, no model
        can answer, the day's pairs are used, a run is under way, or nothing is unread."""
        brain = self.ws.rt.brain
        if not brain.policies().get("model_checks", True):
            return False
        now = self.ws.rt.clock.now()
        today = now.date().isoformat()
        if self.asked.get(today, 0) >= DAILY_PAIRS:
            return False
        if any(run.status in ACTIVE for run in list(self.runners.runs.values())):
            return False
        batch = next(
            (
                b
                for b in brain.pending_checks(limit=4)
                if self.failed.get(str(b["subject"]), now) <= now
            ),
            None,
        )
        if batch is None:
            return False
        owner = self.ws.owner()
        status = self.runners.status(RUNNERS["claude"])
        if not status.installed or status.signed_in is False:
            return False
        pairs = list(batch["pairs"])[: max(1, DAILY_PAIRS - self.asked.get(today, 0))]
        batch = dict(batch, pairs=pairs)
        self.asked = {today: self.asked.get(today, 0) + len(pairs)}
        try:
            answer = self.runners.ask(owner, adjudicate.prompt(batch), job="check", model=MODEL)
        except WorkspaceError as exc:
            log.info("could not read %s side by side: %s", batch["subject"], exc)
            self.failed[str(batch["subject"])] = now + RETRY
            return True
        verdicts = adjudicate.parse(answer, batch)
        if not verdicts:
            log.info("the answer about %s could not be read", batch["subject"])
            self.failed[str(batch["subject"])] = now + RETRY
            return True
        brain.record_checks(verdicts)
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="checks", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                log.exception("check worker tick failed")
                worked = False
            self._stop.wait(5.0 if worked else self.interval)
