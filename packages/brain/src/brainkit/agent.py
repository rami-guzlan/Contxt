"""The knowledge agent's map and evidence: what a model that keeps the brain is shown, made by
code from the brain as it is right now, so the model never guesses at what exists and spends
its tokens on judgment alone.

`outline` is the map: every live note by area and topic (its id, kind, title and the flags
upkeep cares about), the goals, the projects, the skills and what waits. `gather` collects the
candidates for one upkeep action, each with the full text a model needs to judge it and a short
reference (`c1`, `c2`) to answer by, so a small model never has to copy an id right:

- `tidy-repeats`: live notes that say the same thing (review.near_duplicates)
- `check-drift`: notes something newer may contradict: what went in on its own and a model
  read as contradicting a note, older dated values, and the weekly cross-check's findings
- `check-alignment`: the goals and projects against what the brain holds, notes no AI used in
  months, and must-holds with nothing to bring them up
- `freshen-up`: notes past their review date or last day, the most used first, then the most
  used notes nobody checked in half a year
- `tidy-projects`: active projects gone quiet or without next steps
- `tidy-skills`: skills no AI used lately, skills with no words to ask for them, and skills
  asked for with the same words
- `fill-gaps`: what AIs asked that the brain could not answer

Each action follows a procedure of its own (`builtin/agent/<action>/SKILL.md`, and
`knowledge-agent` for a conversation): what the model is given, how to judge, and the JSON to
answer with. They ship with the engine rather than living in a brain, so a conversation that
asks the brain for "my skills" never routes to one; a brain skill of the same name replaces
one, for an owner who wants their own.

Nothing here writes, and nothing calls a model: the workspace asks the model the owner chose
and turns its answers into suggestions that wait for the owner.
"""
from __future__ import annotations

import datetime as _dt
import os

from . import frontmatter as fm
from . import util
from .goals import GOALS_ID

ACTIONS = ("tidy-repeats", "check-drift", "check-alignment", "freshen-up", "tidy-projects",
           "tidy-skills", "fill-gaps")
CHAT = "knowledge-agent"  # the procedure for a conversation with the owner
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin", "agent")
MAX_CANDIDATES = 10
NOTE_CHARS = 900          # of each note's text a candidate carries
UNUSED_DAYS = 90          # a note no AI used this long may be off the goals
QUIET_DAYS = 14           # an active project without an update this long has gone quiet
SKILL_IDLE_DAYS = 60      # a skill no AI used this long may be forgotten or misnamed
CHECKED_DAYS = 180        # a much-used note nobody checked this long deserves a look
NEW_DAYS = 14
BRIEF_LINES = 60          # notes a brief outline lists (for small local models)


def skills(brain=None) -> list[dict]:
    """The agent's procedures: [{"name", "description", "when_to_use", "triggers", "text",
    "own"}], `own` when the brain holds a skill of that name, which is used instead."""
    have = brain.state().index.skills if brain is not None else {}
    out = []
    for name in (CHAT, *ACTIONS):
        path = os.path.join(FOLDER, name, "SKILL.md")
        if not os.path.isfile(path):
            continue
        meta, body, _errors = fm.parse(util.read_text(path))
        own = have.get(name)
        out.append({"name": name, "description": str(meta.get("description") or ""),
                    "when_to_use": str(meta.get("when_to_use") or ""),
                    "triggers": fm.as_list(meta.get("triggers")),
                    "text": own.body if own is not None else body, "own": own is not None})
    return out


def skill_text(brain, name: str) -> str | None:
    """The procedure one action follows: the brain's own skill of that name, else the one the
    engine ships; None for an unknown name."""
    wanted = str(name or "").strip().lstrip("/")
    if wanted not in (CHAT, *ACTIONS):
        return None
    own = brain.state().index.skills.get(wanted) if brain is not None else None
    if own is not None:
        return own.body
    path = os.path.join(FOLDER, wanted, "SKILL.md")
    if not os.path.isfile(path):
        return None
    _meta, body, _errors = fm.parse(util.read_text(path))
    return body


def _usage(brain, kind: str = "note") -> dict:
    """{item: {"total", "d7", "d30", "last"}} for one kind of item, from the session ledger."""
    try:
        table = brain.ledger.usage_table(kind)
    except Exception:  # an unreadable ledger only means nothing is known about use
        return {}
    return {item: row for (found, item), row in table.items() if found == kind}


def _day(days_ago: int) -> str:
    return (util.today_date() - _dt.timedelta(days=days_ago)).isoformat()


def _clip(text: str, limit: int = NOTE_CHARS) -> str:
    text = " ".join(str(text or "").split()) if len(str(text or "")) > limit else str(text or "")
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _live_notes(st, visible=None) -> list:
    return [n for n in st.index.notes.values()
            if n.live and not st.config.is_focus(n) and n.id != GOALS_ID
            and (visible is None or n.id in visible)]


def _unused(note, use: dict) -> bool:
    """No AI used it in `UNUSED_DAYS` days, though it was there to be used."""
    if note.standing or note.must_hold or not note.added or note.added > _day(UNUSED_DAYS):
        return False
    last = str((use or {}).get("last") or "")
    return not last or last < _day(UNUSED_DAYS)


def flags(note, st, today, use: dict) -> list[str]:
    """What upkeep cares about in one note, in a few words each."""
    out = []
    if note.must_hold:
        out.append("must-hold")
    if note.standing:
        out.append("in every chat")
    stale = note.stale_reason(today, st.config.review_days_for(note))
    if stale:
        out.append(f"stale: {stale}")
    if note.confidence == "disputed":
        out.append("disputed")
    if note.as_of:
        out.append(f"as of {note.as_of}")
    if _unused(note, use):
        out.append(f"unused {UNUSED_DAYS} days")
    if note.added and note.added >= _day(NEW_DAYS):
        out.append("new")
    return out


def _goals(st) -> str:
    note = st.index.note(GOALS_ID)
    return note.body.strip() if note is not None and note.body.strip() else ""


def _projects(st) -> list[dict]:
    out = []
    for focus in st.index.focuses.values():
        state = focus.current()
        out.append({"id": focus.id, "title": focus.title, "status": focus.status,
                    "active": focus.active, "updated": str(state.get("updated") or "")[:10],
                    "current": _clip(str(state.get("current") or ""), 240),
                    "next": _clip(str(state.get("next") or ""), 240)})
    out.sort(key=lambda p: (not p["active"], p["title"].lower()))
    return out


def _skills(brain, st) -> list[dict]:
    used = _usage(brain, "skill")
    out = []
    for skill in sorted(st.index.skills.values(), key=lambda s: (s.category, s.name)):
        use = used.get(skill.name) or {}
        out.append({"name": skill.name, "category": skill.category,
                    "description": _clip(skill.description, 200),
                    "triggers": list(skill.triggers[:4]), "uses_30": int(use.get("d30") or 0),
                    "last_used": str(use.get("last") or "") or None})
    return out


def outline(brain, *, brief: bool = False, visible=None) -> dict:
    """The map: {"counts", "goals", "areas", "projects", "skills", "text"}. `text` is what a
    model reads; `brief` keeps it short for a small model (counts, every flagged note, the
    projects and the skills' names). `visible`: the note ids the reader may see (all when
    None): admission comes before anything else."""
    st = brain.state()
    today = util.today_date()
    used = _usage(brain)
    notes = sorted(_live_notes(st, visible),
                   key=lambda n: (n.area, n.route_key, n.title.lower()))
    areas: dict[str, dict] = {}
    for note in notes:
        area = areas.setdefault(note.area, {"area": note.area,
                                            "label": st.config.area_label(note.area),
                                            "topics": {}})
        topic = area["topics"].setdefault(note.route_key, {
            "topic": note.route_key, "label": st.index.topic_label(note.route_key), "notes": []})
        topic["notes"].append({"id": note.id, "kind": note.kind, "title": note.title,
                               "flags": flags(note, st, today, used.get(note.id) or {})})
    shaped = [{**a, "topics": list(a["topics"].values())} for a in areas.values()]
    projects = [p for p in _projects(st) if visible is None or p["id"] in visible]
    skills = _skills(brain, st)
    goals = _goals(st)
    every = [n for a in shaped for t in a["topics"] for n in t["notes"]]
    counts = {
        "notes": len(every),
        "areas": len(shaped),
        "skills": len(skills),
        "projects": sum(1 for p in projects if p["active"]),
        "waiting": len(st.snapshot.proposals),
        "stale": sum(1 for n in every if any(f.startswith("stale") for f in n["flags"])),
        "unused": sum(1 for n in every if f"unused {UNUSED_DAYS} days" in n["flags"]),
        "disputed": sum(1 for n in every if "disputed" in n["flags"]),
        "must_holds": sum(1 for n in every if "must-hold" in n["flags"]),
    }
    return {"counts": counts, "goals": goals, "areas": shaped, "projects": projects,
            "skills": skills, "text": _render(counts, goals, shaped, projects, skills, brief)}


def _render(counts, goals, areas, projects, skills, brief: bool) -> str:
    lines = [f"# The Brain as it is now (made by code on {util.today_date().isoformat()})", "",
             f"{counts['notes']} live notes in {counts['areas']} areas; {counts['skills']} "
             f"skills; {counts['projects']} active projects; {counts['waiting']} suggestions "
             f"waiting for the owner. Flagged: {counts['stale']} stale, {counts['unused']} unused "
             f"{UNUSED_DAYS} days, {counts['disputed']} disputed; {counts['must_holds']} "
             "must-holds.", "", "## Goals", ""]
    lines.append(_clip(goals, 1500 if not brief else 500) if goals else
                 "Not said yet: the owner has not answered what the Brain is for.")
    lines += ["", "## Notes, by area and topic", "",
              "Each line: `id` [kind] title {flags}."]
    shown = 0
    for area in areas:
        topics = area["topics"]
        total = sum(len(t["notes"]) for t in topics)
        lines += ["", f"### {area['label']} ({total} notes)"]
        for topic in topics:
            listed = [n for n in topic["notes"] if not brief or n["flags"]]
            if not listed:
                continue
            if not brief:
                lines.append(f"#### {topic['label']}")
            for note in listed:
                if brief and shown >= BRIEF_LINES:
                    break
                tail = f" {{{'; '.join(note['flags'])}}}" if note["flags"] else ""
                lines.append(f"- `{note['id']}` [{note['kind']}] {note['title']}{tail}")
                shown += 1
    lines += ["", "## Projects", ""]
    for project in projects:
        line = (f"- `{project['id']}` {project['title']}: {project['status']}, last update "
                f"{project['updated'] or 'never'}")
        if not brief and project["next"]:
            line += f"; next: {project['next']}"
        lines.append(line)
    if not projects:
        lines.append("None yet.")
    lines += ["", "## Skills", ""]
    for skill in skills:
        if brief:
            lines.append(f"- /{skill['name']} ({skill['category']}), used {skill['uses_30']} "
                         "times in 30 days")
            continue
        asks = "; ".join(f'"{t}"' for t in skill["triggers"]) or "no words to ask for it"
        lines.append(f"- /{skill['name']} ({skill['category']}): {skill['description']} "
                     f"Asked for with {asks}. Used {skill['uses_30']} times in 30 days.")
    if not skills:
        lines.append("None yet.")
    return "\n".join(lines).strip() + "\n"


# ------------------------------------------------------------------ what one action reads

def _note_text(note, label: str = "") -> str:
    head = f"{label}`{note.id}` [{note.kind}, {note.route_key}] {note.title}"
    extra = []
    if note.as_of:
        extra.append(f"as of {note.as_of}")
    if note.valid_until:
        extra.append(f"holds until {note.valid_until}")
    if note.verified:
        extra.append(f"last checked {str(note.verified)[:10]}")
    return head + (f" ({'; '.join(extra)})" if extra else "") + "\n" + _clip(note.body)


def gather(brain, action: str, *, limit: int = MAX_CANDIDATES, visible=None) -> dict:
    """The candidates one action judges: {"action", "candidates": [{"ref", "kind", "ids",
    "title", "text"}], "found"}. `found` counts what qualified before the limit. With
    `visible` (the note ids the reader may see), a candidate about any other note is left out."""
    if action not in ACTIONS:
        raise ValueError(f"Unknown action {action!r}: one of {', '.join(ACTIONS)}.")
    limit = max(1, min(int(limit or MAX_CANDIDATES), 25))
    st = brain.state()
    found = _GATHER[action](brain, st)
    if visible is not None:
        notes = st.index.notes
        found = [c for c in found
                 if all(i in visible for i in c["ids"] if i in notes and i != GOALS_ID)]
    out = []
    for number, item in enumerate(found[:limit], 1):
        out.append({"ref": f"c{number}", **item})
    return {"action": action, "candidates": out, "found": len(found)}


def _repeats(brain, st) -> list[dict]:
    from . import review
    notes = st.index.notes
    out = []
    for a, b, score in review.near_duplicates(st):
        left, right = notes.get(a), notes.get(b)
        if left is None or right is None or not (left.live and right.live):
            continue
        out.append({"kind": "pair", "ids": [a, b], "title": f"{left.title} / {right.title}",
                    "text": (_note_text(left, "Note A: ") + "\n\n" + _note_text(right, "Note B: ")
                             + f"\n\nWords in common: {score:.2f}")})
    return out


def _drift(brain, st) -> list[dict]:
    from . import dissent, review
    out, seen = [], set()

    def add(ids, title, text):
        key = tuple(sorted(ids))
        if key not in seen:
            seen.add(key)
            out.append({"kind": "pair" if len(ids) > 1 else "note", "ids": list(ids),
                        "title": title, "text": text})

    for row in review.went_in_disagreements(brain):
        note, other = st.index.note(row["note"]["id"]), st.index.note(row["with"]["id"])
        if note is None or other is None:
            continue
        reading = (row.get("model") or {}).get("detail") or ""
        add([note.id, other.id], f"{note.title} / {other.title}",
            _note_text(note, "Went in on its own: ") + "\n\n" + _note_text(other, "It may contradict: ")
            + (f"\n\nA model read them as contradicting: {reading}" if reading else ""))
    for row in review.dated_pairs(st):
        older, newer = st.index.note(row["older"]["id"]), st.index.note(row["newer"]["id"])
        if older is None or newer is None:
            continue
        add([older.id, newer.id], f"{older.title} (older value)",
            _note_text(older, f"Older value, as of {row['older_as_of']}: ") + "\n\n"
            + _note_text(newer, f"Newer value, as of {row['newer_as_of']}: "))
    try:
        beliefs = dissent.cross_check(brain)
    except Exception:  # the weekly cross-check is evidence, never a reason to fail
        beliefs = []
    for row in beliefs:
        note = st.index.note(row["id"])
        if note is None:
            continue
        evidence = row.get("evidence") or {}
        ids = [note.id] + ([evidence["id"]] if evidence.get("kind") == "note"
                           and st.index.note(evidence["id"]) is not None else [])
        add(ids, note.title,
            _note_text(note, "Belief: ") + f"\n\nSomething in the Brain says otherwise "
            f"({evidence.get('kind', 'note')} `{evidence.get('id', '')}`, "
            f"{evidence.get('title', '')}): {_clip(evidence.get('text', ''), 600)}"
            + (f"\n\nWhy it was flagged: {row['why']}" if row.get("why") else ""))
    return out


def _alignment(brain, st) -> list[dict]:
    used = _usage(brain)
    out = [{"kind": "goals", "ids": [GOALS_ID], "title": "The goals and projects",
            "text": ("The owner's goals:\n" + (_clip(_goals(st), 2500) or "Not said yet.")
                     + "\n\nActive projects:\n" + ("\n".join(
                         f"- `{p['id']}` {p['title']}: {p['current'] or p['status']}"
                         for p in _projects(st) if p["active"]) or "None."))}]
    for note in st.index.notes.values():
        if note.must_hold and note.live and not (note.triggers or note.applies_to):
            out.append({"kind": "note", "ids": [note.id], "title": note.title,
                        "text": _note_text(note, "Must-hold with nothing to bring it up: ")})
    idle = sorted((n for n in _live_notes(st) if _unused(n, used.get(n.id) or {})),
                  key=lambda n: (str((used.get(n.id) or {}).get("last") or ""), n.added))
    for note in idle:
        last = (used.get(note.id) or {}).get("last")
        out.append({"kind": "note", "ids": [note.id], "title": note.title,
                    "text": _note_text(note, f"Unused {UNUSED_DAYS}+ days (last used "
                                             f"{last or 'never'}): ")})
    return out


def _freshness(brain, st) -> list[dict]:
    today = util.today_date()
    used = _usage(brain)
    stale = []
    for note in _live_notes(st):
        why = note.stale_reason(today, st.config.review_days_for(note))
        if why:
            stale.append((note, why))
    stale.sort(key=lambda pair: -int((used.get(pair[0].id) or {}).get("d30") or 0))
    out = [{"kind": "note", "ids": [n.id], "title": n.title,
            "text": _note_text(n, f"Stale ({why}): ")} for n, why in stale]
    seen = {n.id for n, _ in stale}
    unchecked = sorted((n for n in _live_notes(st) if n.id not in seen
                        and str(n.verified or "")[:10] < _day(CHECKED_DAYS)
                        and int((used.get(n.id) or {}).get("d30") or 0) > 0),
                       key=lambda n: -int((used.get(n.id) or {}).get("d30") or 0))
    out += [{"kind": "note", "ids": [n.id], "title": n.title,
             "text": _note_text(n, f"Used {int((used.get(n.id) or {}).get('d30') or 0)} times "
                                   f"this month, not checked in {CHECKED_DAYS} days: ")}
            for n in unchecked]
    return out


RESTING = ("paused", "on hold", "on-hold", "waiting", "parked")  # quiet on purpose


def _projects_to_check(brain, st) -> list[dict]:
    out = []
    for focus in st.index.focuses.values():
        if not focus.active or focus.status.strip().lower() in RESTING:
            continue
        state = focus.current()
        updated = str(state.get("updated") or "")[:10]
        quiet = not updated or updated < _day(QUIET_DAYS)
        if not quiet and str(state.get("next") or "").strip():
            continue
        recent = "\n".join(f"- {u.at[:10]}: {_clip(u.summary, 200)}"
                           for u in focus.updates[-3:]) or "- none"
        why = (f"no update since {updated or 'it began'}" if quiet else "no next steps")
        out.append({"kind": "project", "ids": [focus.id], "title": focus.title,
                    "text": (f"Project `{focus.id}` {focus.title} ({why})\nStatus: {focus.status}"
                             f"\nWhere it stands: {_clip(state.get('current') or '', 400) or 'not said'}"
                             f"\nNext steps: {_clip(state.get('next') or '', 400) or 'none'}"
                             f"\nLast updates:\n{recent}")})
    out.sort(key=lambda c: c["text"])
    return out


def _skills_to_check(brain, st) -> list[dict]:
    rows = {s["name"]: s for s in _skills(brain, st)}
    out = []
    phrases: dict[str, list[str]] = {}
    for skill in st.index.skills.values():
        for trigger in skill.triggers:
            phrases.setdefault(" ".join(trigger.lower().split()), []).append(skill.name)

    def text(name: str) -> str:
        row = rows[name]
        asks = "; ".join(f'"{t}"' for t in st.index.skills[name].triggers) or "none"
        return (f"/{name} ({row['category']}): {row['description']}\nAsked for with: {asks}\n"
                f"Used {row['uses_30']} times in 30 days; last used {row['last_used'] or 'never'}")

    for phrase, names in sorted(phrases.items()):
        names = sorted(set(names))
        if len(names) > 1:
            out.append({"kind": "pair", "ids": names[:2], "title": f'"{phrase}"',
                        "text": f'Both are asked for with "{phrase}":\n\n'
                                + "\n\n".join(text(n) for n in names[:2])})
    for name, row in rows.items():
        skill = st.index.skills[name]
        idle = row["uses_30"] == 0 and (not row["last_used"]
                                        or row["last_used"] < _day(SKILL_IDLE_DAYS))
        if not skill.triggers:
            out.append({"kind": "skill", "ids": [name], "title": f"/{name}",
                        "text": "No words to ask for it:\n" + text(name)})
        elif idle:
            out.append({"kind": "skill", "ids": [name], "title": f"/{name}",
                        "text": f"No AI used it in {SKILL_IDLE_DAYS} days:\n" + text(name)})
    return out


def _gaps(brain, st) -> list[dict]:
    try:
        rows = brain.gaps(days=30).data.get("gaps") or []
    except Exception:  # an unreadable ledger has no gaps
        rows = []
    out = []
    for row in rows:
        request = " ".join(str(row.get("request") or "").split())
        if not request:
            continue
        close = ", ".join(f"`{c['id']}` {c['title']}" for c in row.get("close") or [])
        how = ("the AI searched and found " + f"`{row['entry']}` {row.get('entry_title') or ''}"
               if row.get("kind") == "searched" and row.get("entry") else "nothing in the Brain fit")
        out.append({"kind": "gap", "ids": [str(row.get("key") or request)], "title": request[:80],
                    "text": f"Asked: {_clip(request, 600)}\nWhat happened: {how}"
                            + (f"\nClosest notes: {close}" if close else "")})
    return out


_GATHER = {
    "tidy-repeats": _repeats,
    "check-drift": _drift,
    "check-alignment": _alignment,
    "freshen-up": _freshness,
    "tidy-projects": _projects_to_check,
    "tidy-skills": _skills_to_check,
    "fill-gaps": _gaps,
}
