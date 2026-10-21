"""The models the app asks one question of, for the knowledge agent: any the person chooses.

- The AI CLIs on this computer: Claude Code, Codex (ChatGPT) and Gemini CLI, each on the
  person's own plan, asked with nothing but the prompt (an empty folder, none of the person's
  MCP servers, told to answer from the prompt alone). Any model the CLI offers can be named
  (`codex:gpt-5.1-codex`, `gemini:gemini-2.5-flash`); without one, the CLI's own default.
  With nothing chosen, the agent works through the first of them that can answer here.
- Local models through Ollama, when Ollama runs on this computer: free, private and quick, but
  small, so they get the short map and fewer candidates, and their answers are read like any
  other: what cannot be read is kept as nothing.
- The pinned local model (brain-logic plan 17), when the app's model service runs it: verified
  against the lock, its answers bound to a JSON schema. When it is here it is the default, and
  the CLIs become an opt-in (Settings, On this computer): they use the person's own plans,
  and the agent's work then leaves the machine. Where no local model is here yet, the CLIs
  stay on unless the person turned them off.
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
from dataclasses import asdict, dataclass, replace
from typing import Any

from brainkit import machine as brain_machine
from brainkit import models_client
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, ValidationFailed

from .runners import RUNNERS, Runners

OLLAMA = os.environ.get("CONTXT_OLLAMA_URL") or "http://127.0.0.1:11434"
LIST_SECONDS = 30  # how long the list of local models is reused
THINKING = re.compile(r"<think>.*?</think>", re.S)
CLIS = ("claude", "codex", "gemini")  # the AI CLIs the agent can work through, in this order
MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}$")  # a model a CLI offers


@dataclass(frozen=True)
class ModelChoice:
    id: str  # "claude", "codex", "gemini" (each may name a model: "codex:<model>"),
    # "ollama:<name>", "local:<name>"
    label: str
    kind: str  # "cli" | "local" (Ollama) | "pinned" (the app's model service)
    available: bool
    detail: str  # what it is, or why it cannot answer now
    brief: bool  # a small context: the short map and fewer candidates

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Where each CLI sends what the knowledge agent reads, and where it keeps its own model.
VENDORS = {"claude": "Anthropic", "codex": "OpenAI", "gemini": "Google"}
CLI_CONFIG = {
    "claude": (".claude", "settings.json"),
    "codex": (".codex", "config.toml"),
    "gemini": (".gemini", "settings.json"),
}
TOML_MODEL = re.compile(r'^\s*model\s*=\s*"([^"]+)"\s*$')


def cli_model(cli: str, home: str | None = None) -> tuple[str | None, str]:
    """(the model a CLI is set to, the file that says so), read from the CLI's own
    configuration and never written; (None, "") when it names none (its default)."""
    parts = CLI_CONFIG.get(cli)
    if parts is None:
        return None, ""
    path = os.path.join(home or os.path.expanduser("~"), *parts)
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return None, ""
    if path.endswith(".toml"):
        for line in text.splitlines():
            if line.strip().startswith("["):
                break  # a profile's model is not the one the CLI uses by default
            found = TOML_MODEL.match(line)
            if found:
                return found.group(1), path
        return None, ""
    try:
        data = json.loads(text)
    except ValueError:
        return None, ""
    model = data.get("model") if isinstance(data, dict) else None
    if isinstance(model, dict):
        model = model.get("name")
    return (str(model), path) if isinstance(model, str) and model.strip() else (None, "")


def provider_card(choice: ModelChoice, *, home: str | None = None) -> dict[str, Any]:
    """What the knowledge agent's page says about the model it works through: the provider,
    the model (named here, or the one the CLI is set to), whether it can answer now, and
    where what it reads is sent."""
    cli, _, named = choice.id.partition(":")
    if choice.kind == "cli":
        vendor = VENDORS.get(cli, cli)
        model, path = (named, "named here") if named else cli_model(cli, home)
        source = path or "the CLI's own default"
        data = (
            f"What the knowledge agent reads for a job (the notes and captures it works on) "
            f"is sent to {vendor} through {choice.label}, on your own plan."
        )
    else:
        vendor, model, source = "this computer", named or None, "named here"
        data = "What the knowledge agent reads stays on this computer."
    return {
        "id": choice.id,
        "label": choice.label,
        "vendor": vendor,
        "model": model,
        "model_from": "named here" if named else source,
        "available": choice.available,
        "health": choice.detail,
        "data": data,
        "switches": "never on its own: when it cannot answer, the work stops and says so",
    }


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

    def cli_allowed(self, pinned: str) -> bool:
        """The AI CLIs for the agent: the person's opt-in once a local model is here; until
        then they stay on unless the person turned them off (the machine setting keeps its
        first name, `agent_claude_code`)."""
        on = getattr(self, "settings", brain_machine.load)().get("agent_claude_code")
        return on is True or (on is None and not pinned)

    def default(self) -> str:
        """The agent's model when the owner chose none: the pinned local model when it is
        here, else the first AI CLI here that can answer (Claude Code, Codex, Gemini CLI),
        else a local model through Ollama, else Claude Code, which then says how to set it
        up."""
        _service, pinned = self._pinned()
        if pinned:
            return f"local:{pinned}"
        ready = [m for m in self.list() if m.available]
        first = next((m for m in ready if m.kind == "cli"), None) or next(iter(ready), None)
        return first.id if first is not None else "claude"

    def _cli(self, cli: str, allowed: bool) -> ModelChoice:
        spec = RUNNERS[cli]
        status = self.runners.status(spec)
        why = (
            "Off for the knowledge agent: turn the CLIs on in Settings, On this computer"
            if not allowed
            else f"Not installed: {spec.install}"
            if not status.installed
            else f"Not signed in: sign in with `{status.sign_in}` first"
            if status.signed_in is False
            else f"{spec.label} {status.version or ''} on this computer, on your own plan".strip()
        )
        return ModelChoice(
            id=cli,
            label=spec.label,
            kind="cli",
            available=allowed and bool(status.installed) and status.signed_in is not False,
            detail=why,
            brief=False,
        )

    def list(self) -> list[ModelChoice]:
        """Every model the agent could use here: the pinned local model, the AI CLIs, then
        the local models Ollama serves."""
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
        allowed = self.cli_allowed(pinned)
        out += [self._cli(cli, allowed) for cli in CLIS]
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
        """The model to use: the one named, which must be able to answer now. An AI CLI may
        name one of its models after a colon (`gemini:gemini-2.5-flash`)."""
        cli, _, name = wanted.partition(":")
        if cli in CLIS and name:
            if not MODEL_NAME.match(name):
                raise ValidationFailed(
                    f"{name!r} is not a model name: use the name the CLI knows it by, "
                    "without spaces.",
                    field="model",
                )
            base = self.choose(cli)
            return replace(base, id=wanted, label=f"{base.label}, {name}")
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
        cli, _, name = choice.id.partition(":")
        if cli in CLIS:
            return self.runners.ask(
                who, prompt, timeout=timeout, job=job, runner=cli, model=name or None
            )
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
