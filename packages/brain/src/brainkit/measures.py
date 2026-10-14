"""What a computed goal measure reads (goals plan 4.1 and 4.2).

Each signal is pure code over what the Brain already holds, with a plain-English line, and it
shows its value at once when picked ("Right now: 6"). Signals that need what later steps build
(sheets, tasks, the private eval set) are listed and say what they wait for.

A measure is stored on a goal note as JSON (`measure`):
    {"kind": "at_most", "signal": "notes_overdue", "params": {}, "target": 0, "unit": "notes"}
Its kinds: you enter it, keep at or under, keep at or above, reach by a date, do it every
period, a trend, or your judgment.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any, Callable

from . import util

KINDS = ("enter", "at_most", "at_least", "reach_by", "every_period", "trend", "judgment")
KIND_WORDS = {"enter": "You enter it", "at_most": "Keep at or under", "at_least":
              "Keep at or above", "reach_by": "Reach by a date", "every_period":
              "Do it every period", "trend": "A trend", "judgment": "Your judgment"}


@dataclass
class Signal:
    name: str
    label: str              # "Much-used notes past their review date"
    compute: Callable[..., float | None] | None
    params: dict = field(default_factory=dict)
    waits_for: str = ""     # what a signal not available yet needs

    def describe(self, params: dict | None = None) -> str:
        values = dict(self.params, **(params or {}))
        try:
            return self.label.format(**values)
        except (KeyError, IndexError, ValueError):
            return self.label


def _older_than(stamp: str, days: int) -> bool:
    found = util.day_of(stamp)
    return bool(found) and (util.today_date() - found).days > int(days)


def _notes_overdue(brain, st, params) -> float:
    from . import agent
    return float(len(agent._freshness(brain, st)))


def _waiting(brain, st, params) -> float:
    days = int(params.get("days", 7))
    return float(sum(1 for p in st.snapshot.proposals.values()
                     if _older_than(p.created, days)))


def _unanswered(brain, st, params) -> float:
    days = int(params.get("days", 7))
    try:
        rows = brain.gaps(days=90).data.get("gaps") or []
    except Exception:  # an unreadable ledger has no gaps to count
        rows = []
    return float(sum(1 for r in rows if _older_than(str(r.get("at") or ""), days)))


def _quiet_projects(brain, st, params) -> float:
    from . import agent
    days = int(params.get("days", 14))
    count = 0
    for focus in st.index.focuses.values():
        if not focus.active or focus.status.strip().lower() in agent.RESTING:
            continue
        updated = str(focus.current().get("updated") or "")
        if not updated or _older_than(updated, days):
            count += 1
    return float(count)


def _sheet_column(brain, st, params) -> float | None:
    """A column of a State sheet: its latest value, sum, count, average, or the rows in one
    status (`agg`: latest, sum, count, average, or status:<value>)."""
    from . import formulas, state
    sheet_id, column = str(params.get("sheet") or ""), str(params.get("column") or "")
    found = state.sheet(brain, sheet_id)
    if found is None or found.column(column) is None:
        return None
    current = state.rows(brain, sheet_id)
    agg = str(params.get("agg") or "latest")
    is_computed = found.column(column).computed

    def value(row):
        return row.computed.get(column) if is_computed else row.value(column)

    if agg.startswith("status:"):
        wanted = agg.split(":", 1)[1].lower()
        return float(sum(1 for r in current if str(value(r) or "").lower() == wanted))
    if agg == "count":
        return float(sum(1 for r in current if value(r) not in (None, "")))
    numbers = [n for n in (formulas._number(value(r)) for r in current) if n is not None]
    if agg == "sum":
        return float(sum(numbers))
    if agg == "average":
        return sum(numbers) / len(numbers) if numbers else None
    latest = max(current, key=lambda r: r.updated, default=None)
    return formulas._number(value(latest)) if latest is not None else None


def _milestones(brain, st, params) -> float:
    """Milestone tasks done, in one project or all."""
    from . import handoff
    project = str(params.get("project") or "")
    return float(sum(1 for t in handoff.tasks(brain, status="done", project=project)
                     if t["milestone"]))


def _unclaimed(brain, st, params) -> float:
    """Handoffs nobody claimed within N days."""
    from . import handoff
    days = int(params.get("days", 1))
    return float(sum(1 for t in handoff.tasks(brain, status="handed_off")
                     if _older_than(t.get("updated") or "", days - 1)))


def _since(days: int) -> str:
    return (util.today_date() - dt.timedelta(days=int(days))).isoformat()


def _corrections(brain, st, params) -> float:
    """Corrections the owner made to an AI's output (G3)."""
    return float(len(brain.ledger.corrections(status=None,
                                              since=_since(params.get("days", 7)))))


def _sent_back(brain, st, params) -> float:
    """Drafts sent back once, and recorded outputs flagged, for breaking a must-hold (G3)."""
    return float(brain.ledger.sent_back_count(_since(params.get("days", 7))))


SIGNALS: dict[str, Signal] = {s.name: s for s in (
    Signal("notes_overdue", "Much-used notes past their review date, or unchecked for 180 days",
           _notes_overdue),
    Signal("waiting", "Items waiting for you longer than {days} days", _waiting, {"days": 7}),
    Signal("unanswered", "Questions your AIs asked that the Brain could not answer, older "
           "than {days} days", _unanswered, {"days": 7}),
    Signal("quiet_projects", "Active projects quiet for {days} days", _quiet_projects,
           {"days": 14}),
    Signal("must_hold_recall", "Must-hold recall on your eval set", None,
           waits_for="the private eval set, labeled"),
    Signal("milestones", "Milestone tasks done", _milestones, {"project": ""}),
    Signal("sheet_column", "The {agg} of {column} in the {sheet} sheet", _sheet_column,
           {"sheet": "", "column": "", "agg": "latest"}),
    Signal("unclaimed", "Handoffs nobody claimed within {days} days", _unclaimed,
           {"days": 1}),
    Signal("corrections", "Corrections you made to an AI's work in the last {days} days",
           _corrections, {"days": 7}),
    Signal("sent_back", "Drafts sent back or flagged for breaking a must-hold in the last "
           "{days} days", _sent_back, {"days": 7}),
)}


def parse(raw: Any) -> dict:
    """A goal's measure from its note (JSON text, or a dict), else {} (you enter it)."""
    if isinstance(raw, dict):
        found = dict(raw)
    else:
        try:
            found = json.loads(str(raw or "") or "{}")
        except ValueError:
            return {}
    return found if isinstance(found, dict) and found.get("kind") in KINDS else {}


def problems(measure: dict) -> list[str]:
    """What keeps a measure from being kept as written."""
    out = []
    kind = measure.get("kind")
    if kind not in KINDS:
        return [f"a measure's kind is one of {', '.join(KINDS)}"]
    signal = measure.get("signal")
    if signal and signal not in SIGNALS:
        out.append(f"there is no signal {signal!r}")
    if kind in ("at_most", "at_least", "reach_by") and not isinstance(
            measure.get("target"), (int, float)):
        out.append("this kind of measure needs a number to hold it to")
    return out


def value(brain, measure: dict, st=None) -> float | None:
    """The signal's value now, or None when it cannot be computed yet."""
    signal = SIGNALS.get(str(measure.get("signal") or ""))
    if signal is None or signal.compute is None:
        return None
    st = st or brain.state()
    return signal.compute(brain, st, dict(signal.params, **(measure.get("params") or {})))


def judge(measure: dict, now_value: float | None, *, started: str = "", due: str = "",
          today: dt.date | None = None) -> str:
    """A computed status (goals plan 4.3): on_track when the measure meets its target,
    needs_attention within a tenth of it, off_track further out; no_data without a value."""
    kind = measure.get("kind")
    target = measure.get("target")
    if now_value is None or kind not in ("at_most", "at_least", "reach_by") \
            or not isinstance(target, (int, float)):
        return "no_data"
    slack = max(1.0, abs(float(target)) * 0.1)
    if kind == "at_most":
        if now_value <= target:
            return "on_track"
        return "needs_attention" if now_value <= target + slack else "off_track"
    if kind == "at_least":
        if now_value >= target:
            return "on_track"
        return "needs_attention" if now_value >= target - slack else "off_track"
    # Reach by a date: at least an even pace from the start to the due date.
    today = today or util.today_date()
    begin, end = util.parse_date(started), util.parse_date(due)
    if begin and end and end > begin:
        share = min(1.0, max(0.0, (today - begin).days / (end - begin).days))
        pace = float(target) * share
    else:
        pace = float(target)
    if now_value >= pace:
        return "on_track"
    return "needs_attention" if now_value >= pace - slack else "off_track"
