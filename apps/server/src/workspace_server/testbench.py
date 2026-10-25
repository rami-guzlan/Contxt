"""The Test Bench's three panels (Release 1 plan, 15.3).

The same request answered up to three ways by the same runner and model on this computer:

    none     no brain: the request alone
    full     the full brain: the startup context and the packet, as a model with no tools
             needs it
    custom   the packet with what the person unchecked left out, and nothing in its place

Fair by construction, as "See the difference" is: every panel runs headless through the
runners with no tools and no MCP server (the Brain's and the person's connectors are off), the
prompt on stdin, so the only variable is the context. Each panel keeps its output, the packet
it used and its hash, the tokens in and out, the cost, and the time. A run happens only when
the person presses Run, after an estimate. Runs are kept in memory; tests and suites (PR D)
store theirs.
"""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import asdict, dataclass, field
from typing import Any

from workspace_core.clock import iso
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.ids import new_id
from workspace_core.workspace import Workspace

from .difference import WITH_CONTEXT
from .runners import RUNNERS, Runners

log = logging.getLogger(__name__)

MODES = ("none", "full", "custom")
MAX_REQUEST = 4000
KEEP = 30
PROVIDERS = {"claude": "Anthropic", "codex": "OpenAI", "gemini": "Google"}


@dataclass
class Panel:
    mode: str
    status: str = "waiting"  # waiting | running | done | failed
    output: str = ""
    packet: str = ""  # the context this panel was given ("" for no brain)
    packet_hash: str = ""
    included: dict[str, Any] = field(default_factory=dict)  # what custom kept or left out
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    ms: int | None = None
    measured: bool = False
    error: str | None = None


@dataclass
class BenchRun:
    id: str
    request: str
    project: str | None
    runner: str
    model: str | None
    provider: str
    brain_version: str
    started_at: str
    panels: list[Panel]
    status: str = "running"
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


def _cost(model: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    """A price from the cost table when the runner did not report one."""
    try:
        from brainkit import costs

        if costs.price_for(model) is None:
            return None
        found = costs.call_cost(model, tokens_in or 0, tokens_out or 0)
    except (ImportError, ValueError, TypeError):  # no price, never an error
        return None
    return round(float(found), 6) if isinstance(found, int | float) else None


class Bench:
    def __init__(self, ws: Workspace, runners: Runners) -> None:
        self.ws = ws
        self.runners = runners
        self.runs: dict[str, BenchRun] = {}
        self._lock = threading.Lock()

    def _contexts(
        self,
        who: Principal,
        request: str,
        project: str | None,
        modes: list[str],
        include: dict[str, Any] | None,
        exclude: dict[str, Any] | None,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        """The context each panel gets, and the full packet's preview."""
        startup = str(self.ws.rt.brain.kernel(tools=False).get("text") or "")
        full = self.ws.brain.preview(who, request, project=project, tools=False)
        out = {"none": ""}
        if "full" in modes:
            out["full"] = "\n\n".join(p for p in (startup, str(full.get("text") or "")) if p)
        if "custom" in modes:
            custom = self.ws.brain.preview(
                who, request, project=project, tools=False, include=include, exclude=exclude
            )
            out["custom"] = "\n\n".join(p for p in (startup, str(custom.get("text") or "")) if p)
        return out, full

    def estimate(
        self,
        who: Principal,
        request: str,
        *,
        project: str | None = None,
        modes: list[str] | None = None,
        include: dict[str, Any] | None = None,
        exclude: dict[str, Any] | None = None,
        runner: str = "claude",
        model: str | None = None,
    ) -> dict[str, Any]:
        """What a run would send, before it is pressed: tokens in per panel, and the price."""
        who.require("workspace.admin")
        text, chosen = self._check(request, modes, runner)
        contexts, _full = self._contexts(who, text, project, chosen, include, exclude)
        panels = []
        for mode in chosen:
            prompt = self._prompt(text, contexts.get(mode, ""))
            tokens = len(prompt) // 4
            panels.append(
                {"mode": mode, "tokens_in": tokens, "cost": _cost(model or runner, tokens, 0)}
            )
        return {
            "runner": runner,
            "model": model,
            "provider": PROVIDERS.get(runner, runner),
            "panels": panels,
            "estimated": True,
        }

    def _check(self, request: str, modes: list[str] | None, runner: str) -> tuple[str, list[str]]:
        text = " ".join(str(request or "").split())
        if not text:
            raise ValidationFailed("Type the request to run.", field="request")
        if len(text) > MAX_REQUEST:
            raise ValidationFailed(f"Keep it under {MAX_REQUEST:,} characters.", field="request")
        chosen = [m for m in (modes or list(MODES)) if m in MODES]
        if not chosen:
            raise ValidationFailed(f"Run one of {', '.join(MODES)}.", field="modes")
        if runner not in RUNNERS:
            raise ValidationFailed(f"Runner is one of {', '.join(RUNNERS)}.", field="runner")
        return text, list(dict.fromkeys(chosen))

    @staticmethod
    def _prompt(request: str, context: str) -> str:
        return WITH_CONTEXT.format(context=context.strip(), request=request) if context else request

    def start(
        self,
        who: Principal,
        request: str,
        *,
        project: str | None = None,
        modes: list[str] | None = None,
        include: dict[str, Any] | None = None,
        exclude: dict[str, Any] | None = None,
        runner: str = "claude",
        model: str | None = None,
    ) -> BenchRun:
        """Run the panels in the background, one after another, with the same runner and
        model. Only the owner runs one: it starts a CLI on this computer."""
        who.require("workspace.admin")
        text, chosen = self._check(request, modes, runner)
        contexts, full = self._contexts(who, text, project, chosen, include, exclude)
        panels = [
            Panel(
                mode=m,
                packet=contexts.get(m, ""),
                packet_hash=_hash(contexts.get(m, "")),
                included=(
                    {"include": include or {}, "exclude": exclude or {}} if m == "custom" else {}
                ),
            )
            for m in chosen
        ]
        run = BenchRun(
            id=new_id("bench", self.ws.rt.clock.now()),
            request=text,
            project=project or None,
            runner=runner,
            model=model or None,
            provider=PROVIDERS.get(runner, runner),
            brain_version=str(full.get("brain_version") or "unknown"),
            started_at=iso(self.ws.rt.clock.now()),
            panels=panels,
        )
        with self._lock:
            self.runs[run.id] = run
            for old in sorted(self.runs.values(), key=lambda r: r.started_at)[:-KEEP]:
                self.runs.pop(old.id, None)
        threading.Thread(target=self._run, args=(who, run), daemon=True, name="bench").start()
        return run

    def _run(self, who: Principal, run: BenchRun) -> None:
        for panel in run.panels:
            panel.status = "running"
            try:
                found = self.runners.ask_measured(
                    who,
                    self._prompt(run.request, panel.packet),
                    job="bench",
                    runner=run.runner,
                    model=run.model,
                )
                panel.output = str(found.get("answer") or "")
                panel.tokens_in = found.get("tokens_in")
                panel.tokens_out = found.get("tokens_out")
                panel.ms = found.get("ms")
                panel.measured = bool(found.get("measured"))
                panel.cost = found.get("cost")
                if panel.cost is None:
                    panel.cost = _cost(
                        str(found.get("model") or run.runner), panel.tokens_in, panel.tokens_out
                    )
                panel.status = "done"
            except Conflict as exc:
                panel.status, panel.error = "failed", exc.message
            except Exception as exc:  # the CLI, the disk: say what went wrong, never crash
                log.warning("bench run %s stopped", run.id, exc_info=True)
                panel.status, panel.error = "failed", f"It stopped: {exc}"
        run.status = "failed" if all(p.status == "failed" for p in run.panels) else "done"
        run.finished_at = iso(self.ws.rt.clock.now())

    def get(self, who: Principal, run_id: str) -> BenchRun:
        who.require("workspace.admin")
        found = self.runs.get(run_id)
        if found is None:
            raise NotFound(f"No bench run {run_id}: it ran before the server restarted.")
        return found
