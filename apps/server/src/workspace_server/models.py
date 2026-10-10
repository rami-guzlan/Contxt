"""The models the app asks one question of, for the knowledge agent.

- Claude Code on this computer, the default: the same ask the baseline check uses (no tools,
  no MCP server, an empty folder, restricted), so it knows only what the prompt says.
- Local models through Ollama, when Ollama runs on this computer: free, private and quick, but
  small, so they get the short map and fewer candidates, and their answers are read like any
  other: what cannot be read is kept as nothing.
- The pinned local model (brain-logic plan 17), when the app's model service runs it: verified
  against the lock, its answers bound to a JSON schema. When it is here it is the default, and
  Claude Code becomes an opt-in (Settings, On this computer): it uses the person's own plan,
  and the agent's work then leaves the machine. Where no local model is here yet, Claude Code
  stays the agent unless the person turned it off.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from brainkit import machine as brain_machine
from brainkit import models_client
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, ValidationFailed

from .runners import RUNNERS, Runners

OLLAMA = os.environ.get("CONTXT_OLLAMA_URL") or "http://127.0.0.1:11434"
LIST_SECONDS = 30  # how long the list of local models is reused
THINKING = re.compile(r"<think>.*?</think>", re.S)


@dataclass(frozen=True)
class ModelChoice:
    id: str  # "claude", "ollama:<name>", "local:<name>"
    label: str
    kind: str  # "cli" | "local" (Ollama) | "pinned" (the app's model service)
    available: bool
    detail: str  # what it is, or why it cannot answer now
    brief: bool  # a small context: the short map and fewer candidates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _http(url: str, body: dict[str, Any] | None = None, *, timeout: float = 2.0) -> Any:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"} if data else {}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


class Models:
    def __init__(
        self,
        runners: Runners,
        *,
        ollama_url: str = OLLAMA,
        fetch: Callable[..., Any] | None = None,
        service: Callable[[], models_client.Status] | None = None,
        agent: Callable[[models_client.Status], Any] | None = None,
        settings: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.runners = runners
        self.ollama_url = ollama_url.rstrip("/")
        self.fetch = fetch or _http
        self.service = service or models_client.status  # the app's model service
        self.agent_client = agent or models_client.Agent
        self.settings = settings or brain_machine.load  # this computer's choices
        self._local: tuple[float, list[dict[str, Any]]] | None = None
        self._lock = threading.Lock()

    def _ollama_models(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._local and time.monotonic() - self._local[0] < LIST_SECONDS:
                return self._local[1]
        try:
            found = self.fetch(f"{self.ollama_url}/api/tags", timeout=1.5)
            models = [m for m in (found or {}).get("models") or [] if m.get("name")]
        except (OSError, ValueError, urllib.error.URLError):
            models = []
        with self._lock:
            self._local = (time.monotonic(), models)
        return models

    def _pinned(self) -> tuple[models_client.Status | None, str]:
        """The app's model service and the agent model it runs, when one is verified."""
        service = getattr(self, "service", models_client.status)  # a stand-in may set none
        try:
            found = service()
        except (OSError, ValueError):  # a lock or service that cannot be read runs nothing
            return None, ""
        return (found, found.agent) if found.agent else (None, "")

    def claude_allowed(self, pinned: str) -> bool:
        """Claude Code for the agent: the person's opt-in once a local model is here; until
        then it stays on unless they turned it off."""
        on = getattr(self, "settings", brain_machine.load)().get("agent_claude_code")
        return on is True or (on is None and not pinned)

    def default(self) -> str:
        """The agent's model when the owner chose none: the pinned local model when it is
        here, else Claude Code."""
        _service, pinned = self._pinned()
        return f"local:{pinned}" if pinned else "claude"

    def list(self) -> list[ModelChoice]:
        """Every model the agent could use here, the ones that can answer now first."""
        out = []
        _service, pinned = self._pinned()
        if pinned:
            out.append(
                ModelChoice(
                    id=f"local:{pinned}",
                    label=f"{pinned} (on this computer)",
                    kind="pinned",
                    available=True,
                    detail="Pinned and verified, through the app's model service: free and "
                    "private, its answers bound to a schema",
                    brief=True,
                )
            )
        claude = RUNNERS["claude"]
        status = self.runners.status(claude)
        allowed = self.claude_allowed(pinned)
        why = (
            "Off for the knowledge agent: turn it on in Settings, On this computer"
            if not allowed
            else f"Not installed: {claude.install}"
            if not status.installed
            else "Not signed in: sign in to Claude Code first"
            if status.signed_in is False
            else f"Claude Code {status.version or ''} on this computer".strip()
        )
        out.append(
            ModelChoice(
                id="claude",
                label="Claude Code (your CLI)",
                kind="cli",
                available=allowed and bool(status.installed) and status.signed_in is not False,
                detail=why,
                brief=False,
            )
        )
        for model in sorted(self._ollama_models(), key=lambda m: int(m.get("size") or 0)):
            name = str(model["name"])
            size = int(model.get("size") or 0)
            out.append(
                ModelChoice(
                    id=f"ollama:{name}",
                    label=f"{name} (local)",
                    kind="local",
                    available=True,
                    detail=(
                        f"On this computer through Ollama, {size / 1e9:.1f} GB"
                        if size
                        else "On this computer through Ollama"
                    ),
                    brief=True,
                )
            )
        return out

    def choose(self, wanted: str) -> ModelChoice:
        """The model to use: the one named, which must be able to answer now."""
        found = next((m for m in self.list() if m.id == wanted), None)
        if found is None:
            if wanted.startswith("local:"):
                raise Conflict(
                    f"{wanted.split(':', 1)[1]} is not running on this computer: download it "
                    "in Settings, On this computer, or choose another model."
                )
            if wanted.startswith("ollama:"):
                raise Conflict(
                    f"{wanted.split(':', 1)[1]} is not available: start Ollama, or choose "
                    "another model in the knowledge agent's settings."
                )
            raise ValidationFailed(f"No model {wanted} here.", field="model")
        if not found.available:
            raise Conflict(f"{found.label} cannot answer now: {found.detail}.")
        return found

    def ask(
        self,
        who: Principal,
        choice: ModelChoice,
        prompt: str,
        *,
        json_only: bool = False,
        timeout: float = 240.0,
        job: str = "agent",
    ) -> str:
        """One answer to one prompt; what it used is counted under `job` in the cost report
        (a local model's tokens cost nothing, but they are counted too)."""
        if choice.id == "claude":
            return self.runners.ask(who, prompt, timeout=timeout, job=job)
        if choice.id.startswith("local:"):
            who.require("workspace.admin")
            service, pinned = self._pinned()
            if service is None or f"local:{pinned}" != choice.id:
                raise Conflict("The local model is not running on this computer now.")
            try:
                found = self.agent_client(service).generate(
                    prompt,
                    schema={"type": "object"} if json_only else None,
                    max_tokens=2000,
                    timeout=timeout,
                )
            except (models_client.ServiceError, OSError, ValueError) as exc:
                raise Conflict(f"The local model did not answer: {exc}") from exc
            usage = found.get("usage") or {}
            self.runners.count_usage(
                job,
                {
                    "model": choice.id,
                    "tokens_in": int(usage.get("tokens_in") or 0),
                    "tokens_out": int(usage.get("tokens_out") or 0),
                    "cost": 0.0,
                    "ms": int(found.get("latency_ms") or 0) or None,
                },
            )
            return THINKING.sub("", str(found.get("text") or "")).strip()
        if choice.id.startswith("ollama:"):
            who.require("workspace.admin")
            body: dict[str, Any] = {
                "model": choice.id.split(":", 1)[1],
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                # A thinking model (qwen3, say) would otherwise write pages before it answers,
                # slow on a laptop's CPU; the procedure already says how to think.
                "think": False,
                "options": {"temperature": 0.2, "num_ctx": 8192},
            }
            if json_only:
                body["format"] = "json"
            try:
                found = self.fetch(f"{self.ollama_url}/api/chat", body, timeout=timeout)
            except (OSError, ValueError, urllib.error.URLError) as exc:
                raise Conflict(f"The local model did not answer: {exc}") from exc
            if isinstance(found, dict) and (
                found.get("prompt_eval_count") or found.get("eval_count")
            ):
                self.runners.count_usage(
                    job,
                    {
                        "model": choice.id,
                        "tokens_in": int(found.get("prompt_eval_count") or 0),
                        "tokens_out": int(found.get("eval_count") or 0),
                        "cost": 0.0,
                        "ms": int(int(found.get("total_duration") or 0) / 1e6) or None,
                    },
                )
            text = str(((found or {}).get("message") or {}).get("content") or "")
            return THINKING.sub("", text).strip()
        raise ValidationFailed(f"No model {choice.id} here.", field="model")
