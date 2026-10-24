"""Gnomon's own n8n, on this computer: installed on the owner's first click into Gnomon's data
folder (a pinned release), started bound to 127.0.0.1 only, and stopped with Gnomon.

Workflows go in and out through n8n's own command line (`import:workflow`, `update:workflow
--active`) against the same data folder. A running n8n reads which workflows are active when it
starts, so a change of that is followed by a restart. The app sign-ins a workflow uses live in
n8n; Gnomon never sees them.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

PINNED = "1.123.84"  # runs on Node.js 20.19 to 24, as Contxt does (n8n 2 needs Node.js 24)
PORT = 5678


def _quiet() -> dict[str, Any]:
    return {"creationflags": 0x08000000} if sys.platform == "win32" else {}  # no console window


class N8nHost:
    def __init__(
        self,
        data_dir: str,
        *,
        port: int = PORT,
        popen: Callable[..., Any] = subprocess.Popen,
        run: Callable[..., Any] = subprocess.run,
        which: Callable[[str], str | None] = shutil.which,
        alive: Callable[[str], bool] | None = None,
    ) -> None:
        self.root = os.path.join(data_dir, "n8n")
        self.app = os.path.join(self.root, "app")  # the installed n8n
        self.home = os.path.join(self.root, "home")  # n8n's own data: its database, sign-ins
        self.port = port
        self.popen, self.run, self.which = popen, run, which
        self.alive = alive or self._healthy
        self.proc: Any = None
        self._installing = False
        self._problem = ""
        self._guard = threading.Lock()

    # ---------------------------------------------------------------- where things are

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _entry(self) -> str:
        return os.path.join(self.app, "node_modules", "n8n", "bin", "n8n")

    def installed(self) -> bool:
        return os.path.isfile(self._entry())

    def _node(self) -> str:
        found = self.which("node")
        if not found:
            raise RuntimeError("Node.js is not installed on this computer.")
        return found

    def env(self) -> dict[str, str]:
        """n8n on this computer only, with no telemetry and its data in Gnomon's folder."""
        return dict(
            os.environ,
            N8N_USER_FOLDER=self.home,
            N8N_HOST="127.0.0.1",
            N8N_LISTEN_ADDRESS="127.0.0.1",
            N8N_PORT=str(self.port),
            N8N_PROTOCOL="http",
            N8N_SECURE_COOKIE="false",
            N8N_DIAGNOSTICS_ENABLED="false",
            N8N_PERSONALIZATION_ENABLED="false",
            N8N_VERSION_NOTIFICATIONS_ENABLED="false",
            N8N_PUBLIC_API_DISABLED="true",
        )

    # ---------------------------------------------------------------- status

    def _healthy(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(url + "/healthz", timeout=2) as response:
                return bool(response.status == 200)
        except OSError:
            return False

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None and self.alive(self.url)

    def status(self) -> dict[str, Any]:
        installed = self.installed()
        running = installed and self.running()
        if self._installing:
            line = f"Installing n8n {PINNED} on this computer. It takes a few minutes, once."
        elif self._problem:
            line = self._problem
        elif not installed:
            line = "Not installed. Host n8n here to read your apps without spending tokens."
        elif running:
            line = f"Running on this computer at {self.url}. Sign in to your apps there."
        else:
            line = "Installed, not running."
        return {
            "installed": installed,
            "installing": self._installing,
            "running": running,
            "url": self.url,
            "version": PINNED,
            "line": line,
        }

    # ---------------------------------------------------------------- install, start, stop

    def install(self, *, wait: bool = False) -> dict[str, Any]:
        """Install the pinned n8n into Gnomon's data folder (in the background)."""
        with self._guard:
            if self._installing or self.installed():
                return self.status()
            self._installing, self._problem = True, ""

        def work() -> None:
            try:
                npm = self.which("npm") or self.which("npm.cmd")
                if not npm:
                    raise RuntimeError("npm is not installed on this computer.")
                os.makedirs(self.app, exist_ok=True)
                done = self.run(
                    [
                        npm,
                        "install",
                        f"n8n@{PINNED}",
                        "--prefix",
                        self.app,
                        "--omit=dev",
                        "--no-audit",
                        "--no-fund",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    **_quiet(),
                )
                if done.returncode != 0 or not self.installed():
                    tail = (done.stderr or done.stdout or "").strip().splitlines()[-1:]
                    raise RuntimeError("n8n could not be installed: " + " ".join(tail)[:200])
            except (OSError, RuntimeError) as exc:
                self._problem = str(exc)
            finally:
                self._installing = False

        if wait:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()
        return self.status()

    def start(self, *, wait: float = 60.0) -> dict[str, Any]:
        """Start n8n on this computer only (if installed and not already running)."""
        if not self.installed():
            raise RuntimeError("Host n8n here first: it is not installed.")
        if self.proc is not None and self.proc.poll() is None:
            return self.status()
        os.makedirs(self.home, exist_ok=True)
        self.proc = self.popen(
            [self._node(), self._entry(), "start"],
            cwd=self.root,
            env=self.env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **_quiet(),
        )
        until = time.monotonic() + wait
        while time.monotonic() < until and not self.alive(self.url):
            if self.proc.poll() is not None:
                self._problem = "n8n stopped as it started. Try starting it again."
                break
            time.sleep(0.5)
        return self.status()

    def stop(self) -> dict[str, Any]:
        proc, self.proc = self.proc, None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
        return self.status()

    def close(self) -> None:
        self.stop()

    def remember(self, on: bool) -> None:
        """Whether n8n starts with Gnomon (the owner started it last time, or stopped it)."""
        os.makedirs(self.root, exist_ok=True)
        marker = os.path.join(self.root, "start-with-gnomon")
        if on:
            open(marker, "w", encoding="utf-8").close()
        elif os.path.exists(marker):
            os.remove(marker)

    def error_secret_hash(self) -> str | None:
        """The hash of the secret Gnomon's error-report workflow posts with (None: not set up)."""
        try:
            with open(os.path.join(self.root, "errors.sha256"), encoding="utf-8") as handle:
                return handle.read().strip() or None
        except OSError:
            return None

    def keep_error_secret_hash(self, kept: str) -> None:
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, "errors.sha256"), "w", encoding="utf-8") as handle:
            handle.write(kept)

    def starts_with_gnomon(self) -> bool:
        return self.installed() and os.path.exists(os.path.join(self.root, "start-with-gnomon"))

    # ---------------------------------------------------------------- workflows

    def _cli(self, *args: str) -> str:
        done = self.run(
            [self._node(), self._entry(), *args],
            cwd=self.root,
            env=self.env(),
            capture_output=True,
            text=True,
            check=False,
            **_quiet(),
        )
        if done.returncode != 0:
            tail = (done.stderr or done.stdout or "").strip().splitlines()[-1:]
            raise RuntimeError(f"n8n {args[0]} failed: " + " ".join(tail)[:200])
        return str(done.stdout or "")

    def put_workflow(self, workflow: dict[str, Any], *, active: bool) -> str:
        """Put a workflow into n8n (by its id, so a change replaces it) and set it active or
        not. n8n's command line and a running n8n can't share its database, so a running n8n
        stops for it and starts again after (which is also how it picks the change up).
        Returns the workflow's id."""
        if not self.installed():
            raise RuntimeError("Host n8n here first: it is not installed.")
        workflow_id = str(workflow.get("id") or "")
        if not workflow_id:
            raise ValueError("A workflow needs its id.")
        was_running = self.proc is not None and self.proc.poll() is None
        if was_running:
            self.stop()
        folder = tempfile.mkdtemp(prefix="gnomon-n8n-")
        try:
            path = os.path.join(folder, "workflow.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({**workflow, "active": False}, handle)
            self._cli("import:workflow", f"--input={path}")
            self._cli("update:workflow", f"--id={workflow_id}", f"--active={str(active).lower()}")
        finally:
            shutil.rmtree(folder, ignore_errors=True)
            if was_running:
                self.start()
        return workflow_id
