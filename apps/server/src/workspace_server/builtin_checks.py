"""The checks this app can run on its own Brain, for when no Lab is connected.

Every Contxt user can test their own Brain with what the engine already has: `brain check`
(health), `brain report` (what context cost, how big briefs are), `brain eval` (their labeled
requests and the Brain's own eval cases) and "See the difference" (one request answered with
and without the Brain). Each run writes the same files a Lab does (the results contract,
`lab_contract.py`) into the app's own data folder, so the page reads both the same way.

Nothing here changes the Brain. Health is read only. The eval runs route on a second instance
of the Brain with a throwaway ledger (the app's own ledger and conversations are never
touched), and "See the difference" asks Claude Code on this computer, with no tools.

A part that needs a build step not yet merged says what it waits for, and lights up by itself
when the step is there (`ready_matrix`).
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import logging
import os
import platform
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

from workspace_core.errors import Conflict, ValidationFailed

from .lab_contract import Results, Status
from .lab_runner import Active

log = logging.getLogger(__name__)

SOURCE = "Checks on your own Brain"
WAITS_FOR_ENGINE = "Waits for the retrieval engine (build step 3b)"
MAX_REQUEST = 2000
KINDS: list[dict[str, Any]] = [
    {
        "id": "health",
        "name": "Health check",
        "covers": "Is your Brain well formed and current? The same check as brain check.",
        "paid": False,
    },
    {
        "id": "report",
        "name": "Report card",
        "covers": "What your AI's context cost by day, and how big briefs are by request type.",
        "paid": False,
    },
    {
        "id": "eval",
        "name": "Your labeled requests",
        "covers": "Does a brief carry the notes a request needs, and little else? Scored on "
        "the requests you labeled and on your Brain's own eval cases.",
        "paid": False,
    },
    {
        "id": "machine",
        "name": "Check this computer",
        "covers": "Reads this computer (memory, graphics), and which steps of the retrieval "
        "engine run here and which fall back to something simpler.",
        "paid": False,
    },
    {
        "id": "difference",
        "name": "See the difference",
        "covers": "One request answered twice by Claude Code on this computer, without and "
        "with your Brain, and what changed.",
        "paid": True,
        "estimate": {"calls": 3, "seconds": 120},
    },
]
GATES: list[dict[str, Any]] = [
    {
        "id": "health.problems",
        "name": "Problems in your Brain",
        "bar": {"op": "<=", "value": 0},
        "kind": "hard",
        "source": "brain check",
        "pillar": "management",
    },
    {
        "id": "health.warnings",
        "name": "Warnings to look at",
        "bar": {"op": "<=", "value": 0},
        "kind": "watch",
        "source": "brain check",
        "pillar": "management",
    },
    {
        "id": "machine.steps_named",
        "name": "Each step runs here or names its fallback",
        "bar": {"op": ">=", "value": 1.0},
        "kind": "hard",
        "source": "BL 5.11.15",
        "pillar": "retrieval",
    },
    {
        "id": "eval.must_recall.holdout",
        "name": "Needed-note recall, held out",
        "bar": {"op": ">=", "value": 0.9},
        "kind": "hard",
        "source": "BL 5.9",
        "pillar": "retrieval",
    },
    {
        "id": "eval.noise_share",
        "name": "Noise share of brief tokens",
        "bar": {"op": "<=", "value": 0.15},
        "kind": "hard",
        "source": "BL 5.9",
        "pillar": "briefs",
    },
]


class Stopped(Exception):
    """The run was cancelled while it worked."""


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def stamp(moment: dt.datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1, ensure_ascii=False, default=str)
    os.replace(temp, path)


def met(op: str, value: float, bar: float) -> bool:
    return value >= bar if op == ">=" else value <= bar


def engine_ready() -> bool:
    """Whether the local retrieval engine (build step 3b) is part of this install."""
    return importlib.util.find_spec("brainkit.engine") is not None


def machine_ready() -> bool:
    """Whether the engine's machine check (this computer, its setup, its models) is here."""
    return importlib.util.find_spec("brainkit.machine") is not None


def machine_overview() -> dict[str, Any] | None:
    """What Settings > On this computer > Local models shows, or None when the engine's
    machine module is not part of this install or cannot read this computer."""
    if not machine_ready():
        return None
    try:
        from brainkit import machine

        found: dict[str, Any] = machine.overview()
        return found
    except Exception:  # the lock, the disk, a model service: say nothing rather than crash
        log.warning("could not read this computer's model settings", exc_info=True)
        return None


def qualification(over: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Each retrieval step on this computer: whether it runs here or falls back to something
    simpler (and what), its speed against the budget and the memory its model needs. Built from
    the engine's machine overview (brain-logic plan 5.11.15); empty when there is none."""
    if not over:
        return []
    roles = {r["role"]: r for r in over.get("roles") or []}
    engine = over.get("engine") or {}
    running = bool(engine.get("ready"))
    why_not = str(engine.get("reason") or "the local model service is not running")
    budget = over.get("budget_ms") or {}
    named = [str(w) for w in over.get("fallbacks") or []]

    def chosen(role: str) -> tuple[str, dict[str, Any]]:
        found = roles.get(role) or {}
        model = found.get("model")
        option: dict[str, Any] = next(
            (o for o in found.get("options") or [] if o.get("name") == model), {}
        )
        return (str(model) if model else "none"), option

    def row(
        step: str, role: str, budget_key: str | None, runs: bool, instead: str
    ) -> dict[str, Any]:
        model, option = chosen(role)
        measured = option.get("measured") or {}
        ram = option.get("ram_gb")
        return {
            "step": step,
            "model": model,
            "state": "on" if runs else "fallback",
            "fallback": "" if runs else instead,
            "speed_ms": measured.get("speed_ms"),
            "budget_ms": budget.get(budget_key) if budget_key else None,
            "peak_ram_mb": int(float(ram) * 1000) if ram else None,
        }

    def said(step_words: str, default: str) -> str:
        found = next((w for w in named if step_words in w), "")
        return found or default

    simple = "the router's own scoring decides."
    gate_off = said("for the gate", f"{why_not}: {simple}")
    second_off = said("for the second pass", f"{why_not}: this step is skipped.")
    agent_runs = bool(engine.get("agent"))
    claude = bool(over.get("agent_claude_code"))
    _model, embed_option = chosen("embed")
    return [
        row(
            "Matching by meaning",
            "embed",
            None,
            bool(embed_option.get("downloaded")),
            "Matching by words only until its model is downloaded.",
        ),
        row("The relevance cut", "rerank", "cut", running, f"{why_not}: {simple}"),
        row(
            "The gate", "decide", "gate", running and not named_has(named, "for the gate"), gate_off
        ),
        row(
            "The second pass",
            "decide",
            "second_pass",
            running and not named_has(named, "for the second pass"),
            second_off,
        ),
        row(
            "The knowledge agent",
            "agent",
            None,
            agent_runs,
            "Claude Code on this computer does its work."
            if claude
            else "The knowledge agent is off.",
        ),
    ]


def named_has(named: list[str], words: str) -> bool:
    return any(words in w for w in named)


class BuiltinChecks:
    def __init__(self, data_dir: str, ws: Any, adapter: Any, differences: Any) -> None:
        self.root = os.path.join(data_dir, "test-the-brain", "builtin", "results")
        self.ws = ws
        self.adapter = adapter
        self.differences = differences
        self.active: Active | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._cancel = threading.Event()

    # ----- what exists
    def results(self) -> Results:
        os.makedirs(self.root, exist_ok=True)
        return Results(self.root)

    def labels(self) -> dict[str, Any]:
        if self.adapter is None:
            return {"labeled": 0, "total": 0}
        try:
            found = self.adapter.eval_status()
        except (OSError, ValueError, KeyError):
            return {"labeled": 0, "total": 0}
        return {
            "labeled": found.get("labeled", 0),
            "total": found.get("cases", 0),
            "held_out": found.get("held_out", 0),
        }

    def ready_matrix(self) -> list[dict[str, Any]]:
        """Each part of the page and whether it can run now, or what it waits for."""
        if self.adapter is None:
            have = {
                "state": "waiting_step",
                "note": "This workspace has no Brain yet. Run contxt setup.",
            }
            return [dict(have, suite=k["name"], setup="this computer") for k in KINDS]
        labeled = self.labels()["labeled"]
        engine = engine_ready()
        rows: list[dict[str, Any]] = [
            {"suite": "Health check", "setup": "this computer", "state": "ready"},
            {"suite": "Report card", "setup": "this computer", "state": "ready"},
            {
                "suite": "Your labeled requests",
                "setup": "this computer",
                "state": "ready" if labeled else "waiting_labels",
                "note": "" if labeled else "Label some of your requests in Activity first.",
            },
            {"suite": "See the difference", "setup": "this computer", "state": "ready"},
            {
                "suite": "Scores for each layer and the why view",
                "setup": "this computer",
                "state": "ready" if engine else "waiting_step",
                "note": "" if engine else WAITS_FOR_ENGINE,
            },
            {
                "suite": "The machine check",
                "setup": "this computer",
                "state": "ready" if machine_ready() else "waiting_step",
                "note": "" if machine_ready() else WAITS_FOR_ENGINE,
            },
        ]
        return rows

    def status(self) -> Status:
        holder = self.active.run if self.active and self.active.state == "running" else None
        last = self._last_runs()
        kinds = []
        for kind in KINDS:
            row = dict(kind)
            if kind["id"] in last:
                row["last"] = last[kind["id"]]
            kinds.append(row)
        found = Status.model_validate(
            {
                "updated": stamp(now()),
                "machine_setup": "this computer",
                "brain": self._brain_name(),
                "run_kinds": kinds,
                "ready": self.ready_matrix(),
                "gates": GATES,
                "labels": self.labels(),
                "qualification": qualification(machine_overview()),
                "lock": {"run": holder} if holder else None,
            }
        )
        return found

    def _last_runs(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for summary in self.results().summaries(limit=40):
            out.setdefault(
                summary.kind,
                {
                    "run": summary.run,
                    "at": summary.ended,
                    "seconds": summary.cost.seconds,
                    "usd": summary.cost.usd_estimate,
                },
            )
        return out

    def _brain_name(self) -> str:
        if self.adapter is None:
            return "none"
        return os.path.basename(os.path.dirname(self.adapter.vault)) or "your Brain"

    def describe(self) -> dict[str, Any]:
        """What the page says about this source: its name, what waits, this computer."""
        matching: dict[str, Any] = {}
        if self.adapter is not None:
            try:
                matching = dict(self.adapter.models().get("matching") or {})
            except (OSError, ValueError, KeyError, AttributeError):
                matching = {}
        return {
            "name": SOURCE,
            "reads_brain": self._brain_name(),
            "waits": [r for r in self.ready_matrix() if r["state"] != "ready"],
            "computer": {
                "system": f"{platform.system()} {platform.release()}",
                "cpus": os.cpu_count(),
                "python": platform.python_version(),
                "matching": matching,
                "engine": engine_ready(),
                "machine": self._machine_line(),
            },
        }

    @staticmethod
    def _machine_line() -> dict[str, Any] | None:
        over = machine_overview()
        if not over:
            return None
        machine = over.get("machine") or {}
        engine = over.get("engine") or {}
        return {
            "setup": over.get("setup_label"),
            "ram_gb": machine.get("ram_gb"),
            "gpu": machine.get("gpu") or "none found",
            "models_ram_gb": over.get("ram_in_use_gb"),
            "checked_at": over.get("checked_at"),
            "engine_running": bool(engine.get("ready")),
            "engine_reason": engine.get("reason") or "",
        }

    def running(self) -> dict[str, Any] | None:
        active = self.active
        return active.to_dict() if active and active.state == "running" else None

    # ----- running
    def start(
        self, kind: str, suite: str | None, confirm: bool, request: str | None = None
    ) -> dict[str, Any]:
        listed = next((k for k in KINDS if k["id"] == kind), None)
        if listed is None:
            names = ", ".join(k["id"] for k in KINDS)
            raise ValidationFailed(
                f"There is no check called {kind}. Your Brain's checks are: {names}.", field="kind"
            )
        if self.adapter is None:
            raise Conflict("This workspace has no Brain to check. Run contxt setup first.")
        text = " ".join(str(request or "").split())
        if len(text) > MAX_REQUEST:
            raise ValidationFailed(f"Keep the request under {MAX_REQUEST:,} characters.")
        with self._lock:
            if (self.active and self.active.state == "running") or (
                self._thread and self._thread.is_alive()
            ):
                raise Conflict("A check is already running. Wait for it, or cancel it.")
            if listed["paid"] and not confirm:
                raise Conflict(
                    f"{listed['name']} uses your Claude Code plan. Press again to run it.",
                    needs_confirmation=True,
                    estimate=listed.get("estimate"),
                    kind=kind,
                )
            moment = now()
            run = f"{moment.strftime('%Y-%m-%dT%H-%M')}_{kind}_builtin_{secrets.token_hex(3)}"
            folder = os.path.join(self.root, "runs", run)
            os.makedirs(folder, exist_ok=True)
            active = Active(
                ticket=run,
                kind=kind,
                suite=suite,
                progress_file=os.path.join(folder, "progress.jsonl"),
                started_at=stamp(moment),
                run=run,
            )
            self.active = active
            self._cancel.clear()
            self._thread = threading.Thread(
                target=self._execute, args=(active, text), daemon=True, name=f"builtin-{kind}"
            )
            self._thread.start()
        return active.to_dict()

    def cancel(self, run: str) -> dict[str, Any]:
        active = self.active
        if not active or active.run != run or active.state != "running":
            raise Conflict("That check is not running.")
        self._cancel.set()
        active.cancel_asked = True
        active.state = "cancelled"
        active.message = "Stopped on request. Work already started finishes in the background."
        active.ended_at = stamp(now())
        return active.to_dict()

    def close(self) -> None:
        self._cancel.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

    def live(self, after: int = 0) -> dict[str, Any]:
        active = self.active
        if active is None:
            return {"active": None, "events": [], "next": after}
        return {"active": active.to_dict(), **Results.progress(active.progress_file, after)}

    # ----- the work
    def _emit(self, active: Active, event: str, **data: Any) -> None:
        line = {"event": event, "at": stamp(now()), "run": active.run, **data}
        with open(active.progress_file, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")

    def _check_stop(self) -> None:
        if self._cancel.is_set():
            raise Stopped

    def _execute(self, active: Active, request: str) -> None:
        started = time.monotonic()
        emit: Callable[..., None] = lambda event, **data: self._emit(active, event, **data)  # noqa: E731
        try:
            emit("start", kind=active.kind)
            emit(
                "suite_start", suite=active.kind, total=1, message="Working on a copy of the read."
            )
            work = getattr(self, f"_run_{active.kind}")
            metrics, cases, extra = work(emit, request)
            self._check_stop()
            seconds = round(time.monotonic() - started, 1)
            failing = [c for c in cases if c.get("pass") is False]
            summary: dict[str, Any] = {
                "run": active.run,
                "kind": active.kind,
                "started": active.started_at,
                "ended": stamp(now()),
                "config": {
                    "source": SOURCE,
                    "machine_setup": "this computer",
                    "engine_ref": self._engine_ref(),
                    "brain": self._brain_name(),
                },
                "valid": True,
                "metrics": metrics,
                "cost": {
                    "usd_estimate": extra.pop("usd", 0.0),
                    "tokens": 0,
                    "seconds": seconds,
                },
                "failing_cases": [
                    {"id": c["id"], "title": c["title"], "why": c.get("why", "")} for c in failing
                ],
                **extra,
            }
            folder = os.path.dirname(active.progress_file)
            with open(os.path.join(folder, "cases.jsonl"), "w", encoding="utf-8") as handle:
                for case in cases:
                    handle.write(json.dumps(case, ensure_ascii=False, default=str) + "\n")
            write_json(os.path.join(folder, "summary.json"), summary)
            for case in cases[:200]:
                emit("case_done", suite=active.kind, case=case["id"])
            emit(
                "suite_end",
                suite=active.kind,
                done=len(cases),
                total=len(cases),
                failures=len(failing),
            )
            self._finish(active, "done", "")
            emit("end", done=len(cases), failures=len(failing))
        except Stopped:
            emit("cancelled", message="Stopped on request.")
            self._finish(active, "cancelled", "Stopped on request.")
        except (Conflict, ValidationFailed) as exc:
            emit("failure", message=exc.message)
            self._finish(active, "failed", exc.message)
        except Exception as exc:  # the engine, the disk, Claude Code: say what went wrong
            log.warning("built-in check %s stopped", active.kind, exc_info=True)
            emit("failure", message=str(exc))
            self._finish(active, "failed", f"The check stopped: {exc}")

    def _finish(self, active: Active, state: str, message: str) -> None:
        with self._lock:
            if active.state == "running":
                active.state = state
                active.message = message
                active.ended_at = stamp(now())
                active.exit_code = 0 if state == "done" else 1

    @staticmethod
    def _engine_ref() -> str:
        try:
            from brainkit import runtime

            return str(runtime.STARTED_WITH)
        except (ImportError, AttributeError):
            return "unknown"

    # ----- the checks. Each returns (metrics, cases, extra summary fields)
    def _run_health(self, emit: Callable[..., None], _request: str):  # type: ignore[no-untyped-def]
        from brainkit import health

        found = health.report(self.adapter.brain)
        data = found.data
        problems, warnings = list(data["problems"]), list(data["warnings"])
        cases: list[dict[str, Any]] = [
            {
                "id": f"HC-problem-{i + 1}",
                "gates": ["health.problems"],
                "suite": "health",
                "kind": "table",
                "title": text[:90],
                "pass": False,
                "why": text[:200],
                "measures": {},
                "view": {
                    "columns": ["What", "Detail"],
                    "rows": [{"label": "Problem", "expected": "none", "got": text, "pass": False}],
                },
            }
            for i, text in enumerate(problems)
        ]
        cases += [
            {
                "id": f"HC-warning-{i + 1}",
                "gates": ["health.warnings"],
                "suite": "health",
                "kind": "table",
                "title": text[:90],
                "pass": None,
                "measures": {},
                "view": {
                    "columns": ["What", "Detail"],
                    "rows": [{"label": "Warning", "expected": "none", "got": text, "pass": None}],
                },
            }
            for i, text in enumerate(warnings)
        ]
        cases.append(
            {
                "id": "HC-facts",
                "suite": "health",
                "kind": "table",
                "title": "What the check found out",
                "pass": not problems,
                "measures": {"problems": len(problems), "warnings": len(warnings)},
                "view": {
                    "columns": ["Fact", ""],
                    "rows": [
                        {"label": fact, "expected": "", "got": "", "pass": True}
                        for fact in data["facts"]
                    ],
                },
            }
        )
        metrics = [
            {
                "id": "health.problems",
                "value": float(len(problems)),
                "gate": "health.problems",
                "met": not problems,
                "met_confident": not problems,
                "pillar": "management",
            },
            {
                "id": "health.warnings",
                "value": float(len(warnings)),
                "gate": "health.warnings",
                "met": not warnings,
                "met_confident": not warnings,
                "pillar": "management",
            },
            {"id": "health.kernel_tokens", "value": float(data["kernel_tokens"])},
        ]
        return metrics, cases, {"note": "Read only: nothing in your Brain was changed."}

    def _run_report(self, emit: Callable[..., None], _request: str):  # type: ignore[no-untyped-def]
        found = self.adapter.report(days=7, quality=False)
        self._check_stop()
        spend = found.get("spend") or {}
        days = spend.get("days") or []
        metrics: list[dict[str, Any]] = [
            {"id": "report.per_day_usd", "value": float(found.get("per_day_usd") or 0.0)}
        ]
        for kind, tokens in (found.get("brief_tokens_by_type") or {}).items():
            metrics.append({"id": f"report.brief_tokens.{kind}", "value": float(tokens)})
        rows = [
            {
                "label": d["day"],
                "expected": "",
                "got": f"${d['total_usd']:.4f}",
                "pass": True,
            }
            for d in days
        ]
        cases = [
            {
                "id": "RP-days",
                "suite": "report",
                "kind": "table",
                "title": "Cost by day, last 7 days",
                "pass": True,
                "measures": {"per_day_usd": found.get("per_day_usd")},
                "view": {"columns": ["Day", "Estimated cost"], "rows": rows},
            }
        ]
        card = {
            "days": found.get("days"),
            "per_day_usd": found.get("per_day_usd"),
            "brief_tokens_by_type": found.get("brief_tokens_by_type") or {},
            "by_day": [
                {
                    "day": d["day"],
                    "total_usd": d["total_usd"],
                    "lines": {k: v.get("usd") for k, v in (d.get("lines") or {}).items()},
                }
                for d in days
            ],
            "text": found.get("text", ""),
        }
        return metrics, cases, {"card": card}

    def _run_eval(self, emit: Callable[..., None], _request: str):  # type: ignore[no-untyped-def]
        from brainkit import evalset, evaluate
        from brainkit.api import Brain

        other = Brain(
            self.adapter.vault,
            embeddings=self.adapter.brain.embedder is not None,
            local_models=True,
        )
        results: list[tuple[str, str, dict[str, Any], dict[str, dict[str, Any]]]] = []
        try:
            emit("progress", message="Scoring your labeled requests.")
            private = evalset.run(other)
            if private.get("all"):
                spec = {c["id"]: c for c in evalset.load(other)["cases"]}
                results.append(("eval", "Your labeled requests", private, spec))
            self._check_stop()
            public_path = os.path.join(other.vault.root, "eval.json")
            if os.path.isfile(public_path):
                emit("progress", message="Scoring your Brain's own eval cases.")
                public = evaluate.run(other, public_path)
                with open(public_path, encoding="utf-8") as handle:
                    spec = {c["id"]: c for c in json.load(handle).get("cases") or []}
                results.append(("evalcases", "Your Brain's eval cases", public, spec))
            state = other.state()
            titles = {n.id: n.title for n in state.index.notes.values()}
        finally:
            other.close()
        if not results:
            raise ValidationFailed(
                "There is nothing to score yet. Label some of your requests in Activity, "
                "or add an eval.json to your Brain."
            )
        metrics: list[dict[str, Any]] = []
        cases: list[dict[str, Any]] = []
        for prefix, label, result, spec in results:
            for split in ("tuning", "holdout", "all"):
                agg = result[split]
                if not agg["cases"]:
                    continue
                for name in ("must_recall", "precision", "noise_share"):
                    if name not in agg:
                        continue
                    value = float(agg[name])
                    row: dict[str, Any] = {
                        "id": f"{prefix}.{name}",
                        "split": split,
                        "n": agg["cases"],
                        "value": value,
                    }
                    if prefix == "eval" and split == "holdout" and name == "must_recall":
                        ok = met(">=", value, 0.9)
                        row.update(gate="eval.must_recall.holdout")
                        row.update(met=ok, met_confident=ok and agg["cases"] >= 20)
                    if prefix == "eval" and split == "all" and name == "noise_share":
                        ok = met("<=", value, 0.15)
                        row.update(
                            gate="eval.noise_share", met=ok, met_confident=ok and agg["cases"] >= 20
                        )
                    metrics.append(row)
            for row in result["rows"]:
                cases.append(self._eval_case(prefix, label, row, spec.get(row["id"]) or {}, titles))
        return (
            metrics,
            cases,
            {"note": "Scored on a second copy of your Brain; your own ledger was not used."},
        )

    @staticmethod
    def _eval_case(
        prefix: str,
        label: str,
        row: dict[str, Any],
        spec: dict[str, Any],
        titles: dict[str, str],
    ) -> dict[str, Any]:
        must = {i for group in spec.get("must") or [] for i in group}
        useful = set(spec.get("useful") or [])
        noise = set(row.get("noise") or [])
        notes: list[dict[str, Any]] = []
        for note_id in row.get("notes") or []:
            kind = (
                "noise"
                if note_id in noise
                else "needed_delivered"
                if note_id in must
                else "useful"
                if note_id in useful
                else "unlabeled"
            )
            notes.append(
                {
                    "id": note_id,
                    "title": titles.get(note_id, note_id),
                    "label": kind,
                    "form": "body",
                    "scores": {},
                    "why": "",
                }
            )
        for group in row.get("missed") or []:
            first = group[0] if group else ""
            notes.append(
                {
                    "id": first,
                    "title": titles.get(first, first),
                    "label": "needed_missed",
                    "form": "none",
                    "scores": {},
                    "why": "The brief did not carry it"
                    + (" or any of its alternatives." if len(group) > 1 else "."),
                }
            )
        ok = not row.get("missed") and not noise and not row.get("problems")
        must_count = row.get("must") or 0
        return {
            "id": f"{prefix}-{row['id']}",
            "suite": label,
            "gates": ["eval.must_recall.holdout", "eval.noise_share"] if prefix == "eval" else [],
            "kind": "retrieval",
            "title": " ".join(str(row.get("request") or "").split())[:90],
            "sensitive": False,
            "pass": bool(ok),
            "why": "; ".join(row.get("problems") or [])
            or ("missed a needed note" if row.get("missed") else ""),
            "measures": {
                "needed_recall": round(row["hits"] / must_count, 3) if must_count else None,
                "tokens": row.get("tokens"),
                "ms": row.get("ms"),
                "held_out": bool(row.get("holdout")),
            },
            "request": row.get("request"),
            "view": {
                "request": row.get("request"),
                "mode": row.get("mode"),
                "notes": notes,
                "standards": [
                    {"id": "problems", "name": p, "pass": False} for p in row.get("problems") or []
                ],
                "waits": ""
                if engine_ready()
                else "Scores for each layer: " + WAITS_FOR_ENGINE.lower(),
            },
        }

    def _run_difference(self, emit: Callable[..., None], request: str):  # type: ignore[no-untyped-def]
        owner = self.ws.owner()
        text = request
        if not text:
            latest = self.adapter.requests(limit=1).get("requests") or []
            text = str(latest[0]["request"]) if latest else ""
        if not text:
            raise ValidationFailed("Type the request to compare.")
        job = self.differences.start(owner, text)
        seen = ""
        while job.status == "running":
            self._check_stop()
            if job.step != seen:
                seen = job.step
                emit(
                    "progress",
                    message={
                        "without": "Asking without your Brain.",
                        "with": "Asking with your Brain.",
                        "differences": "Comparing the two answers.",
                    }.get(seen, seen),
                )
            time.sleep(0.5)
        if job.status != "done":
            raise Conflict(job.error or "The comparison did not finish.")
        points = [
            {"text": d["what"], "with": True, "without": False, "item": d.get("item", "")}
            for d in job.differences
        ]
        case = {
            "id": "DF-1",
            "suite": "difference",
            "kind": "outcome",
            "title": " ".join(text.split())[:90],
            "sensitive": False,
            "pass": None,
            "measures": {"changes": len(points), "context_tokens": job.tokens},
            "request": text,
            "view": {
                "request": text,
                "with": {"text": job.with_context},
                "without": {"text": job.without},
                "key_points": points,
                "violations": [],
                "pieces": job.pieces,
            },
        }
        metrics = [
            {"id": "difference.changes", "n": 1, "value": float(len(points))},
            {"id": "difference.context_tokens", "n": 1, "value": float(job.tokens)},
        ]
        return (
            metrics,
            [case],
            {"note": "One request, answered twice with Claude Code on this computer."},
        )

    def _run_machine(self, emit: Callable[..., None], _request: str):  # type: ignore[no-untyped-def]
        """Read this computer again and say which engine steps run here. It keeps what it found
        in this computer's own model settings (the same as Local models' "check again"), never
        in a Brain. With the model service running, it also times the reranker."""
        if not machine_ready():
            raise Conflict(f"{WAITS_FOR_ENGINE}. There is no machine check in this install yet.")
        from brainkit import machine, models_client

        settings = machine.check()
        self._check_stop()
        speed: dict[str, Any] = {}
        found = models_client.status()
        if found.ready:
            emit("progress", message="Timing the reranker on this computer.")
            speed = machine.check_speed(found)
        over = machine_overview()
        rows = qualification(over)
        found_machine = settings.get("machine") or {}
        facts = [
            ("Memory", f"{found_machine.get('ram_gb')} GB"),
            ("Graphics", found_machine.get("gpu") or "none found"),
            ("Setup it gets", (over or {}).get("setup_label") or settings.get("setup") or ""),
            ("Models in memory at once", f"{(over or {}).get('ram_in_use_gb')} GB"),
            ("Local model service", "running" if found.ready else f"not running: {found.reason}"),
        ]
        cases: list[dict[str, Any]] = [
            {
                "id": "MC-computer",
                "suite": "machine",
                "kind": "table",
                "title": "What was found on this computer",
                "pass": True,
                "gates": [],
                "measures": {},
                "view": {
                    "columns": ["What", "Found"],
                    "rows": [
                        {"label": k, "expected": "", "got": str(v), "pass": True} for k, v in facts
                    ],
                },
            }
        ]
        for index, step in enumerate(rows):
            runs = step["state"] == "on"
            slow = (
                step["speed_ms"] is not None
                and step["budget_ms"] is not None
                and step["speed_ms"] > step["budget_ms"]
            )
            cases.append(
                {
                    "id": f"MC-step-{index + 1}",
                    "suite": "machine",
                    "kind": "table",
                    "title": f"{step['step']}: " + ("runs here" if runs else "falls back"),
                    "pass": None if not runs else not slow,
                    "gates": ["machine.steps_named"],
                    "why": step["fallback"],
                    "measures": {"speed_ms": step["speed_ms"], "budget_ms": step["budget_ms"]},
                    "view": {
                        "columns": ["What", "Detail"],
                        "rows": [
                            {"label": "Model", "expected": "", "got": step["model"], "pass": True},
                            {
                                "label": "Here",
                                "expected": "runs, or names what runs instead",
                                "got": "runs here" if runs else step["fallback"],
                                "pass": True,
                            },
                            {
                                "label": "Speed",
                                "expected": f"within {step['budget_ms']} ms"
                                if step["budget_ms"]
                                else "",
                                "got": f"{step['speed_ms']} ms"
                                if step["speed_ms"] is not None
                                else "not measured yet",
                                "pass": not slow,
                            },
                        ],
                    },
                }
            )
        named = sum(1 for s in rows if s["state"] == "on" or s["fallback"])
        share = named / len(rows) if rows else 0.0
        metrics: list[dict[str, Any]] = [
            {
                "id": "machine.steps_named",
                "n": len(rows),
                "value": share,
                "gate": "machine.steps_named",
                "met": bool(rows) and share >= 1.0,
                "met_confident": bool(rows) and share >= 1.0,
                "pillar": "retrieval",
            },
            {"id": "machine.ram_gb", "value": float(found_machine.get("ram_gb") or 0)},
            {
                "id": "machine.steps_running",
                "n": len(rows),
                "value": float(sum(1 for s in rows if s["state"] == "on")),
            },
        ]
        extra: dict[str, Any] = {"note": "Read this computer; nothing in your Brain was changed."}
        if speed:
            extra["speed"] = speed
        return metrics, cases, extra
