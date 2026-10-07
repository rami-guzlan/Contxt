"""Focus items: ongoing work with a governed baseline and an append-only journal.

The baseline is an ordinary `state/focus` note (reviewed like any knowledge). Progress goes
to `journal/focus/<focus id>.jsonl`, one JSON object per update, never rewritten. The
current state is the baseline overlaid with every update's changes, last write wins, so the
history of how a Focus got here is always recoverable line by line.
"""
from __future__ import annotations

from . import util
from .scopes import Scopes

STATE_FIELDS = ("status", "current", "blockers", "next", "completed", "decisions")


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _visible(brain, principal=None, partition=None):
    caller = brain.caller(principal, None, partition)
    if not isinstance(caller, tuple):
        return None, caller
    chain, partitions = caller
    st = brain.state()
    return [f for f in st.index.focuses.values()
            if Scopes.admits(f.note.scope, f.note.partition, chain, partitions)], None


def resolve(brain, name, principal=None, partition=None):
    focuses, refusal = _visible(brain, principal, partition)
    if refusal:
        return None, refusal
    key = util.normalize(name)
    target = brain.state().config.aliases.get(str(name or "").strip())
    exact = [f for f in focuses
             if key in {util.normalize(v) for v in [f.id, f.slug, f.title] + f.aliases}
             or (target and f.id == target)]
    if len(exact) == 1:
        return exact[0], None
    partial = [f for f in focuses if key and key in util.normalize(f"{f.id} {f.title}")]
    if len(partial) == 1:
        return partial[0], None
    if not exact and not partial:
        return None, _result(f"No visible Focus named {name!r}.", {"status": "missing"}, True)
    names = ", ".join(f.id for f in (exact or partial))
    return None, _result(f"{name!r} is ambiguous: {names}.", {"status": "ambiguous"}, True)


def _row(focus):
    state = focus.current()
    return {"id": focus.id, "title": focus.title, "scope": focus.note.scope,
            "status": state.get("status"), "current": state.get("current"),
            "blockers": state.get("blockers"), "next": state.get("next"),
            "updated": state.get("updated"), "updates": len(focus.updates),
            "active": focus.active, "summary": focus.note.index_line}


def list_focuses(brain, *, principal=None, status=None, partition=None, **_ignored):
    focuses, refusal = _visible(brain, principal, partition)
    if refusal:
        return refusal
    rows = [_row(f) for f in focuses]
    if status:
        rows = [r for r in rows if str(r["status"]).lower() == str(status).lower()]
    rows.sort(key=lambda r: str(r["updated"] or ""), reverse=True)
    rows.sort(key=lambda r: not r["active"])  # stable: active first, newest first
    text = "\n".join(f"- `{r['id']}` [{r['status']}] {r['title']}: "
                     f"{util.excerpt(r['current'] or r['summary'], 120)}" for r in rows)
    return _result(text or "No visible Focus items.", {"focuses": rows})


def get_focus(brain, name, *, principal=None, partition=None, limit=10, **_ignored):
    focus, refusal = resolve(brain, name, principal, partition)
    if refusal:
        return refusal
    row = _row(focus)
    lines = [f"# {focus.title} (`{focus.id}`) [{row['status']}]", "",
             f"Scope: {focus.note.scope}", ""]
    for label, key in (("Current", "current"), ("Blockers", "blockers"), ("Next", "next")):
        if row.get(key):
            lines.append(f"{label}: {row[key]}")
    lines += ["", "## Baseline", "", focus.note.body.strip(), ""]
    if focus.updates:
        lines += ["## Journal (newest first)", ""]
        for update in focus.updates[::-1][:int(limit or 10)]:
            lines.append(f"- {update.at} #{update.seq}: {update.summary}")
    return _result("\n".join(lines).rstrip() + "\n", {
        "focus": row, "baseline": focus.note.body, "meta": focus.note.meta,
        "updates": [u.__dict__ for u in focus.updates]})


def record_update(brain, name, summary, changes=None, *, principal=None, evidence="",
                  session_id=None, partition=None, **_ignored):
    """Append one progress snapshot. No approval: the journal is append-only history."""
    summary = str(summary or "").strip()
    if not summary:
        return _result("A Focus update needs a one-line summary.", {"status": "invalid"}, True)
    focus, refusal = resolve(brain, name, principal, partition)
    if refusal:
        return refusal
    if changes is not None and not isinstance(changes, dict):
        return _result("changes must be an object such as {\"next\": \"...\"}.",
                       {"status": "invalid"}, True)
    clean = {}
    for key, value in (changes or {}).items():
        key = {"project_status": "status", "focus_status": "status",
               "current_state": "current", "next_actions": "next",
               "next_action": "next"}.get(str(key), str(key))
        if isinstance(value, (list, tuple)):
            value = "; ".join(str(v).strip() for v in value if str(v).strip())
        if value is None or str(value).strip() == "":
            continue
        clean[key] = str(value).strip()
    who = brain.principal(principal)
    record = {"seq": len(focus.updates) + 1, "at": util.now_iso(), "summary": summary,
              "changes": clean, "evidence": str(evidence or "").strip(),
              "session": str(session_id or ""), "actor": who}
    relpath = brain.vault.append_focus_update(focus.id, record)
    outcome = brain.after_write([brain.vault.path(relpath)],
                                f"Focus {focus.id}: {util.excerpt(summary, 60)}")
    return _result(f"Recorded update #{record['seq']} on {focus.id}: {summary}",
                   {"status": "recorded", "focus": focus.id, "seq": record["seq"],
                    "changes": clean, "commit": outcome.get("commit")})


def create_focus(brain, name, summary, *, principal=None, status="active", scope=None,
                 participants=None, pinned_notes=None, pinned_skills=None, outputs=None,
                 aliases=None, session_id=None, **_ignored):
    """Propose a new Focus baseline. Inside your own scope it applies immediately.

    `aliases` are the other names people will call it by ("the campaign proposals"); a
    request that uses one brings the project's state and files."""
    from . import governance
    name = str(name or "").strip()
    summary = str(summary or "").strip()
    if not name or not summary:
        return _result("create_focus needs a name and a summary.", {"status": "invalid"}, True)
    st = brain.state()
    config = st.config
    if config.uses_areas:
        # A project gets its own folder; its decisions and client notes can live beside it.
        area, topic = config.focus_area, util.slugify(name, 48)
        note_id = topic
    else:
        focus_cfg = config.structure.get("focus") or {}
        area, topic = focus_cfg.get("layer", "state"), focus_cfg.get("topic", "focus")
        note_id = f"{area}-{topic}-{util.slugify(name, 48)}"
    existing = st.index.note(note_id)
    if existing is not None and config.is_focus(existing):
        return _result(f"A Focus {note_id} already exists; record an update instead.",
                       {"status": "exists", "id": note_id}, True)
    if existing is not None or note_id in st.index.archived:
        note_id = f"{note_id}-project"
    who = brain.principal(principal)
    extra = {"project": name, "project_status": status or "active", "owner": who}
    if not config.uses_areas:
        extra["index_line"] = util.excerpt(summary, 110)
    if participants:
        extra["participants"] = list(participants)
    if pinned_notes:
        extra["pinned_notes"] = list(pinned_notes)
    if pinned_skills:
        extra["pinned_skills"] = list(pinned_skills)
    if outputs:
        extra["outputs"] = outputs
    names = aliases if isinstance(aliases, (list, tuple)) else (
        [a for a in str(aliases or "").split(",")])
    names = list(dict.fromkeys(" ".join(str(a).split()) for a in names
                               if str(a or "").strip() and util.normalize(str(a))
                               != util.normalize(name)))
    if names:
        extra["aliases"] = names[:12]
    return governance.propose_note(
        brain, area=area, topic=topic, text=summary, scope=scope or who, principal=who,
        note_id=note_id, title=name, summary=util.excerpt(summary, 110),
        source=f"created by {who}", evidence="create_focus", kind="focus.create",
        extra=extra, session_id=session_id)
