"""The Test Bench after each distill (Release 1 plan, 15.6).

When a distill saves a Brain version, every suite marked "after distill" answers its tests in
full mode against that version and the grader scores each answer. A test whose packet is the
same as last time keeps its last answer and score, with no run. At most CAP tests run a day;
the rest wait for the next distill.

Each answer is compared with the test's baseline: its latest earlier answer that is not the
"after" of a drop still open or rolled back. It is a drop when the grade falls a point or more,
a criterion goes from met to missed, or an answer you gave a thumbs up is now graded 2 or under.
A drop raises one "Quality dropped" card in Catch up: the answers before and after, why, and
the likely causes (entries the distill added or changed that are in the new packet), with Roll
back (those entries as they were at the baseline's version), Edit (in the Brain) and Accept
(the new answer becomes the baseline).
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal
from workspace_core.errors import NotFound, ValidationFailed, WorkspaceError
from workspace_core.ids import new_id
from workspace_core.workspace import Workspace

from .benchsuites import GRADER, Suites
from .testbench import BenchRun, Panel

log = logging.getLogger(__name__)

CAP = 20  # test runs a day after distills
DAY = timedelta(hours=24)
BATCH = "bnight"
KEEP = 50  # drop cards kept
CAUSES = 5
SHOWN = 4000  # characters of each answer on the card
VERSION = re.compile(r"^v\d+")


def _best(scores: dict[str, Any]) -> dict[str, Any] | None:
    return scores.get("human") or scores.get("model")


def defaults() -> dict[str, Any]:
    """What counts as a drop, and the day's cap, unless the owner set otherwise."""
    return {"fall": 1, "met_to_missed": True, "liked_floor": 2, "daily_cap": CAP}


def reasons(
    before: dict[str, Any], after: dict[str, Any], rules: dict[str, Any] | None = None
) -> list[str]:
    """Why `after` (its scores by who gave them) is worse than `before`; [] when it is not.
    `rules` says what counts: the grade falling `fall` points or more, a criterion going from
    met to missed, an answer you liked now graded `liked_floor` or under."""
    rule = {**defaults(), **(rules or {})}
    new = after.get("model")
    if new is None:
        return []  # the grader gave no score: nothing to compare
    out = []
    old = before.get("model") or before.get("human")
    if old is not None and int(old["overall"]) - int(new["overall"]) >= int(rule["fall"]):
        out.append(f"The grade fell from {old['overall']} to {new['overall']}.")
    now = {str(c.get("criterion", "")).lower(): c.get("result") for c in new["criteria"] or []}
    for c in (before.get("model") or {}).get("criteria") or [] if rule["met_to_missed"] else []:
        name = str(c.get("criterion") or "")
        if c.get("result") == "met" and now.get(name.lower()) == "missed":
            out.append(f"{name}: met before, missed now.")
    liked = before.get("human")
    floor = int(rule["liked_floor"])
    if liked is not None and liked.get("thumbs") == "up" and int(new["overall"]) <= floor:
        out.append(f"You gave the last answer a thumbs up; this one is graded {new['overall']}.")
    return out


class Regression:
    def __init__(self, ws: Workspace, suites: Suites) -> None:
        self.ws = ws
        self.suites = suites

    # ---------------------------------------------------------------- the drop cards

    def rules(self, who: Principal | None = None) -> dict[str, Any]:
        """What counts as a drop and the day's cap, as the owner set them."""
        if who is not None:
            who.require("workspace.admin")
        with self.ws.rt.read() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
        stored = ((row["settings"] or {}).get("bench") or {}).get("rules") or {}
        return {**defaults(), **{k: v for k, v in stored.items() if k in defaults()}}

    def set_rules(self, who: Principal, changes: dict[str, Any]) -> dict[str, Any]:
        who.require("workspace.admin")
        rules = {**self.rules(), **{k: v for k, v in changes.items() if v is not None}}
        with self.ws.rt.write() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            settings["bench"] = {**dict(settings.get("bench") or {}), "rules": rules}
            tx.update(schema.workspaces, row, {"settings": settings})
            tx.emit(
                "bench.rules_changed",
                actor_id=who.actor_id,
                subject_type="workspace",
                subject_id=tx.workspace_id,
                data=rules,
            )
        return rules

    def _drops(self) -> list[dict[str, Any]]:
        with self.ws.rt.read() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
        return list(((row["settings"] or {}).get("bench") or {}).get("drops") or [])

    def _save(self, who: Principal, drops: list[dict[str, Any]], event: str, drop: dict) -> None:
        with self.ws.rt.write() as tx:
            row = tx.one(schema.workspaces, self.ws.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            settings["bench"] = {**dict(settings.get("bench") or {}), "drops": drops[:KEEP]}
            tx.update(schema.workspaces, row, {"settings": settings})
            tx.emit(
                event,
                actor_id=who.actor_id,
                subject_type="bench_drop",
                subject_id=drop["id"],
                data={k: drop[k] for k in ("suite", "test", "version", "status")},
            )

    def cards(self, who: Principal) -> list[dict[str, Any]]:
        """The open "Quality dropped" cards, newest first, for Catch up."""
        who.require("brain.read")
        return [d for d in self._drops() if d["status"] == "open"]

    def resolve(self, who: Principal, drop_id: str, action: str) -> dict[str, Any]:
        """Roll back the likely causes to the baseline's version, or accept the new answer."""
        who.require("workspace.admin")
        drops = self._drops()
        drop = next((d for d in drops if d["id"] == drop_id), None)
        if drop is None:
            raise NotFound(f"No quality drop {drop_id}.")
        if drop["status"] != "open":
            raise ValidationFailed("That drop was already decided.")
        if action == "roll-back":
            if not VERSION.match(drop["from_version"]):
                raise ValidationFailed("The answer before had no Brain version to roll back to.")
            ids = [c["id"] for c in drop["causes"]] or None
            found = self.ws.rt.brain.restore_version(drop["from_version"], ids=ids)
            made = found.get("version")
            drop["restored"] = str(made.get("name") if isinstance(made, dict) else made or "")
            drop["status"] = "rolled_back"
        elif action == "accept":
            drop["status"] = "accepted"
        else:
            raise ValidationFailed("Roll back or accept a drop.")
        drop["decided_at"] = iso(self.ws.rt.clock.now())
        self._save(who, drops, "bench.drop_decided", drop)
        return drop

    # ---------------------------------------------------------------- after a distill

    def after_distill(self, who: Principal, version: str) -> dict[str, Any]:
        """Run the after-distill suites against `version`: {ran, reused, skipped, drops,
        details}. Never raises: a broken test or the grader is logged and skipped."""
        drops = self._drops()
        held = {d["after"]["result_id"] for d in drops if d["status"] != "accepted"}
        rules = self.rules()
        cap = int(rules["daily_cap"])
        budget = cap - self._ran_today()
        batch = new_id(BATCH, self.ws.rt.clock.now())
        ran = reused = skipped = 0
        raised: list[dict[str, Any]] = []
        for suite in self.suites.suites(who):
            if not suite["after_distill"]:
                continue
            for test in suite["tests"]:
                if test.get("broken") or not str(test.get("request") or "").strip():
                    continue
                try:
                    run = self.suites.bench.prepare(
                        who,
                        str(test["request"]),
                        project=test.get("project") or None,
                        modes=["full"],
                        include=test.get("include") or None,
                        exclude=test.get("exclude") or None,
                        runner=str(test.get("runner") or "claude"),
                        model=test.get("model") or None,
                        batch=batch,
                        suite=suite["id"],
                        test=str(test["id"]),
                    )
                except WorkspaceError:
                    log.warning("after-distill test %s/%s", suite["id"], test["id"], exc_info=True)
                    continue
                run.brain_version = version
                panel = run.panels[0]
                base = self._baseline(suite["id"], str(test["id"]), held)
                if base is not None and base["row"]["packet_hash"] == panel.packet_hash:
                    self._reuse(base, batch, version)
                    reused += 1
                    continue
                if budget <= 0:
                    skipped += 1
                    continue
                budget -= 1
                ran += 1
                self._answer(who, run, test)
                if base is None or not panel.result_id or panel.status != "done":
                    continue
                after = self._result(panel.result_id)
                why = reasons(base["scores"], after["scores"], rules)
                if why:
                    raised.append(self._drop(suite, test, base, after, panel, version, why))
        if raised:
            drops = raised[::-1] + self._drops()
            for drop in raised:
                self._save(who, drops, "bench.quality_dropped", drop)
        details = []
        if ran or reused or skipped:
            details.append(
                f"Test Bench on {version}: {ran} ran, {reused} unchanged"
                + (
                    f", {skipped} left for the next distill (the day's {cap} are spent)"
                    if skipped
                    else ""
                )
                + "."
            )
        if raised:
            details.append(f"Quality dropped on {len(raised)}: see Catch up.")
        return {
            "ran": ran,
            "reused": reused,
            "skipped": skipped,
            "drops": len(raised),
            "details": details,
        }

    def _answer(self, who: Principal, run: BenchRun, test: dict[str, Any]) -> None:
        def graded(r: BenchRun, panel: Panel) -> None:
            if panel.status == "done":
                self.suites._grade(who, r, panel, test, GRADER)

        self.suites.bench.run(who, run, after=graded)

    def _ran_today(self) -> int:
        """Tests answered after distills in the last day (a kept answer is not a run)."""
        table = schema.bench_runs
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(table.c.included)
                .where(table.c.workspace_id == tx.workspace_id)
                .where(table.c.batch.like(f"{BATCH}%"))
                .where(table.c.created_at >= iso(self.ws.rt.clock.now() - DAY))
            )
        return sum(1 for r in rows if not (r["included"] or {}).get("reused_from"))

    def _scores(self, tx: Any, ids: list[str]) -> dict[str, dict[str, Any]]:
        return self.suites._scores(tx, ids)

    def _result(self, result_id: str) -> dict[str, Any]:
        with self.ws.rt.read() as tx:
            row = tx.one(schema.bench_runs, result_id, "bench answer")
            scores = self._scores(tx, [result_id]).get(result_id, {})
        return {"row": row, "scores": scores}

    def _baseline(self, suite: str, test: str, held: set[str]) -> dict[str, Any] | None:
        table = schema.bench_runs
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(table.c.workspace_id == tx.workspace_id)
                .where(table.c.suite == suite, table.c.test == test, table.c.mode == "full")
                .order_by(table.c.created_at.desc(), table.c.id.desc())
                .limit(50)
            )
            scores = self._scores(tx, [r["id"] for r in rows])
        for row in rows:
            if row["id"] not in held and _best(scores.get(row["id"], {})) is not None:
                return {"row": row, "scores": scores[row["id"]]}
        return None

    def _reuse(self, base: dict[str, Any], batch: str, version: str) -> None:
        """The baseline's answer and scores again, as this version's: its packet is the same."""
        row = base["row"]
        with self.ws.rt.write() as tx:
            made = tx.new_id("bres")
            tx.insert(
                schema.bench_runs,
                {
                    **{k: v for k, v in row.items() if k not in ("id", "created_at")},
                    "id": made,
                    "batch": batch,
                    "brain_version": version,
                    "included": {"reused_from": row["id"]},
                    "created_at": tx.now,
                },
            )
            for by, score in base["scores"].items():
                tx.insert(
                    schema.bench_scores,
                    {
                        **{k: v for k, v in score.items() if k not in ("id", "created_at")},
                        "id": tx.new_id("bscore"),
                        "run_id": made,
                        "by": by,
                        "created_at": tx.now,
                    },
                )

    def _drop(
        self,
        suite: dict[str, Any],
        test: dict[str, Any],
        base: dict[str, Any],
        after: dict[str, Any],
        panel: Panel,
        version: str,
        why: list[str],
    ) -> dict[str, Any]:
        before_version = str(base["row"]["brain_version"] or "").split("+")[0]
        name = str(test.get("name") or test["id"])
        return {
            "id": new_id("bdrop", self.ws.rt.clock.now()),
            "key": f"quality:{suite['id']}/{test['id']}:{version}",
            "type": "quality",
            "title": f"Quality dropped: {name}",
            "suite": suite["id"],
            "suite_name": suite["name"],
            "test": str(test["id"]),
            "test_name": name,
            "request": str(test.get("request") or ""),
            "version": version,
            "from_version": before_version,
            "reasons": why,
            "before": self._side(base),
            "after": self._side(after),
            "causes": self._causes(before_version, version, panel.packet),
            "status": "open",
            "raised_at": iso(self.ws.rt.clock.now()),
        }

    @staticmethod
    def _side(found: dict[str, Any]) -> dict[str, Any]:
        row, best = found["row"], _best(found["scores"]) or {}
        return {
            "result_id": row["id"],
            "brain_version": row["brain_version"],
            "overall": best.get("overall"),
            "criteria": best.get("criteria") or [],
            "by": best.get("by"),
            "output": str(row["output"] or "")[:SHOWN],
        }

    def _causes(self, before: str, after: str, packet: str) -> list[dict[str, Any]]:
        """Entries the distill added or changed that the new answer's packet holds."""
        if not VERSION.match(before) or before == after:
            return []
        try:
            diff = self.ws.rt.brain.version_diff(before, after)
        except WorkspaceError:
            return []
        text = packet.lower()
        out = []
        for change in ("added", "changed"):
            for entry in diff.get(change) or []:
                title = str(entry.get("title") or "")
                seen = str(entry.get("id") or "").lower() in text or (
                    len(title) >= 4 and title.lower() in text
                )
                if seen and entry.get("id"):
                    out.append(
                        {
                            "id": entry["id"],
                            "title": title,
                            "path": entry.get("path") or "",
                            "change": change,
                        }
                    )
        return out[:CAUSES]

    # ---------------------------------------------------------------- history

    def history(self, who: Principal, suite: str) -> dict[str, Any]:
        """A suite's after-distill answers and its average grade by Brain version."""
        who.require("workspace.admin")
        table = schema.bench_runs
        with self.ws.rt.read() as tx:
            rows = tx.rows(
                sa.select(table)
                .where(table.c.workspace_id == tx.workspace_id, table.c.suite == suite)
                .where(table.c.batch.like(f"{BATCH}%"))
                .order_by(table.c.created_at, table.c.id)
            )
            scores = self._scores(tx, [r["id"] for r in rows])
        by: dict[str, list[int]] = {}
        results = []
        for row in rows:
            best = _best(scores.get(row["id"], {}))
            results.append(
                {
                    "id": row["id"],
                    "test": row["test"],
                    "brain_version": row["brain_version"],
                    "reused": bool((row["included"] or {}).get("reused_from")),
                    "overall": best["overall"] if best else None,
                }
            )
            if best is not None:
                by.setdefault(row["brain_version"], []).append(int(best["overall"]))
        return {
            "suite": suite,
            "versions": [
                {"brain_version": v, "tests": len(xs), "average": round(sum(xs) / len(xs), 2)}
                for v, xs in by.items()
            ],
            "results": results,
        }
