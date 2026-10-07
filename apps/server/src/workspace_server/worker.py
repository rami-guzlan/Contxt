"""The background worker: the server's clock.

Each tick expires runs whose lease ran out (their tasks go back in the queue), wakes recurring
tasks whose next occurrence has arrived, and hands AI work that waited for a model to the one
that can now take it. The bus also expires and wakes lazily when a model asks for work, so a
missed tick never loses anything.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from workspace_core.workspace import Workspace

log = logging.getLogger("workspace.worker")


@dataclass
class Tick:
    expired: int
    woke: int
    assigned: int = 0


class Worker:
    def __init__(self, ws: Workspace, interval: float = 15.0) -> None:
        self.ws = ws
        self.interval = max(1.0, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def tick(self) -> Tick:
        expired = self.ws.bus.expire_leases()
        woke = self.ws.bus.schedule_due()
        system = self.ws.system()
        assigned = self.ws.distill.assign_waiting(system)
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
