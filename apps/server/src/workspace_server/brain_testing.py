"""Test the Brain (Settings > Test the Brain): where the tests are run and their results read.

The page reads one results contract (lab_contract.py). Its source is a Lab the owner connected
by folder, or, with none connected, the checks this app can run on its own Brain
(builtin_checks.py), written into the same shape. Either way the page only reads results and
starts and cancels runs: it writes no approvals, gates or labels, and a run never inherits the
app's settings (lab_runner.py).
"""

from __future__ import annotations

import json
import os
from typing import Any

from workspace_core.errors import Conflict, NotFound, ValidationFailed

from . import watch as watching
from .lab_contract import (
    ContractError,
    Lab,
    Metric,
    MissingResult,
    Results,
    Status,
    check_id,
    inside,
    open_lab,
)
from .lab_runner import LabRunner
from .settings import Settings

PILLARS = (
    ("retrieval", "Retrieval"),
    ("briefs", "Briefs"),
    ("management", "Context management"),
    ("agent", "Knowledge agent"),
)
# Which pillar a gate or metric belongs to when it does not say: by the start of its id.
PILLAR_PREFIXES = {
    "retrieval": "retrieval",
    "brief": "briefs",
    "briefs": "briefs",
    "management": "management",
    "ingestion": "management",
    "distillation": "management",
    "governance": "management",
    "updating": "management",
    "state": "management",
    "goals": "management",
    "agent": "agent",
}
TREND_LENGTH = 20


def pillar_of(item_id: str, explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    return PILLAR_PREFIXES.get(item_id.split(".", 1)[0].lower())


def metric_key(metric: Any) -> str:
    return f"{metric.id}:{metric.split}" if metric.split else metric.id


def to_domain(exc: ContractError) -> Exception:
    """A contract problem as the app's refusals: 404 for something that is not there."""
    if isinstance(exc, MissingResult):
        return NotFound(str(exc))
    return ValidationFailed(str(exc))


class TestTheBrain:
    __test__ = False  # not a test class, whatever pytest makes of its name

    def __init__(self, settings: Settings, ws: Any, *, builtin: Any = None) -> None:
        self.settings = settings
        self.ws = ws
        self.folder = os.path.join(settings.data_dir, "test-the-brain")
        self.runner = LabRunner(settings.data_dir)
        self.builtin = builtin

    # ----- what is connected
    @property
    def settings_file(self) -> str:
        return os.path.join(self.folder, "settings.json")

    def connected_folder(self) -> str | None:
        try:
            with open(self.settings_file, encoding="utf-8") as handle:
                found = json.load(handle).get("lab_folder")
        except (OSError, ValueError):
            return None
        return str(found) if found else None

    def _save(self, **values: Any) -> None:
        os.makedirs(self.folder, exist_ok=True)
        try:
            with open(self.settings_file, encoding="utf-8") as handle:
                current = json.load(handle)
        except (OSError, ValueError):
            current = {}
        current.update(values)
        temp = self.settings_file + ".tmp"
        with open(temp, "w", encoding="utf-8") as handle:
            json.dump(current, handle, indent=1)
        os.replace(temp, self.settings_file)

    def _own_places(self) -> list[str]:
        places = [self.settings.data_dir]
        if self.settings.brain_vault:
            places.append(self.settings.brain_vault)
        return places

    def connect(self, folder: str) -> dict[str, Any]:
        """Point the page at a Lab's folder, once. Stored here, on this machine."""
        try:
            lab = open_lab(os.path.expanduser(str(folder or "").strip()))
        except ContractError as exc:
            raise to_domain(exc) from None
        for place in self._own_places():
            if inside(place, lab.folder) or inside(lab.folder, place):
                raise ValidationFailed(
                    "That folder holds or sits inside this app's own data or Brain. "
                    "A Lab is a separate folder, so the live Brain is never under test.",
                    field="folder",
                )
        self._save(lab_folder=lab.folder)
        return self.state()

    def disconnect(self) -> dict[str, Any]:
        self._save(lab_folder=None)
        return self.state()

    def lab(self) -> Lab | None:
        """The connected Lab, checked again now; None when none is connected."""
        folder = self.connected_folder()
        if not folder:
            return None
        try:
            return open_lab(folder)
        except ContractError as exc:
            raise to_domain(exc) from None

    def results(self) -> Results | None:
        lab = self.lab()
        if lab:
            return Results(lab.results)
        return self.builtin.results() if self.builtin else None

    def _status(self, lab: Lab | None) -> Status | None:
        if lab:
            found = Results(lab.results).status()
            return found or self.runner.fetch_status(lab)
        return self.builtin.status() if self.builtin else None

    # ----- the page's state
    def state(self) -> dict[str, Any]:
        folder = self.connected_folder()
        out: dict[str, Any] = {
            "source": "lab" if folder else "builtin",
            "lab": None,
            "error": None,
            "status": None,
            "running": None,
        }
        lab: Lab | None = None
        if folder:
            try:
                lab = open_lab(folder)
                out["lab"] = {
                    "name": lab.name,
                    "folder": lab.folder,
                    "contract": lab.contract.contract,
                }
            except ContractError as exc:
                out["lab"] = {"name": None, "folder": folder, "contract": None}
                out["error"] = str(exc)
                return out
        try:
            status = self._status(lab)
        except ContractError as exc:
            out["error"] = str(exc)
            status = None
        if status is not None:
            out["status"] = dict(status.model_dump(), lock_holder=status.lock_holder())
        active = self.runner.active
        if active and active.state == "running":
            out["running"] = active.to_dict()
        elif self.builtin and not folder:
            out["running"] = self.builtin.running()
        if self.builtin:
            out["builtin"] = self.builtin.describe()
        return out

    # ----- reading
    def _results(self) -> Results:
        found = self.results()
        if found is None:
            raise NotFound("Nothing has been run yet.")
        return found

    def runs(self, kind: str | None = None) -> list[dict[str, Any]]:
        try:
            summaries = self._results().summaries(kind=kind)
        except ContractError as exc:
            raise to_domain(exc) from None
        return [
            {
                "run": s.run,
                "kind": s.kind,
                "valid": s.valid,
                "config": s.config,
                "cost": s.cost.model_dump(exclude_none=True),
                "metrics": len(s.metrics),
                "failing": len(s.failing_cases),
                "started": s.started,
                "ended": s.ended,
                "note": s.note,
            }
            for s in summaries
        ]

    def run(self, run: str) -> dict[str, Any]:
        try:
            return self._results().summary(run).model_dump(exclude_none=True)
        except ContractError as exc:
            raise to_domain(exc) from None

    def cases(self, run: str, **filters: Any) -> dict[str, Any]:
        try:
            return self._results().cases(run, **filters)
        except ContractError as exc:
            raise to_domain(exc) from None

    def case(self, run: str, case_id: str) -> dict[str, Any]:
        try:
            return self._results().case(run, case_id).full()
        except ContractError as exc:
            raise to_domain(exc) from None

    def gates(self) -> dict[str, Any]:
        """Every gate the status lists with its latest value, interval and verdict, and the
        values it had in earlier runs (oldest first) for its trend line."""
        results = self.results()
        if results is None:
            return {"gates": [], "run": None}
        try:
            status = self._status(self.lab())
            summaries = results.summaries(limit=60)
        except ContractError as exc:
            raise to_domain(exc) from None
        latest: dict[str, tuple[str, Metric]] = {}
        history: dict[str, list[float]] = {}
        for summary in summaries:  # newest first
            if not summary.valid:
                continue
            for metric in summary.metrics:
                if metric.gate and metric.value is not None:
                    latest.setdefault(metric.gate, (summary.run, metric))
                    history.setdefault(metric.gate, []).append(metric.value)
        rows = []
        for gate in status.gates if status else []:
            found = latest.get(gate.id)
            run = found[0] if found else None
            measured = found[1] if found else None
            rows.append(
                {
                    "id": gate.id,
                    "name": gate.name or gate.id,
                    "bar": gate.bar,
                    "kind": gate.kind,
                    "source": gate.source,
                    "pillar": pillar_of(gate.id, gate.pillar),
                    "value": measured.value if measured else None,
                    "ci": measured.ci if measured else None,
                    "n": measured.n if measured else None,
                    "met": measured.met if measured else None,
                    "met_confident": measured.met_confident if measured else None,
                    "run": run,
                    "trend": list(reversed(history.get(gate.id, [])))[-TREND_LENGTH:],
                }
            )
        return {"gates": rows, "run": summaries[0].run if summaries else None}

    def compare(self, a: str, b: str) -> dict[str, Any]:
        """Two runs side by side: the metrics that moved and the cases that flipped."""
        results = self._results()
        try:
            first, second = results.summary(a), results.summary(b)
            before = {metric_key(m): m for m in first.metrics}
            metrics = []
            for metric in second.metrics:
                key = metric_key(metric)
                old = before.get(key)
                delta = None
                if old and old.value is not None and metric.value is not None:
                    delta = round(metric.value - old.value, 6)
                metrics.append(
                    {
                        "id": key,
                        "gate": metric.gate,
                        "from": old.value if old else None,
                        "to": metric.value,
                        "delta": delta,
                        "met_from": old.met if old else None,
                        "met_to": metric.met,
                    }
                )
            was = {c["id"]: c["pass"] for c in results.cases(a, limit=500)["cases"]}
            flipped = [
                {"id": c["id"], "title": c["title"], "from": was[c["id"]], "to": c["pass"]}
                for c in results.cases(b, limit=500)["cases"]
                if c["id"] in was
                and was[c["id"]] is not None
                and c["pass"] is not None
                and was[c["id"]] != c["pass"]
            ]
        except ContractError as exc:
            raise to_domain(exc) from None
        return {
            "a": a,
            "b": b,
            "config": {"a": first.config, "b": second.config},
            "metrics": metrics,
            "flipped": flipped,
        }

    def overview(self) -> dict[str, Any]:
        """Is the Brain helping? A card per pillar, the Brain's effect, what is ready and what
        waits, label progress, and the report card's lines."""
        gates = self.gates()["gates"]
        pillars = []
        for pillar_id, name in PILLARS:
            rows = [g for g in gates if g["pillar"] == pillar_id]
            measured = [g for g in rows if g["value"] is not None]
            head = measured[0] if measured else None
            pillars.append(
                {
                    "id": pillar_id,
                    "name": name,
                    "total": len(rows),
                    "measured": len(measured),
                    "met": sum(1 for g in rows if g["met"] is True),
                    "confident": sum(1 for g in rows if g["met_confident"] is True),
                    "headline": {k: head[k] for k in ("id", "name", "value", "ci", "bar")}
                    if head
                    else None,
                    "trend": head["trend"] if head else [],
                }
            )
        results = self.results()
        summaries = results.summaries(limit=40) if results else []
        effect = None
        card = None
        for summary in summaries:
            if summary.valid and effect is None:
                for metric in summary.metrics:
                    if metric.id.lower() == "o1" or metric.id.lower().endswith("brain_effect"):
                        effect = dict(metric.model_dump(exclude_none=True), run=summary.run)
                        break
            if card is None and isinstance(summary.model_extra, dict):
                card = summary.model_extra.get("card")
        status = None
        try:
            status = self._status(self.lab())
        except ContractError:
            status = None
        last = summaries[0] if summaries else None
        return {
            "source": "lab" if self.connected_folder() else "builtin",
            "pillars": pillars,
            "effect": effect,
            "ready": status.ready if status else [],
            "labels": status.labels if status else {},
            "card": card,
            "last": {"run": last.run, "kind": last.kind, "ended": last.ended, "valid": last.valid}
            if last
            else None,
            "lock_holder": status.lock_holder() if status else None,
        }

    def watch(
        self, *, request: str | None = None, run: str | None = None, case: str | None = None
    ) -> dict[str, Any]:
        """One request drawn stage by stage. Typed, it runs read only on this app's Brain and
        records nothing. A saved case of a Lab is drawn from the Lab's own record; a case of
        the built-in checks is routed again, read only, with the labels it carried."""
        labels: dict[str, str] = {}
        if run and case:
            saved = self.case(run, case)
            for note in (saved.get("view") or {}).get("notes") or []:
                labels[str(note.get("id"))] = str(note.get("label") or "")
            if self.connected_folder():
                return dict(watching.from_record(saved), request=saved.get("request"), case=case)
            text = str(saved.get("request") or "")
        else:
            text = " ".join(str(request or "").split())
        if not text:
            raise ValidationFailed("Type a request, or pick a case.", field="request")
        if len(text) > 2000:
            raise ValidationFailed("Keep the request under 2,000 characters.", field="request")
        adapter = self.builtin.adapter if self.builtin else None
        if adapter is None:
            raise Conflict("This workspace has no Brain to read yet. Run contxt setup first.")
        try:
            found = watching.run_request(adapter, text)
        except ValueError as exc:
            raise ValidationFailed(str(exc), field="request") from None
        for note in found["notes"]:
            note["label"] = labels.get(note["id"], "")
        return dict(found, request=text, case=case, labels=labels)

    # ----- running
    def start(
        self, kind: str, suite: str | None, confirm: bool, request: str | None = None
    ) -> dict[str, Any]:
        lab = self.lab()
        if lab is None:
            if self.builtin is None:
                raise Conflict("Connect a Lab to run its tests.")
            return self.builtin.start(kind, suite, confirm, request)
        if request:
            raise ValidationFailed("A Lab run takes a run kind and a suite only.", field="request")
        try:
            status = self._status(lab)
        except ContractError as exc:
            raise to_domain(exc) from None
        return self.runner.start(lab, status, kind, suite=suite, confirm=confirm).to_dict()

    def cancel(self, run: str) -> dict[str, Any]:
        try:
            check_id(run, what="The run")
        except ContractError as exc:
            raise to_domain(exc) from None
        lab = self.lab()
        if lab is None:
            if self.builtin is None:
                raise NotFound("Nothing is running.")
            return self.builtin.cancel(run)
        return self.runner.cancel(lab, run)

    def live(self, after: int = 0) -> dict[str, Any]:
        """The run in progress (or the last one this app started) and its events past
        `after`. A run someone else started is followed through the Lab's own progress file."""
        if self.connected_folder() is None and self.builtin:
            return self.builtin.live(after)
        found = self.runner.live(after)
        active = found["active"]
        if active and active["state"] == "running":
            return found
        try:
            lab = self.lab()
            status = self._status(lab) if lab else None
            holder = status.lock_holder() if status else None
        except (ContractError, ValidationFailed, NotFound):
            holder = None
        if lab and holder and holder != "held":
            try:
                path = os.path.join(Results(lab.results).run_dir(holder), "progress.jsonl")
            except ContractError:
                return found
            seen = Results.progress(path, after)
            return {
                "active": {
                    "run": holder,
                    "state": "running",
                    "kind": None,
                    "ours": False,
                    "message": "Started outside this page; you can follow it and cancel it.",
                },
                **seen,
            }
        return found

    def close(self) -> None:
        self.runner.close()
        if self.builtin:
            self.builtin.close()
