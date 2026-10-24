"""Lore: lessons, a kind beside fact, rule, preference and decision (v4 spec, section 6).

A lesson is a short story, the pattern it warns about, and the words that bring it up. It is a
note of kind `lesson`, loaded `manual` so ordinary routing never sends it, with three parts:

    ## Story      what happened
    ## Pattern    the pattern it warns about
    ## Words      the words that bring it up, separated by commas

A request that uses one of a lesson's words brings it up: the first time in a conversation it
goes in full, after that by name only (the session ledger keeps what each conversation got).
A lesson is proposed like any other note (`lore_propose`) and waits in Catch up, or goes in
on its own where the owner's governance lets it.
"""
from __future__ import annotations

import re

from . import addresses, levels, util
from .scopes import Scopes

KIND = "lesson"
TOPIC = "lore"
PER_REQUEST = 2      # lessons a packet brings up at most
WORD_MAX = 6         # a word that brings a lesson up is a word or a short phrase
_SEP = re.compile(r"\s*(?:[,;·\n]|\s\|\s)\s*")


def is_lesson(note) -> bool:
    return note.kind == KIND


def parts(note) -> dict:
    """A lesson's story, pattern and words, read from its text."""
    found = {p["slug"]: p["text"] for p in addresses.split(note.body)}
    words = [w.strip().strip("\"'“”").lower() for w in _SEP.split(found.get("words", ""))]
    words += [str(w).strip().lower() for w in note.meta.get("words") or []
              if isinstance(w, str)]
    return {"story": found.get("story", "").strip(),
            "pattern": found.get("pattern", "").strip(),
            "words": list(dict.fromkeys(w for w in words if w))}


def row(note) -> dict:
    """One lesson as the shelf, the map and `lore_list` show it."""
    found = parts(note)
    level = levels.of(note)
    return {"id": note.id, "title": note.title or note.id, "story": found["story"],
            "pattern": found["pattern"], "words": found["words"], "level": level,
            "level_label": levels.label(level), "address": f"{note.id}#story",
            "sections": [f"{note.id}#{s}" for s in ("story", "pattern", "words")],
            "added": note.added, "scope": note.scope}


def visible(st, chain, partitions) -> list:
    """The lessons the caller may see, newest first."""
    notes = [n for n in st.index.notes.values()
             if is_lesson(n) and Scopes.admits(n.scope, n.partition, chain, partitions)]
    return sorted(notes, key=lambda n: (str(n.added or ""), n.id), reverse=True)


def brought_up(st, request: str, chain, partitions, limit: int = PER_REQUEST) -> list:
    """The lessons whose words the request uses, most words first."""
    text = util.normalize(request)
    scored = []
    for note in visible(st, chain, partitions):
        hits = [w for w in parts(note)["words"] if util.phrase_in(w, text)]
        if hits:
            scored.append((len(hits), note, hits))
    scored.sort(key=lambda s: (-s[0], s[1].id))
    return [(note, hits) for _n, note, hits in scored[:limit]]


def block(found, delivered: dict) -> tuple[str, list, dict]:
    """The packet's lore: each lesson in full the first time in this conversation, then by
    name only. Returns (text, delivery items, data)."""
    full, named, items = [], [], []
    data: dict = {"lessons_full": [], "lessons_named": [], "lesson_tokens": {}}
    for note, hits in found:
        held = delivered.get(("lesson", note.id))
        if held and note.body_hash in held.get("hashes", {held.get("hash")}):
            at = str(held.get("at") or "")
            when = f", sent in full at {at[11:16]}" if len(at) >= 16 else ""
            named.append(f"- {note.title} (`{note.id}#story`) {levels.tag(note)}, by name "
                         f"only{when}")
            data["lessons_named"].append(note.id)
            continue
        found_parts = parts(note)
        full += [f"## Lesson: {note.title}   {levels.tag(note)}",
                 f"Story: {found_parts['story']}",
                 f"Watch for: {found_parts['pattern']}",
                 "Brought up by: " + ", ".join(hits) + ".",
                 "Sent in full once this conversation; later requests name it only. Apply "
                 f"it; do not retell it unless asked. Section: `{note.id}#story`", ""]
        text = "\n".join(full[-6:])
        items.append(("lesson", note.id, note.body_hash, util.tokens(text)))
        data["lesson_tokens"][note.id] = util.tokens(text)
        data["lessons_full"].append(note.id)
    lines = list(full)
    if named:
        lines += ["## Lessons already given this conversation", *named, ""]
    return "\n".join(lines).strip(), items, data


def body(story: str, pattern: str, words) -> str:
    return (f"## Story\n\n{story.strip()}\n\n## Pattern\n\n{pattern.strip()}\n\n"
            f"## Words\n\n{', '.join(words)}\n")


def problems(title, story, pattern, words) -> list[str]:
    out = []
    if not str(title or "").strip():
        out.append("a lesson needs a title")
    if not str(story or "").strip():
        out.append("a lesson needs its story")
    if not str(pattern or "").strip():
        out.append("a lesson needs the pattern it warns about")
    if not words:
        out.append("a lesson needs at least one word that brings it up")
    long = [w for w in words if len(w.split()) > WORD_MAX or len(w) > 60]
    if long:
        out.append("each word that brings a lesson up is a word or a short phrase: "
                   + ", ".join(repr(w) for w in long))
    return out


def words_of(raw) -> list[str]:
    if isinstance(raw, str):
        raw = _SEP.split(raw)
    return list(dict.fromkeys(str(w).strip().lower() for w in raw or [] if str(w).strip()))


def propose(brain, *, title, story, pattern, words, evidence="", source="", area=None,
            scope=None, session_id=None, op_id=None, capture_origin="chat"):
    """A lesson, proposed like any other note: it waits in Catch up (Keep, Edit first,
    Skip), or goes in on its own where the owner's governance lets it."""
    from . import governance
    from .api import error
    words = words_of(words)
    found = problems(title, story, pattern, words)
    if found:
        return error("Lesson not proposed: " + "; ".join(found) + ".", status="invalid",
                     problems=found)
    config = brain.state().config
    area = area or next(iter(config.area_order()), None)
    return governance.propose_note(
        brain, area=area, topic=TOPIC, text=body(story, pattern, words),
        title=str(title).strip(), summary=str(pattern).strip(), note_kind=KIND,
        load="manual", scope=scope, evidence=evidence, source=source,
        note_id="lore_" + util.slugify(title, 50).replace("-", "_"),
        session_id=session_id, capture_origin=capture_origin, op_id=op_id)
