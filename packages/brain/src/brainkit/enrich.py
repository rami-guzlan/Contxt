"""Enrichment at the door (general-retrieval plan 3.1): one model call per note writes how a
person would ask for it, when it applies and when it does not, and what part it plays.

What a person once wrote by hand for routing (topics.md lines, `requires_any`, intents,
trigger words, house-style lists) comes from each note itself, so a Brain nobody tuned is
found as well as one somebody did. The fields are part of the note, versioned with it and
shown on its page ("Found when you ask"), where the owner can change them:

    asked_as        6 to 8 ways a person would ask for this note, in plain words
    applies_when    one line: the work this note is for
    not_when        one line: look-alike work it is not for
    role            knowledge, rule, style (how to write, not what), procedure or pointer
    enriched        the date, and enriched_by (the model) and enriched_hash (of the text it
                    read: when the note's text changes, it is enriched again)

For a must-hold, the words people use when doing the work it governs come back as
`suggested_triggers`: they wait for the owner's yes (`accept_triggers`), like the rule.

The engine writes the prompt and reads the answer; the app's knowledge agent asks the model
the person chose. Without a model, notes are found by their own text, as before.
"""
from __future__ import annotations

import json
import re

from . import util

ROLES = ("knowledge", "rule", "style", "procedure", "pointer")
MIN_ASKED, MAX_ASKED = 3, 10
LINE_MAX = 140
TRIGGERS_MAX = 12
BODY_CHARS = 2400

PROMPT = """You write the retrieval lines for one note in a person's Brain (their long-term \
notes), so their AI assistant finds this note when it is needed, and only then.

The note
Title: {title}
Summary: {summary}
Filed under: {place}
Kind: {kind}
{must}Text:
{body}

Return only a JSON object, nothing else:
{{"asked_as": [6 to 8 requests this person might type to their AI assistant when this note \
should be in front of it: questions it answers, writing or planning it shapes, decisions it \
settles. Plain everyday wording, each under 15 words, varied, mostly in words the note does \
not use],
 "applies_when": "one line: the work this note is for",
 "not_when": "one line: look-alike work it is not for",
 "role": "knowledge, rule, style, procedure or pointer"{triggers}}}

Roles: rule is a constraint on what to do; style is how to write or present, not what to \
say; procedure is steps to follow; pointer says where something is or who to ask; knowledge \
is everything else. Use only what the note says: no new facts, names or numbers. No dashes \
between clauses."""

TRIGGERS = (',\n "triggers": [5 to 10 words or short phrases people use when doing the work '
            'this rule governs, without naming the rule]')
MUST = "This note is a rule that must always hold in its domain: {rule}\n"


def text_hash(note) -> str:
    return util.sha256(f"{note.title}\n{note.summary}\n{note.body}")[:16]


def version(note) -> str:
    """A model response must not overwrite either edited text or an owner's new hints."""
    return util.sha256(json.dumps({"meta": note.meta, "body": note.body},
                                  sort_keys=True, ensure_ascii=False, default=str))


def current(note) -> bool:
    """Owner-written legacy hints remain usable; generated hints belong to one text version."""
    recorded = str(note.meta.get("enriched_hash") or "")
    return not recorded or recorded == text_hash(note)


def needs(note) -> bool:
    """No retrieval lines yet, or the note's text changed since they were written."""
    if not note.live or note.standing:
        return False
    return not note.asked_as or str(note.meta.get("enriched_hash") or "") != text_hash(note)


def pending(index, limit: int | None = None) -> list:
    """The notes that need enrichment, newest first."""
    notes = sorted((n for n in index.notes.values() if needs(n)),
                   key=lambda n: (str(n.meta.get("added") or ""), n.id), reverse=True)
    return notes[:limit] if limit else notes


def prompt_for(note) -> str:
    must = MUST.format(rule=note.must_text) if note.must_hold and note.must_text else ""
    return PROMPT.format(
        title=note.title, summary=note.summary or "(none)",
        place=note.route_key.replace("/", " / "), kind=note.kind, must=must,
        body=util.excerpt(note.body, BODY_CHARS) if len(note.body) > BODY_CHARS else note.body,
        triggers=TRIGGERS if note.must_hold else "")


def _clean(line) -> str:
    text = " ".join(str(line or "").replace("—", ", ").replace("–", ", ").split())
    return text.strip(" ,;")[:LINE_MAX].strip()


def parse(answer: str, *, must_hold: bool = False) -> dict:
    """The fields from a model's answer. Raises ValueError, in plain words, when it holds
    none that can be used."""
    match = re.search(r"\{.*\}", answer or "", re.S)
    if not match:
        raise ValueError("The answer held no JSON object.")
    try:
        data = json.loads(match.group(0))
    except ValueError as exc:
        raise ValueError(f"The answer's JSON did not read: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("The answer's JSON was not an object.")
    raw = data.get("asked_as")
    asked = list(dict.fromkeys(
        c for c in (_clean(x) for x in (raw if isinstance(raw, list) else [])) if c))
    if len(asked) < MIN_ASKED:
        raise ValueError(f"The answer held {len(asked)} ways to ask; at least {MIN_ASKED}.")
    role = _clean(data.get("role")).lower()
    out = {"asked_as": asked[:MAX_ASKED],
           "applies_when": _clean(data.get("applies_when")),
           "not_when": _clean(data.get("not_when")),
           "role": role if role in ROLES else "knowledge"}
    if must_hold:
        triggers = data.get("triggers")
        out["triggers"] = list(dict.fromkeys(
            c.lower() for c in (_clean(x) for x in (
                triggers if isinstance(triggers, list) else [])) if c))[:TRIGGERS_MAX]
    return out


def fields_for(note, found: dict, *, by: str) -> dict:
    """The note's front matter with the enrichment in it."""
    meta = dict(note.meta)
    for key in ("asked_as", "applies_when", "not_when", "role"):
        if found.get(key):
            meta[key] = found[key]
        else:
            meta.pop(key, None)
    if note.must_hold and found.get("triggers"):
        suggested = [t for t in found["triggers"] if t not in set(note.triggers)]
        if suggested:
            meta["suggested_triggers"] = suggested
    meta["enriched"] = util.today()
    meta["enriched_by"] = by
    meta["enriched_hash"] = text_hash(note)
    return meta


def apply(brain, note_id: str, answer: str, *, by: str,
          expected_version: str | None = None) -> dict:
    """Read one model answer and write it into the note: one undo point."""
    from . import governance
    note = brain.state().index.note(note_id)
    if note is None or not note.live:
        return governance._result(f"No live note {note_id!r} to enrich.",
                                  {"status": "missing"}, True)
    if expected_version is not None and expected_version != version(note):
        return governance._result(
            "This note changed while its retrieval lines were being written. "
            "Try again with the current note.",
            {"status": "changed", "id": note_id}, True)
    try:
        found = parse(answer, must_hold=note.must_hold)
    except ValueError as exc:
        return governance._result(f"Could not use the answer for {note_id}: {exc}",
                                  {"status": "unreadable", "id": note_id}, True)
    meta = fields_for(note, found, by=by)
    return governance._freshness_write(
        brain, note, meta, by, {"action": "enriched", "asked_as": len(found["asked_as"])},
        f"Wrote how {note.id} is asked for")


def set_asked_as(brain, note_id: str, lines, *, actor=None) -> dict:
    """The owner's own wording of how this note is asked for (an empty list clears it)."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    note = brain.state().index.note(note_id)
    if note is None or not note.live:
        return governance._result(f"No live note {note_id!r}.", {"status": "missing"}, True)
    asked = list(dict.fromkeys(c for c in (_clean(x) for x in lines or []) if c))[:MAX_ASKED]
    meta = dict(note.meta)
    if not current(note):
        for key in ("applies_when", "not_when", "role"):
            meta.pop(key, None)
    if asked:
        meta["asked_as"] = asked
        meta["enriched_hash"] = text_hash(note)
    else:
        meta.pop("asked_as", None)
    return governance._freshness_write(
        brain, note, meta, who, {"action": "asked-as-edited", "asked_as": len(asked)},
        f"Changed how {note.id} is asked for")


def accept_triggers(brain, note_id: str, *, actor=None) -> dict:
    """The owner's yes to the trigger words the model suggested for a must-hold."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    note = brain.state().index.note(note_id)
    suggested = list(note.meta.get("suggested_triggers") or []) if note is not None else []
    if note is None or not note.must_hold or not suggested:
        return governance._result(f"{note_id} has no suggested trigger words to accept.",
                                  {"status": "missing"}, True)
    meta = dict(note.meta)
    meta["triggers"] = list(dict.fromkeys([*note.triggers, *suggested]))
    meta.pop("suggested_triggers", None)
    return governance._freshness_write(
        brain, note, meta, who, {"action": "triggers-accepted", "triggers": meta["triggers"]},
        f"Accepted the trigger words for {note.id}")
