"""Learning from use (general-retrieval plan 3.5): the Brain's text improves where briefs
fell short, the same way in every Brain, without an engineer.

The ledger knows when a conversation opened a note that none of its briefs brought or listed
(a "searched" gap, Ledger.gaps): the person asked in words the note was not found by. That
request's wording joins the note's `asked_as`, so the next request like it finds the note:

- in a conversation of the Brain's owner, at once, as one undo point per note;
- in anyone else's, it waits on the note as `suggested_asked_as` for the owner's yes
  (`accept_asked_as`), as trigger words a model suggests for a must-hold do.

A gap that taught its note is dismissed, so it is learned once. The ranking stays the same
code for everyone: only the Brain's text changes.

`pointer_report` lists notes that briefs listed as pointers and conversations opened most
times: the sign a note should come whole, for the owner to read.
"""
from __future__ import annotations

import datetime as dt

from . import enrich, util

MAX_WORDS = 24
OPENED_SHARE = 0.5
MIN_LISTED = 3


def wording(request: str) -> str:
    """A request as a way to ask: its first sentence, at most MAX_WORDS words."""
    text = " ".join(str(request or "").split())
    for stop in (". ", "? ", "! ", "\n"):
        head, sep, _rest = text.partition(stop)
        if sep and len(head.split()) >= 3:
            text = head + sep.strip()
            break
    words = text.split()
    return enrich._clean(" ".join(words[:MAX_WORDS]))


def _known(note, line: str) -> bool:
    have = {" ".join(x.lower().split()) for x in [*note.asked_as,
                                                  *(note.meta.get("suggested_asked_as") or [])]}
    return " ".join(line.lower().split()) in have


def _owners(brain, since: str) -> dict[str, bool]:
    """{session id: was it the owner's own conversation?}: its briefs say whose scope they
    served (the last person in their scope chain)."""
    owner = brain.state().config.owner
    out: dict[str, bool] = {}
    for row in brain.ledger.packet_rows(since):
        chain = (row.get("data") or {}).get("scope_chain") or []
        people = [s for s in chain if str(s).startswith("person:")]
        out[str(row.get("session_id"))] = not people or people[-1] == owner
    return out


def from_gaps(brain, *, days: int = 30) -> dict:
    """Teach each note a conversation had to search for the words it was asked in."""
    from . import governance
    since = (util.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    learned, suggested, skipped = [], [], []
    owners = _owners(brain, since)
    for gap in brain.ledger.gaps(since):
        if gap.get("kind") != "searched" or not gap.get("entry"):
            continue
        note = brain.state().index.note(gap["entry"])
        line = wording(gap.get("request") or "")
        if note is None or not note.live or note.standing or len(line.split()) < 3 \
                or _known(note, line):
            skipped.append(gap["key"])
            brain.ledger.dismiss(gap["key"])
            continue
        meta = dict(note.meta)
        if owners.get(str(gap.get("session_id")), False):
            asked = note.asked_as
            if len(asked) >= enrich.MAX_ASKED:
                asked = asked[1:]  # the oldest way to ask makes room
            meta["asked_as"] = [*asked, line]
            meta.setdefault("enriched_hash", enrich.text_hash(note))
            outcome = governance._freshness_write(
                brain, note, meta, "learned from use",
                {"action": "learned", "asked_as": line}, f"Learned how {note.id} is asked for")
            (learned if not outcome.is_error else skipped).append(note.id)
        else:
            meta["suggested_asked_as"] = [*(note.meta.get("suggested_asked_as") or []), line]
            outcome = governance._freshness_write(
                brain, note, meta, "learned from use",
                {"action": "asked-as-suggested", "asked_as": line},
                f"Suggested a way to ask for {note.id}")
            (suggested if not outcome.is_error else skipped).append(note.id)
        brain.ledger.dismiss(gap["key"])
    return {"learned": learned, "suggested": suggested, "skipped": len(skipped)}


def accept_asked_as(brain, note_id: str, *, actor=None) -> dict:
    """The owner's yes to the ways of asking learned from other people's conversations."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    note = brain.state().index.note(note_id)
    waiting = list(note.meta.get("suggested_asked_as") or []) if note is not None else []
    if note is None or not waiting:
        return governance._result(f"{note_id} has no suggested ways to ask to accept.",
                                  {"status": "missing"}, True)
    meta = dict(note.meta)
    meta["asked_as"] = list(dict.fromkeys([*note.asked_as, *waiting]))[-enrich.MAX_ASKED:]
    meta.pop("suggested_asked_as", None)
    return governance._freshness_write(
        brain, note, meta, who, {"action": "asked-as-accepted", "asked_as": len(waiting)},
        f"Accepted the ways to ask for {note.id}")


def pointer_report(brain, *, days: int = 30) -> list[dict]:
    """Notes listed as pointers at least MIN_LISTED times and opened in most of those
    conversations: they should probably come whole."""
    since = (util.now() - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    listed: dict[str, set] = {}
    for row in brain.ledger.packet_rows(since):
        for note_id in (row.get("data") or {}).get("related_ids") or []:
            listed.setdefault(note_id, set()).add(row.get("session_id"))
    opened = brain.ledger.opened_notes(since)
    out = []
    for note_id, sessions in listed.items():
        hits = len(sessions & set(opened.get(note_id) or ()))
        if len(sessions) >= MIN_LISTED and hits / len(sessions) >= OPENED_SHARE:
            out.append({"id": note_id, "listed": len(sessions), "opened": hits})
    return sorted(out, key=lambda r: (-r["opened"], r["id"]))
