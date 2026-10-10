"""The knowledge agent's tools (brain-logic plan 17.4 and 17.6): all local, typed and checked by
code. To look: the map, search_notes, get_note, get_state, changes_since, history, impact,
past_suggestions, and the Library, skills, agents, workflows, projects and goals read only. To
suggest: a note to add, edit, merge, narrow or retire; a State update; a challenge or a "Still
true?" card; a task (`hand_off`); a goal progress note. A suggestion tool writes nothing: it
returns the suggestion, which code turns into a proposal or a card that waits for the person.

THE CHANGE DIGEST (`changes_since`): what changed since a moment, by area, from undo points,
decisions, State cell logs and goal checks. THE IMPACT CHECK (`impact`): what depends on an item
(other notes that name it, skills, agents and workflows that load it, briefs that used it in 30
days, must-holds that reached those briefs, goal measures and open tasks), one line on every
card. THE MEMORY (`past_suggestions`): each suggestion, the person's decision and the reason,
found again by topic; a lesson that holds across cases is offered as a governed note.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable

from . import util

MAX_RESULT_CHARS = 3000
LESSON_CASES = 3


@dataclass
class Tool:
    name: str
    kind: str  # look | suggest
    description: str
    args: dict[str, str]  # name -> "str" | "int" | "list" | "str?" (optional)
    run: Callable[..., Any]
    ids: tuple[str, ...] = field(default_factory=tuple)  # args that must name a live note

    def problems(self, brain, args: Any) -> list[str]:
        if not isinstance(args, dict):
            return ["args is an object"]
        out = []
        for name, kind in self.args.items():
            optional = kind.endswith("?")
            value = args.get(name)
            if value in (None, "") and not optional:
                out.append(f"{name} is required")
                continue
            if value in (None, ""):
                continue
            base = kind.rstrip("?")
            if base == "int" and not isinstance(value, int):
                out.append(f"{name} is a whole number")
            if base == "list" and not isinstance(value, list):
                out.append(f"{name} is a list")
            if base == "str" and not isinstance(value, str):
                out.append(f"{name} is text")
        unknown = sorted(set(args) - set(self.args))
        if unknown:
            out.append(f"no argument {unknown[0]!r}")
        st = brain.state()
        for name in self.ids:
            values = args.get(name)
            for value in (values if isinstance(values, list) else [values]):
                if value and st.index.note(str(value)) is None:
                    out.append(f"no note {value!r}")
        return out


# ---------------------------------------------------------------------- the digest
def changes_since(brain, since: str = "", *, days: int = 7) -> dict:
    """What changed since `since` (or the last `days`), grouped by area."""
    from . import checkpoints, state
    since = since or (util.today_date() - dt.timedelta(days=days)).isoformat()
    st = brain.state()
    by_area: dict[str, list[str]] = {}

    def add(area: str, line: str) -> None:
        by_area.setdefault(area or "other", []).append(line)

    for record in brain.vault.decisions():
        if str(record.get("at") or "") < since:
            continue
        note = st.index.note(str(record.get("note") or ""))
        area = note.area if note is not None else "other"
        add(area, f"{record.get('action')} {record.get('note') or record.get('proposal')}")
    for point in checkpoints.list_checkpoints(brain, limit=50):
        if str(point.get("at") or "") >= since:
            add("undo points", str(point.get("label") or ""))
    for sheet in state.sheets(brain):
        for row in state.rows(brain, sheet.id, with_computed=False):
            if row.updated >= since:
                add(f"state/{sheet.id}", f"{row.key} changed")
    from . import ladder
    for goal in ladder.goal_notes(st):
        checks = [c for c in brain.ledger.goal_checks(goal.id, limit=5) if c["at"] >= since]
        if checks:
            add("goals", f"{goal.title}: {checks[0]['status']}")
    lines = [f"{area}: {len(items)} ({'; '.join(items[:3])})"
             for area, items in sorted(by_area.items())]
    return {"since": since, "areas": by_area,
            "line": "Changed since " + since[:10] + ": " + ("; ".join(lines) if lines
                                                            else "nothing")}


# ---------------------------------------------------------------------- the impact check
def impact(brain, item_id: str, *, days: int = 30) -> dict:
    """What depends on an item, and the line every card carries."""
    from . import handoff, ladder
    st = brain.state()
    note = st.index.note(item_id)
    if note is None:
        return {"id": item_id, "line": f"No note {item_id!r}."}
    title = note.title.lower()
    linked = [n.id for n in st.index.notes.values()
              if n.id != note.id and (note.id in n.body or (len(title) > 6 and title in
                                                              n.body.lower()))]
    skills = [name for name, skill in st.index.skills.items()
              if note.id in (getattr(skill, "loads", None) or [])
              or note.route_key in (getattr(skill, "loads", None) or [])]
    since = (util.today_date() - dt.timedelta(days=days)).isoformat()
    briefs, holds = 0, set()
    for row in brain.ledger.requests(limit=500):
        if str(row.get("at") or "") < since:
            continue
        data = row.get("data") or {}
        if note.id in (data.get("note_ids") or []):
            briefs += 1
            holds.update(data.get("must_hold_ids") or [])
    measures = [g.id for g in ladder.goal_notes(st) if note.id in str(g.meta.get("measure"))]
    tasks = [t["id"] for t in handoff.tasks(brain, open_only=True)
             if note.id in str((t.get("card") or {}).get("load") or "")]
    parts = []
    if skills:
        parts.append(f"{len(skills)} skill{'s' if len(skills) != 1 else ''}")
    if linked:
        parts.append(f"{len(linked)} other note{'s' if len(linked) != 1 else ''}")
    parts.append(f"{briefs} brief{'s' if briefs != 1 else ''} from the last month")
    if tasks:
        parts.append(f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''}")
    return {"id": note.id, "linked": linked, "skills": skills, "briefs": briefs,
            "must_holds": sorted(holds), "measures": measures, "tasks": tasks,
            "line": f"{note.title} touches " + ", ".join(parts) + "."}


# ---------------------------------------------------------------------- the memory
def past_suggestions(brain, topic: str, *, limit: int = 5) -> list[dict]:
    """Earlier suggestions and the person's decisions, found again by topic."""
    words = set(util.content_terms(topic))
    rows = brain.ledger.episodes()
    scored = []
    for row in rows:
        overlap = len(words & set(util.content_terms(f"{row['topic']} {row['text']}")))
        if overlap:
            scored.append((overlap, row))
    scored.sort(key=lambda s: (-s[0], s[1]["at"]), reverse=False)
    return [r for _s, r in scored[:limit]]


def lessons(brain) -> list[dict]:
    """A lesson that holds across cases: the same kind of suggestion in the same area decided
    the same way three times or more, offered as a governed note."""
    groups: dict[tuple, list[dict]] = {}
    for row in brain.ledger.episodes():
        if row["decision"] in ("kept", "declined"):
            groups.setdefault((row["action"], row["area"], row["decision"]), []).append(row)
    out = []
    for (action, area, decision), rows in groups.items():
        if len(rows) >= LESSON_CASES:
            reasons = [r["reason"] for r in rows if r.get("reason")][:3]
            out.append({"action": action, "area": area, "decision": decision,
                        "cases": len(rows),
                        "text": f"In {area}, the owner {decision} the knowledge agent's "
                                f"{action} suggestions {len(rows)} times"
                                + (f": {'; '.join(reasons)}." if reasons else ".")})
    return out


# ---------------------------------------------------------------------- the registry
def _note(brain, args):
    found = brain.note(args["id"])
    return util.excerpt(found.text, MAX_RESULT_CHARS)


def _search(brain, args):
    return util.excerpt(brain.search(args["query"], limit=6).text, MAX_RESULT_CHARS)


def _state(brain, args):
    return util.excerpt(brain.get_state(sheet=args.get("sheet") or "",
                                        row=args.get("row") or "").text, MAX_RESULT_CHARS)


def _history(brain, args):
    from . import history
    rows = history.versions(brain, args["id"], limit=5) or []
    return [{"at": r.get("at"), "by": r.get("by"), "reason": r.get("reason")} for r in rows]


def _suggest(kind: str):
    def run(brain, args):
        return {"suggestion": kind, **args}
    return run


TOOLS: dict[str, Tool] = {t.name: t for t in (
    Tool("get_note", "look", "Open one note by id.", {"id": "str"}, _note, ids=("id",)),
    Tool("search_notes", "look", "Find notes by meaning.", {"query": "str"}, _search),
    Tool("get_state", "look", "Read a State sheet or a row.", {"sheet": "str?", "row": "str?"},
         _state),
    Tool("changes_since", "look", "What changed lately, by area.", {"since": "str?"},
         lambda b, a: changes_since(b, a.get("since") or "")["line"]),
    Tool("history", "look", "A note's changes, who and why.", {"id": "str"}, _history,
         ids=("id",)),
    Tool("impact", "look", "What depends on a note.", {"id": "str"},
         lambda b, a: impact(b, a["id"]), ids=("id",)),
    Tool("past_suggestions", "look", "Earlier suggestions on a topic and what the person "
         "decided.", {"topic": "str"}, lambda b, a: past_suggestions(b, a["topic"])),
    Tool("suggest_note", "suggest", "Suggest a note to add, edit, merge, narrow or retire.",
         {"change": "str", "ids": "list?", "text": "str?", "why": "str"},
         _suggest("note"), ids=("ids",)),
    Tool("suggest_state", "suggest", "Suggest a State value.",
         {"sheet": "str", "row": "str", "column": "str", "value": "str", "why": "str"},
         _suggest("state")),
    Tool("challenge", "suggest", "Ask the person whether a note is still true.",
         {"id": "str", "why": "str"}, _suggest("challenge"), ids=("id",)),
    Tool("open_task", "suggest", "Suggest a task.", {"title": "str", "why": "str"},
         _suggest("task")),
)}
CHANGES = ("add", "edit", "merge", "narrow", "retire")


def call(brain, name: str, args: Any) -> tuple[Any, list[str]]:
    """(the tool's result, problems). A suggestion tool returns the suggestion, never writes."""
    tool = TOOLS.get(str(name or ""))
    if tool is None:
        return None, [f"no tool {name!r}; use one of {', '.join(TOOLS)}"]
    problems = tool.problems(brain, args)
    if tool.name == "suggest_note" and isinstance(args, dict) \
            and args.get("change") not in CHANGES:
        problems.append(f"change is one of {', '.join(CHANGES)}")
    if problems:
        return None, problems
    try:
        return tool.run(brain, args), []
    except (KeyError, ValueError, OSError) as exc:
        return None, [f"the tool could not run: {exc}"]


def menu() -> str:
    """The tools as the core prompt lists them, one line each."""
    return "\n".join(f"- {t.name}({', '.join(t.args)}): {t.description}"
                     for t in TOOLS.values())

