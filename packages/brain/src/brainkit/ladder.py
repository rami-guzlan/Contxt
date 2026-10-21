"""The goal ladder (goals plan 3, 4 and 7): the Brain's purpose, your goals and agent goals.

- THE PURPOSE is the `you-goals` note (goals.py): why this Brain exists. It never ends and has
  no target; the interview's "how will you know it's working" answer names its signals.
- YOUR GOALS (optional) and AGENT GOALS are notes of kind `goal`, loaded `manual` and filed
  beside the purpose: a goal steers what is kept and what agents do, never what a request
  receives. Their fields: `level` (yours, agent), `kept_by` (the agent keeping an agent goal),
  `serves` (goal ids, or the purpose), `measure` (measures.py, as JSON), `due`, `cadence`,
  `goal_status` (active, paused, met, missed, dropped, retired), `why` (the owner's words),
  `started`, and `owners` (teammates who keep a shared goal with you: the team edition's
  scaffold, refused in a solo Brain, which names no teammates).
- Each goal has an append-only journal (`journal/goals/<id>.jsonl`): your check-ins, agents'
  progress notes and the decisions recorded on it. A journal line never changes a computed
  status or the goal itself, and is never evidence for a note.
- Each check is a point in the ledger's `goal_checks`, kept for good: yours (`you`) from a
  check-in, or computed (`code`) from the goal's measure on its cadence.
- How a goal is going (plan 4.3): your latest call sets your goal's status for one cadence;
  after two without a check-in it shows "Not checked in". A computed measure that disagrees
  shows as a flag beside your call, never over it. Agent goals are computed: on track when the
  measure meets its target, needs attention within a tenth of it, off track further out or
  after two misses in a row. A check that keeps the same status says nothing; a Catch up card
  comes only when an agent goal turns off track (one card per slip).
- The board's shared blocks are written to the goal's plan file (`goals/<id>/plan.md`,
  generated, rewritten on save), so every AI reads the same text, in the app or over MCP.
  Private blocks never reach the vault.

Setting or changing one of your goals is your own act: one undo point. An agent goal its owner
sets in the app applies the same way; one proposed from a chat (notes_propose, kind goal) waits.
"""
from __future__ import annotations

import datetime as dt
import json

from . import frontmatter as fm
from . import governance, measures, statements, util
from .goals import GOALS_ID
from .goals import _home as goals_home
from .goals import read as read_purpose

CADENCES = statements.CADENCES
CALLS = ("on_track", "at_risk", "off_track")  # your call at a check-in
WORDS = {"on_track": "On track", "at_risk": "At risk", "off_track": "Off track",
         "needs_attention": "Needs attention", "no_data": "No data yet",
         "not_checked_in": "Not checked in", "paused": "Paused", "met": "Met",
         "missed": "Missed", "dropped": "Dropped", "retired": "Retired"}
MISSES = ("needs_attention", "off_track")
MAX_TITLE = 160
MAX_WHY = 600
MAX_LINE = 300
MAX_PLAN = 20000
TREND = 8  # checks on a trend line
KNOWLEDGE = "knowledge-agent"
# The knowledge agent's four goals: they keep the Brain itself healthy, and serve the purpose.
STARTERS = (
    {"id": "goal-notes-checked", "title": "No much-used note goes 180 days unchecked",
     "why": "The notes AIs use most cause the most wrong answers when they go stale.",
     "measure": {"kind": "at_most", "signal": "notes_overdue", "target": 0, "unit": "notes"},
     "cadence": "weekly"},
    {"id": "goal-nothing-waits", "title": "Nothing waits in Catch up over a week",
     "why": "What waits too long gets approved without a look, or never.",
     "measure": {"kind": "at_most", "signal": "waiting", "params": {"days": 7}, "target": 0,
                 "unit": "items"},
     "cadence": "daily"},
    {"id": "goal-questions-answered", "title": "Questions your AIs ask get answered in a week",
     "why": "A question the Brain cannot answer gets guessed at instead.",
     "measure": {"kind": "at_most", "signal": "unanswered", "params": {"days": 7},
                 "target": 0, "unit": "questions"},
     "cadence": "weekly"},
    {"id": "goal-rules-reach", "title": "Your rules reach every brief in their topic",
     "why": "A rule that misses a brief is a rule your AI never heard.",
     "measure": {"kind": "at_least", "signal": "must_hold_recall", "target": 95,
                 "unit": "%"},
     "cadence": "weekly"},
)


def _result(message, data=None, is_error=False):
    return governance._result(message, data, is_error)


def _clean(text, limit) -> str:
    """One line of the owner's words, with anything that looks like a secret hidden: goal
    notes, journals and plan files are read by every AI (goals plan 11, integrity)."""
    from .handoff import mask
    return mask(" ".join(str(text or "").split()))[:limit]


def is_goal(note) -> bool:
    return note is not None and note.kind == "goal"


def goal_notes(st, level: str | None = None) -> list:
    """Live goal notes, oldest first; only one level with `level`."""
    found = [n for n in st.index.notes.values() if is_goal(n)
             and (level is None or str(n.meta.get("level") or "yours") == level)]
    return sorted(found, key=lambda n: (str(n.meta.get("started") or n.added or ""), n.id))


def has_goals(st) -> bool:
    """Whether the Brain holds any goals of yours: without them every goal surface stays
    hidden, and briefs and cards never mention goals."""
    return any(lifecycle(n) not in ("dropped", "retired") for n in goal_notes(st, "yours"))


def lifecycle(note) -> str:
    found = str(note.meta.get("goal_status") or "active").strip()
    return found if found in statements.GOAL_STATUSES else "active"


def measure_of(note) -> dict:
    return measures.parse(note.meta.get("measure"))


def _period(note) -> int:
    return CADENCES.get(str(note.meta.get("cadence") or "weekly"), 7)


def _age_days(stamp: str, today: dt.date) -> int | None:
    found = util.day_of(stamp)
    return None if found is None else (today - found).days


def describe_measure(measure: dict) -> str:
    """A measure in plain words: "Much-used notes past ...: at most 0 notes"."""
    if not measure:
        return "You enter it at check-in"
    signal = measures.SIGNALS.get(str(measure.get("signal") or ""))
    what = signal.describe(measure.get("params")) if signal else ""
    unit = f" {measure['unit']}" if measure.get("unit") and measure["unit"] != "%" else (
        "%" if measure.get("unit") == "%" else "")
    target = measure.get("target")
    goal = {"at_most": f"at most {target}{unit}", "at_least": f"at least {target}{unit}",
            "reach_by": f"{target}{unit} by the due date",
            "enter": f"{target}{unit}" if target is not None else "",
            "every_period": "every period", "trend": "a trend",
            "judgment": "your judgment"}.get(str(measure.get("kind")), "")
    if what and goal:
        return f"{what}: {goal}"
    if measure.get("kind") == "enter":
        return f"You enter it at check-in{f', toward {goal}' if goal else ''}"
    return what or measures.KIND_WORDS.get(str(measure.get("kind")), "")


def status(note, checks: list[dict], today: dt.date | None = None) -> dict:
    """How the goal is going, by the rules in plan 4.3: {"status", "words", "call", "flag",
    "stale"}. `checks` are its checks, newest first."""
    today = today or util.today_date()
    life = lifecycle(note)
    out = {"status": life, "words": WORDS.get(life, life), "call": None, "flag": "",
           "stale": False}
    if life != "active":
        return out
    code = next((c for c in checks if c.get("source") == "code"), None)
    if str(note.meta.get("level") or "yours") == "agent":
        found = str(code.get("status")) if code else "no_data"
        return dict(out, status=found, words=WORDS.get(found, found))
    yours = next((c for c in checks if c.get("source") == "you"), None)
    period = _period(note)
    age = _age_days(str(yours.get("at") or ""), today) if yours else None
    if yours is None or age is None or age > 2 * period:
        out.update(status="not_checked_in", words=WORDS["not_checked_in"])
    else:
        call = str(yours.get("status"))
        out.update(status=call, words=WORDS.get(call, call), call=call, stale=age > period)
    # A computed measure beside your call says so when it disagrees; your call stands.
    if code and code.get("status") in ("on_track", *MISSES) and out["call"]:
        computed_ok = code.get("status") == "on_track"
        if computed_ok != (out["call"] == "on_track"):
            measure = measure_of(note)
            value = code.get("value")
            shown = f"{value:g}" if isinstance(value, (int, float)) else "no value"
            target = measure.get("target")
            behind = "meets its target" if computed_ok else "is behind its target"
            out["flag"] = (f"The measure says {shown}"
                           f"{f' against {target}' if target is not None else ''}, which "
                           f"{behind}.")
    return out


def view(brain, note, *, st=None, full: bool = False, today: dt.date | None = None) -> dict:
    """One goal as the app shows it; with `full`, its journal, checks and plan too."""
    st = st or brain.state()
    checks = brain.ledger.goal_checks(note.id, limit=60 if full else 2 * TREND + 2)
    measure = measure_of(note)
    how = status(note, checks, today)
    level = str(note.meta.get("level") or "yours")
    latest = next((c for c in checks if c.get("value") is not None
                   and (level == "agent" or c.get("source") == "you"
                        or measure.get("kind") != "enter")), None)
    trend_source = "code" if level == "agent" else "you"
    trend = [c["value"] for c in checks
             if c.get("source") == trend_source and c.get("value") is not None][:TREND]
    serves = note.meta.get("serves") or []
    if isinstance(serves, str):
        serves = [s.strip() for s in serves.split(",") if s.strip()]
    projects = [{"id": f.id, "title": f.title, "status": f.status}
                for f in st.index.focuses.values()
                if note.id in fm.as_list(f.note.meta.get("goals"))]
    period = _period(note)
    you = next((c for c in checks if c.get("source") == "you"), None)
    age = _age_days(str(you.get("at") or ""), today or util.today_date()) if you else None
    plan = brain.vault.goal_plan(note.id)
    out = {
        "id": note.id, "title": note.title, "level": level,
        "kept_by": str(note.meta.get("kept_by") or "") or None,
        "owners": fm.as_list(note.meta.get("owners")),
        "admins": sorted(governance.admins_of(st, note.area)),
        "why": str(note.meta.get("why") or ""), "serves": list(serves),
        "measure": measure or None, "measure_words": describe_measure(measure),
        "due": str(note.meta.get("due") or "") or None,
        "cadence": str(note.meta.get("cadence") or "weekly"),
        "lifecycle": lifecycle(note), "started": str(note.meta.get("started") or "") or None,
        **how,
        "now": latest.get("value") if latest else None,
        "target": measure.get("target"), "unit": measure.get("unit"),
        "trend": list(reversed(trend)),
        "checked_at": checks[0]["at"] if checks else None,
        "checked_in_at": you["at"] if you else None,
        "check_in_due": level == "yours" and lifecycle(note) == "active"
        and (age is None or age >= period),
        "projects": projects, "shared_plan": bool(plan.strip()),
    }
    if full:
        out["journal"] = list(reversed(brain.vault.goal_journal(note.id)))[:100]
        out["checks"] = checks
        out["plan"] = plan
    return out


def _goal(st, goal_id):
    note = st.index.note(str(goal_id or ""))
    return note if is_goal(note) else None


def ladder(brain, *, today: dt.date | None = None) -> dict:
    """The whole ladder: the purpose, your goals, agent goals by who keeps them."""
    st = brain.state()
    purpose = read_purpose(brain)
    answers = purpose.get("answers") or {}
    working = str(answers.get("working") or "")
    yours = [view(brain, n, st=st, today=today) for n in goal_notes(st, "yours")]
    agents = [view(brain, n, st=st, today=today) for n in goal_notes(st, "agent")]
    return {
        "purpose": {"id": GOALS_ID, "exists": purpose.get("exists", False),
                    "text": purpose.get("purpose", ""),
                    "signals": [line.strip(" -*\t") for line in working.splitlines()
                                if line.strip(" -*\t")],
                    # The interview's "how" and "never" answers show under Rules.
                    "rules": {k: str(answers.get(k) or "") for k in ("how", "never",
                                                                      "leave_out")}},
        "must_holds": must_holds(st),
        "yours": yours, "agents": agents,
        "has_goals": has_goals(st),
        "check_ins_due": sum(1 for g in yours if g["check_in_due"]),
        "starters": [{"id": s["id"], "title": s["title"],
                      "on": st.index.note(s["id"]) is not None} for s in STARTERS],
    }


def must_holds(st) -> list[dict]:
    """The must-holds by domain: what reaches every brief whenever its domain comes up."""
    domains: dict[str, list[dict]] = {}
    for note in st.index.notes.values():
        if not note.must_hold or not note.live:
            continue
        for domain in note.applies_to or ["every request"]:
            domains.setdefault(str(domain), []).append(
                {"id": note.id, "title": note.title,
                 "text": note.must_text or util.excerpt(note.body, 200)})
    return [{"domain": d, "notes": notes} for d, notes in sorted(domains.items())]


def signals(brain) -> list[dict]:
    """The signal library for the measure picker, each with its value right now."""
    st = brain.state()
    out = []
    for signal in measures.SIGNALS.values():
        now = None
        if signal.compute is not None:
            try:
                now = signal.compute(brain, st, dict(signal.params))
            except Exception:  # a signal that cannot read shows no value
                now = None
        out.append({"name": signal.name, "label": signal.describe(),
                    "params": signal.params, "available": signal.compute is not None,
                    "waits_for": signal.waits_for or None, "now": now})
    return out


# ---------------------------------------------------------------------- setting and changing
def _body(title: str, why: str) -> str:
    return f"{title.rstrip('.')}.\n\nWhy: {why}" if why else f"{title.rstrip('.')}."


def teammates(st) -> set[str]:
    """Who can share a goal (G3's scaffold): brain.json's `people` and the admins it names.
    A solo Brain names none, so its goals stay the owner's."""
    named = {str(p) for p in st.config.data.get("people") or []}
    for people in (st.config.data.get("admins") or {}).values():
        named.update(str(p) for p in people or [])
    return named


def _problems(st, *, title, why, level, kept_by, measure, due, cadence, serves,
              owners=()) -> list[str]:
    problems = []
    if owners:
        known = teammates(st)
        if not known:
            problems.append("teammates share goals in the team edition")
        elif set(owners) - known:
            problems.append(f"{', '.join(sorted(set(owners) - known))} is not a teammate")
    if not title:
        problems.append("say the goal in a sentence")
    if level not in ("yours", "agent"):
        problems.append("a goal is yours or an agent's")
    if level == "agent" and not kept_by:
        problems.append("an agent goal names the agent that keeps it")
    if measure:
        problems += measures.problems(measure)
    if level == "agent" and (not measure or measure.get("kind") == "enter"):
        problems.append("an agent goal has a measure code can compute")
    if due and util.parse_date(due) is None:
        problems.append("due is a date (YYYY-MM-DD)")
    if cadence not in CADENCES:
        problems.append(f"cadence is one of {', '.join(CADENCES)}")
    unknown = [s for s in serves if s != GOALS_ID and _goal(st, s) is None]
    if unknown:
        problems.append(f"no goal {', '.join(repr(s) for s in unknown)} to serve")
    return problems


def set_goal(brain, *, title, why="", level="yours", kept_by="", measure=None, due="",
             cadence="weekly", serves=(), goal_id=None, actor=None, apply=True, owners=()):
    """Set a goal. The owner's own act applies as one undo point; with `apply` false (an AI
    proposing it from a chat) it waits for the owner."""
    from . import checkpoints
    who, refusal = governance._require_approver(brain, actor) if apply else (
        brain.principal(actor), None)
    if refusal:
        return refusal
    st = brain.state()
    title, why = _clean(title, MAX_TITLE), _clean(why, MAX_WHY)
    measure = measures.parse(measure) if measure else {}
    serves = [str(s).strip() for s in (serves or []) if str(s).strip()]
    owners = [str(o).strip() for o in (owners or []) if str(o).strip()]
    problems = _problems(st, title=title, why=why, level=level, kept_by=kept_by,
                         measure=measure, due=str(due or "").strip(), cadence=cadence,
                         serves=serves, owners=owners)
    if problems:
        return _result("Not set: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    wanted = goal_id or ("goal-" + util.slugify(title, 48))
    note_id = wanted if goal_id and st.index.note(goal_id) is None else governance.unique_id(
        st, wanted)
    area, topic = goals_home(brain, who, title)
    day = util.today()
    extra = {"level": level, "goal_status": "active", "cadence": cadence, "started": day}
    if why:
        extra["why"] = why
    if kept_by:
        extra["kept_by"] = kept_by
    if measure:
        extra["measure"] = json.dumps(measure, sort_keys=True)
    if due:
        extra["due"] = util.parse_date(due).isoformat()
    if serves:
        extra["serves"] = serves
    if owners:
        extra["owners"] = owners
    made_by = "set by the owner" if apply else "proposed in a conversation"
    with checkpoints.batch(brain, actor=who, label=f"Goal: {title}") as batch:
        made = governance.propose_note(
            brain, area=area, topic=topic, text=_body(title, why), scope=who, load="manual",
            principal=who, title=title, summary=title, note_kind="goal", note_id=note_id,
            evidence=f"The goal as {made_by}, {day}.", source=f"{made_by} ({who})",
            reason="a goal for the Brain's ladder", force_pending=True, extra=extra)
        if made.is_error or not apply:
            return made
        done = governance.approve(brain, made.data["proposal_id"], actor=who)
        if done.is_error:
            return done
        batch.decisions.append({"action": "approved", "note": note_id, "title": title})
    st = brain.state()
    return _result(f"Goal set: {title}.",
                   {"status": "set", "goal": view(brain, st.index.note(note_id), st=st),
                    "checkpoint": batch.checkpoint})


def change_goal(brain, goal_id, changes: dict, *, reason="", actor=None):
    """Change a goal: its words (`title`, `why`) and its fields (measure, due, cadence,
    status, what it serves). One undo point."""
    from . import checkpoints
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    st = brain.state()
    note = _goal(st, goal_id)
    if note is None:
        return _result(f"No goal {goal_id!r}.", {"status": "missing"}, True)
    changes = dict(changes or {})
    title = _clean(changes.pop("title", note.title), MAX_TITLE)
    why = _clean(changes.pop("why", note.meta.get("why") or ""), MAX_WHY)
    fields = {}
    for key, value in changes.items():
        if key == "measure":
            value = json.dumps(measures.parse(value), sort_keys=True) if value else ""
        elif key == "serves" and isinstance(value, (list, tuple)):
            value = ", ".join(str(v) for v in value)
        elif key == "status":
            key = "goal_status"
        fields[key] = "" if value is None else str(value)
    if not title:
        return _result("Say the goal in a sentence.", {"status": "invalid"}, True)
    with checkpoints.batch(brain, actor=who, label=f"Goal changed: {title}") as batch:
        with brain.deferring() as deferred:
            deferred.message = f"Goal changed: {title}"
            if title != note.title or why != str(note.meta.get("why") or ""):
                done = governance.edit(brain, note.id, _body(title, why), title=title,
                                       summary=title, reason=reason or "The owner changed the "
                                       "goal.", actor=who)
                if done.is_error:
                    return done
                fields["why"] = why
            if fields:
                done = governance.update(brain, note.id, fields, reason=reason, actor=who)
                if done.is_error and done.data.get("status") != "unchanged":
                    return done
            batch.decisions.append({"action": "edited", "note": note.id, "title": title})
    st = brain.state()
    return _result(f"Goal changed: {title}.",
                   {"status": "changed", "goal": view(brain, st.index.note(note.id), st=st),
                    "checkpoint": batch.checkpoint})


def link_project(brain, goal_id, project_id, *, linked=True, actor=None):
    """Link a project to a goal it serves, or unlink it (the project's `goals`)."""
    st = brain.state()
    if _goal(st, goal_id) is None:
        return _result(f"No goal {goal_id!r}.", {"status": "missing"}, True)
    focus = st.index.focuses.get(str(project_id or ""))
    if focus is None:
        return _result(f"No project {project_id!r}.", {"status": "missing"}, True)
    goals = [g for g in fm.as_list(focus.note.meta.get("goals")) if g != goal_id]
    if linked:
        goals.append(goal_id)
    return governance.update(brain, focus.id, {"goals": ", ".join(goals)},
                             reason="Linked to a goal." if linked else "Unlinked from a goal.",
                             actor=actor)


def turn_on_starters(brain, *, actor=None):
    """The knowledge agent's four goals, set by the owner in one tap (the ones already on are
    left as they are)."""
    st = brain.state()
    made = []
    for starter in STARTERS:
        if st.index.note(starter["id"], include_archived=True) is not None:
            continue
        done = set_goal(brain, title=starter["title"], why=starter["why"], level="agent",
                        kept_by=KNOWLEDGE, measure=starter["measure"],
                        cadence=starter["cadence"], serves=[GOALS_ID],
                        goal_id=starter["id"], actor=actor)
        if done.is_error:
            return done
        made.append(starter["id"])
    return _result(f"{len(made)} of the knowledge agent's goals turned on."
                   if made else "The knowledge agent's goals are already on.",
                   {"status": "on", "made": made})


# ---------------------------------------------------------------------- check-ins and journals
def check_in(brain, goal_id, *, call, value=None, line="", actor=None, via="app"):
    """Your check-in on one of your goals: your call (on track, at risk, off track), the
    number when the goal tracks one, and a line. It goes in the goal's journal and on its
    trend line."""
    who = brain.principal(actor)
    st = brain.state()
    note = _goal(st, goal_id)
    if note is None:
        return _result(f"No goal {goal_id!r}.", {"status": "missing"}, True)
    if str(note.meta.get("level") or "yours") != "yours":
        return _result("An agent goal is checked by code on its cadence, not by a check-in.",
                       {"status": "invalid"}, True)
    if lifecycle(note) != "active":
        return _result(f"This goal is {WORDS[lifecycle(note)].lower()}.",
                       {"status": "invalid"}, True)
    if call not in CALLS:
        return _result("Say how it is going: on_track, at_risk or off_track.",
                       {"status": "invalid", "field": "call"}, True)
    number = None
    if value not in (None, ""):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return _result("The number is a number, for example 71.",
                           {"status": "invalid", "field": "value"}, True)
    line = _clean(line, MAX_LINE)
    at = util.now_iso()
    record = {"at": at, "kind": "check_in", "by": who, "call": call, "value": number,
              "line": line, "via": via}
    relpath = brain.vault.append_goal_entry(note.id, record)
    brain.ledger.add_goal_check(note.id, status=call, value=number, source="you", note=line,
                                at=at)
    brain.after_write([brain.vault.path(relpath)], f"Check-in on {note.id}: {WORDS[call]}")
    return _result(f"Checked in: {WORDS[call]}.",
                   {"status": "checked_in", "goal": view(brain, note, st=st)})


def journal_note(brain, goal_id, text, *, kind="decision", by=None, actor=None):
    """A decision recorded on the goal, or an agent's progress note. It never changes the
    goal or its status."""
    who = brain.principal(actor)
    st = brain.state()
    note = _goal(st, goal_id)
    if note is None:
        return _result(f"No goal {goal_id!r}.", {"status": "missing"}, True)
    if kind not in ("decision", "progress"):
        return _result("A goal's journal takes a decision or a progress note.",
                       {"status": "invalid"}, True)
    text = _clean(text, 1000)
    if not text:
        return _result("Say what was decided or done.", {"status": "invalid"}, True)
    record = {"at": util.now_iso(), "kind": kind, "by": str(by or who), "text": text}
    relpath = brain.vault.append_goal_entry(note.id, record)
    brain.after_write([brain.vault.path(relpath)], f"{kind.title()} on {note.id}")
    return _result("Recorded.", {"status": "recorded", "entry": record})


# ---------------------------------------------------------------------- computed checks
def _due(note, last: dict | None, today: dt.date) -> bool:
    if last is None:
        return True
    age = _age_days(str(last.get("at") or ""), today)
    return age is None or age >= _period(note)


def run_checks(brain, *, force=False, only=None, today: dt.date | None = None) -> list[dict]:
    """Check every active goal with a computed measure on its cadence (code only, free):
    agent goals, and the measure beside your goals. A check that keeps the same status says
    nothing; an agent goal that turns off track raises one Catch up card."""
    today = today or util.today_date()
    st = brain.state()
    out = []
    for note in goal_notes(st):
        if only and note.id not in only:
            continue
        measure = measure_of(note)
        signal = measures.SIGNALS.get(str(measure.get("signal") or ""))
        if lifecycle(note) != "active" or signal is None or signal.compute is None:
            continue
        previous = brain.ledger.goal_checks(note.id, limit=1, source="code")
        last = previous[0] if previous else None
        if not force and not _due(note, last, today):
            continue
        try:
            value = measures.value(brain, measure, st)
        except Exception:  # a signal that cannot read records no data
            value = None
        found = measures.judge(measure, value, started=str(note.meta.get("started") or ""),
                               due=str(note.meta.get("due") or ""), today=today)
        was = str(last.get("status")) if last else ""
        if found == "needs_attention" and was in MISSES:
            found = "off_track"  # two misses in a row
        agent = str(note.meta.get("level") or "yours") == "agent"
        card = agent and found == "off_track" and was != "off_track"
        why = ""
        if card:
            why = (f"It turned off track: {describe_measure(measure)}, now "
                   f"{value:g}." if isinstance(value, (int, float)) else
                   "It turned off track.")
        brain.ledger.add_goal_check(note.id, status=found, value=value, source="code",
                                    note=why, card=card)
        task = None
        if card:
            # Its agent opens a task for it (one open per goal, five per agent).
            from . import handoff
            task = handoff.open_for_slipped_goal(brain, note.id)
        out.append({"goal": note.id, "status": found, "value": value, "was": was or None,
                    "card": card, "why": why or None, "task": task})
    return out


def cards(brain, *, st=None) -> list[dict]:
    """Agent goals that slipped and are still off track: one card per slip, keyed by the
    check that raised it, until the goal recovers (or the owner sets the card aside)."""
    st = st or brain.state()
    out = []
    for note in goal_notes(st, "agent"):
        if lifecycle(note) != "active":
            continue
        for check in brain.ledger.goal_checks(note.id, limit=2 * TREND, source="code"):
            if check.get("status") != "off_track":
                break
            if check.get("card"):
                out.append({"key": f"goal:{note.id}:{check['at']}",
                            "goal": view(brain, note, st=st),
                            "why": check.get("note") or "", "at": check["at"]})
                break
    return out


# ---------------------------------------------------------------------- the shared plan
def write_plan(brain, goal_id, blocks, *, actor=None):
    """Write the goal's shared plan from the board's shared blocks ([{"title", "text"}], in
    board order); none removes it. The owner's own words in their own scope: no approval."""
    who = brain.principal(actor)
    st = brain.state()
    note = _goal(st, goal_id)
    if note is None:
        return _result(f"No goal {goal_id!r}.", {"status": "missing"}, True)
    from .handoff import mask
    sections = []
    for block in blocks or []:
        title = _clean(block.get("title") or "", 120) or "Untitled"
        text = mask(str(block.get("text") or "").strip())
        sections.append(f"## {title}\n\n{text}" if text else f"## {title}")
    text = ""
    if sections:
        text = (f"# Plan: {note.title}\n\nThe owner's shared plan for goal `{note.id}`, from "
                "its board. Generated; rewritten when the board is saved.\n\n"
                + "\n\n".join(sections))
    if len(text) > MAX_PLAN:
        return _result(f"Keep the shared plan under {MAX_PLAN:,} characters.",
                       {"status": "invalid"}, True)
    if text.strip() == brain.vault.goal_plan(note.id).strip():
        return _result("The shared plan already says that.", {"status": "unchanged"})
    relpath = brain.vault.write_goal_plan(note.id, text)
    brain.after_write([brain.vault.path(relpath)], f"Shared plan for {note.id} ({who})")
    return _result("Shared plan saved." if text else "Nothing on the board is shared now.",
                   {"status": "saved", "path": relpath, "sections": len(sections)})


def context(brain, goal_id) -> str:
    """A goal as an AI receives it (about 150 tokens before anything is opened): the goal,
    its why, its measure and status, and a pointer to its shared plan."""
    st = brain.state()
    note = _goal(st, goal_id)
    if note is None:
        return ""
    shown = view(brain, note, st=st)
    lines = [f"Goal: {note.title} (`{note.id}`, {shown['level']})"]
    if shown["why"]:
        lines.append(f"Why: {shown['why']}")
    lines.append(f"Measure: {shown['measure_words']}. Status: {shown['words']}.")
    if shown["due"]:
        lines.append(f"Due: {shown['due']}.")
    if shown["shared_plan"]:
        plan = brain.vault.goal_plan(note.id)
        heads = [line[3:].strip() for line in plan.splitlines() if line.startswith("## ")]
        lines.append(f"Shared plan: notes_get `{note.id}` ({', '.join(heads[:6])}).")
    return "\n".join(lines)
