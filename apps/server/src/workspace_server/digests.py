"""Summaries as things arrive: once a capture's text is in (a transcript, a document, a talk or
a recording turned into text), ask for its digest and run it with the local CLI, one at a time.

A capture brought in while summaries are on carries `summarize: auto` (services/captures.py);
the worker takes the oldest such capture with text and no digest asked for yet. When no CLI on
this computer can run it (none installed or signed in), the request still goes in and waits for
a model, as any AI work does, and the capture shows it waiting.
"""

from __future__ import annotations

import logging
import threading

from workspace_core.errors import WorkspaceError
from workspace_core.workspace import Workspace

from .runners import ACTIVE, Runners

log = logging.getLogger("workspace.digests")


class DigestWorker:
    def __init__(self, ws: Workspace, runners: Runners, interval: float = 10.0) -> None:
        self.ws = ws
        self.runners = runners
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Ask for one digest and start it. False when there was nothing to do now (nothing
        waiting, or a run already under way: one at a time)."""
        if any(run.status in ACTIVE for run in list(self.runners.runs.values())):
            return False
        waiting = self.ws.captures.to_summarize(limit=1)
        if not waiting:
            return False
        owner = self.ws.owner()
        task = self.ws.captures.summarize(owner, waiting[0])
        runner = next(
            (
                status
                for status in self.runners.statuses(owner)
                if status.one_click and status.installed and status.signed_in is not False
            ),
            None,
        )
        if runner is None:
            log.info("digest of %s waits for a model (no CLI here can run it)", waiting[0])
            return True
        try:
            self.runners.start(owner, runner.id, task.id)
        except WorkspaceError as exc:
            log.warning("could not start the digest of %s: %s", waiting[0], exc)
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="digests", daemon=True)
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
                log.exception("digest worker tick failed")
                worked = False
            self._stop.wait(2.0 if worked else self.interval)
