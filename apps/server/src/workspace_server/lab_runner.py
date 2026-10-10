"""Start and stop a Lab's runner, with the app's settings kept out of it.

The runner is the fixed executable and argument list the Lab's contract names. It starts:

- without a shell, from the folder the contract names, which must be inside the Lab's folder
  (`lab_contract.open_lab` checks this before every use)
- with a short environment of its own: `PATH`, `SYSTEMROOT`, `TEMP`, `TMP` and `USERPROFILE`,
  and the variables the contract lists. Never the app's `.env` values or any `CONTXT_` or
  `WORKSPACE_` setting: tests run with the live storage settings loaded write to the live store
- one run at a time, and never while the Lab's own run lock is held

A run is the runner's `run` command left running. It prints the run's id first, and appends its
events to the progress file this module names (in the app's own data folder), which the page
tails. Cancelling calls the runner's `cancel` command, then ends whatever is left of the process
tree. Stopping the app ends it too.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from workspace_core.clock import iso
from workspace_core.errors import Conflict, ValidationFailed

from .lab_contract import (
    FORBIDDEN_ENV_PREFIXES,
    Contract,
    Lab,
    Results,
    Status,
    check_id,
)

log = logging.getLogger(__name__)

BASE_ENV = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "USERPROFILE")
SAFE_WORD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")
START_WAIT = 20.0  # seconds for a runner to print its run id or refuse
CANCEL_WAIT = 10.0  # seconds a runner gets to stop itself before its tree is ended
KEEP_PROGRESS = 40  # progress files kept in the app's data folder


def child_environment(contract: Contract) -> dict[str, str]:
    """The only variables a runner is given."""
    env: dict[str, str] = {}
    for name in (*BASE_ENV, *contract.env_allow):
        if name.upper().startswith(FORBIDDEN_ENV_PREFIXES):
            continue
        value = os.environ.get(name)
        if value is not None:
            env[name] = value
    return env


def kill_tree(process: subprocess.Popen[str]) -> None:
    """End the process and everything it started."""
    pid = process.pid
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=20,
                check=False,
            )
        else:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(pid, sig)
                except (ProcessLookupError, PermissionError):
                    break
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    continue
    except (OSError, subprocess.SubprocessError):
        log.warning("could not end process %s", pid, exc_info=True)
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.warning("process %s did not exit", pid)


def popen_options() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


@dataclass
class Active:
    """The run this app started: running, then done, failed or cancelled."""

    ticket: str
    kind: str
    suite: str | None
    progress_file: str
    started_at: str
    run: str | None = None
    state: str = "running"
    message: str = ""
    exit_code: int | None = None
    ended_at: str | None = None
    cancel_asked: bool = False
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    id_ready: threading.Event = field(default_factory=threading.Event, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket": self.ticket,
            "run": self.run,
            "kind": self.kind,
            "suite": self.suite,
            "state": self.state,
            "message": self.message,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


class LabRunner:
    def __init__(self, data_dir: str) -> None:
        self.folder = os.path.join(data_dir, "test-the-brain", "progress")
        self.active: Active | None = None
        self._lock = threading.RLock()
        self._counter = 0

    # ----- asking the runner things
    def _command(self, lab: Lab, *words: str) -> list[str]:
        return [lab.exe, *lab.contract.runner.args, *words]

    def call(
        self, lab: Lab, *words: str, timeout: float = 20.0
    ) -> subprocess.CompletedProcess[str]:
        """Run one short command of the runner and wait for it."""
        return subprocess.run(
            self._command(lab, *words),
            cwd=lab.cwd,
            env=child_environment(lab.contract),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            check=False,
        )

    def fetch_status(self, lab: Lab) -> Status | None:
        """`status --json`, for a Lab that has not written status.json yet."""
        try:
            done = self.call(lab, "status", "--json", timeout=20)
            if done.returncode != 0:
                return None
            return Status.model_validate_json(done.stdout)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    # ----- starting
    def start(
        self,
        lab: Lab,
        status: Status | None,
        kind: str,
        *,
        suite: str | None = None,
        confirm: bool = False,
    ) -> Active:
        if not SAFE_WORD.match(kind or ""):
            raise ValidationFailed("That is not a run kind.", field="kind")
        if suite is not None and not SAFE_WORD.match(suite):
            raise ValidationFailed("That is not a suite name.", field="suite")
        listed = status.kind(kind) if status else None
        if listed is None:
            names = ", ".join(k.id for k in (status.run_kinds if status else [])) or "none"
            raise ValidationFailed(
                f"This Lab does not list a run called {kind}. It lists: {names}.", field="kind"
            )
        if listed.suites and suite and suite not in listed.suites:
            raise ValidationFailed(f"{kind} has no suite called {suite}.", field="suite")
        with self._lock:
            if self.active and self.active.state == "running":
                raise Conflict(
                    f"A {self.active.kind} run is already running. Wait for it, or cancel it."
                )
            holder = status.lock_holder() if status else None
            if holder:
                raise Conflict(
                    f"The Lab is busy: run {holder} holds its run lock. "
                    "Wait for it to finish, or cancel it from wherever it was started.",
                    lock_holder=holder,
                )
            if listed.paid and not confirm:
                raise Conflict(
                    f"{listed.name or kind} uses paid model calls. Press again to run it.",
                    needs_confirmation=True,
                    estimate=listed.estimate,
                    kind=kind,
                )
            os.makedirs(self.folder, exist_ok=True)
            self._counter += 1
            ticket = f"t-{int(time.time())}-{self._counter}"
            progress = os.path.join(self.folder, ticket + ".jsonl")
            with open(progress, "w", encoding="utf-8"):
                pass
            words = ["run", kind]
            if suite:
                words += ["--suite", suite]
            words += ["--progress", progress]
            try:
                process = subprocess.Popen(
                    self._command(lab, *words),
                    cwd=lab.cwd,
                    env=child_environment(lab.contract),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    shell=False,
                    **popen_options(),
                )
            except OSError as exc:
                raise Conflict(f"The Lab's runner would not start: {exc}") from None
            active = Active(
                ticket=ticket,
                kind=kind,
                suite=suite,
                progress_file=progress,
                started_at=iso(datetime.now(UTC)),
                process=process,
            )
            self.active = active
            threading.Thread(
                target=self._watch, args=(active,), daemon=True, name=f"lab-run-{ticket}"
            ).start()
        if not active.id_ready.wait(START_WAIT):
            self._end(active, "failed", "The Lab's runner did not say which run it started.")
            raise Conflict("The Lab's runner did not answer. It was stopped.")
        if active.state != "running" and not active.run:
            raise Conflict(active.message or "The Lab's runner stopped without starting a run.")
        self._prune()
        return active

    def _watch(self, active: Active) -> None:
        """Read the runner's output until it ends, then settle the run's state."""
        process = active.process
        assert process is not None and process.stdout is not None and process.stderr is not None
        lines: queue.Queue[str] = queue.Queue()
        tails: dict[str, list[str]] = {"out": [], "err": []}

        def drain(stream: Any, key: str) -> None:
            for line in stream:
                text = line.strip()
                if text:
                    tails[key] = (tails[key] + [text])[-12:]
                    if key == "out":
                        lines.put(text)

        threads = [
            threading.Thread(target=drain, args=(process.stdout, "out"), daemon=True),
            threading.Thread(target=drain, args=(process.stderr, "err"), daemon=True),
        ]
        for thread in threads:
            thread.start()
        first = None
        deadline = time.monotonic() + START_WAIT
        while first is None and time.monotonic() < deadline:
            try:
                first = lines.get(timeout=0.1)
            except queue.Empty:
                if not threads[0].is_alive():  # it ended without printing a run id
                    try:
                        first = lines.get_nowait()
                    except queue.Empty:
                        break
        word = first.split()[0] if first else ""
        active.run = word if SAFE_WORD.match(word) else None
        active.id_ready.set()
        code = process.wait()
        for thread in threads:
            thread.join(timeout=2)
        for stream in (process.stdout, process.stderr):
            stream.close()
        active.exit_code = code
        said = " ".join(tails["err"] or tails["out"][-3:])
        if active.cancel_asked:
            self._end(active, "cancelled", "Stopped on request.")
        elif code == 0:
            last = Results.progress(active.progress_file, 0, 100000)["events"]
            if last and last[-1].get("event") == "cancelled":
                self._end(active, "cancelled", last[-1].get("message") or "Stopped.")
            else:
                self._end(active, "done", "")
        else:
            self._end(active, "failed", said or f"The runner stopped with code {code}.")
        if sys.platform != "win32":  # a group is still addressable after its leader is gone
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _end(self, active: Active, state: str, message: str) -> None:
        with self._lock:
            if active.ended_at:
                return
            active.state = state
            active.message = message
            active.ended_at = iso(datetime.now(UTC))
            active.id_ready.set()

    # ----- stopping
    def cancel(self, lab: Lab, run: str) -> dict[str, Any]:
        """Ask the runner to stop `run`; end its process tree if it does not. A run started
        somewhere else (the Lab's own pane) is asked to stop the same way."""
        name = check_id(run, what="The run")
        active = self.active
        ours = active is not None and active.run == name and active.state == "running"
        if ours:
            assert active is not None
            active.cancel_asked = True
        try:
            done = self.call(lab, "cancel", name, timeout=20)
        except (OSError, subprocess.SubprocessError) as exc:
            if not ours:
                raise Conflict(f"The Lab's runner would not cancel: {exc}") from None
            done = None
        if not ours:
            if done is not None and done.returncode != 0:
                raise Conflict((done.stderr or done.stdout or "The Lab would not cancel.").strip())
            return {"run": name, "state": "cancelling", "ours": False}
        assert active is not None and active.process is not None
        end = time.monotonic() + CANCEL_WAIT
        while time.monotonic() < end and active.state == "running":
            time.sleep(0.1)
        if active.state == "running":
            kill_tree(active.process)
            for _ in range(50):
                if active.state != "running":
                    break
                time.sleep(0.1)
        else:
            kill_tree(active.process)  # whatever the runner left behind
        return active.to_dict()

    def close(self) -> None:
        """The app is stopping: end a run in progress and everything it started."""
        active = self.active
        if active and active.process is not None and active.state == "running":
            active.cancel_asked = True
            kill_tree(active.process)

    # ----- the live view
    def live(self, after: int = 0) -> dict[str, Any]:
        active = self.active
        if active is None:
            return {"active": None, "events": [], "next": after}
        found = Results.progress(active.progress_file, after)
        return {"active": active.to_dict(), **found}

    def _prune(self) -> None:
        try:
            files = sorted(
                (os.path.join(self.folder, n) for n in os.listdir(self.folder)),
                key=os.path.getmtime,
            )
        except OSError:
            return
        for path in files[:-KEEP_PROGRESS]:
            try:
                os.remove(path)
            except OSError:
                pass
