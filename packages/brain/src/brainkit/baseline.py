"""Baselines: the notes a change must not quietly overturn.

A note is a baseline when any of these holds (`why`):

    marked     the owner marked it a baseline (`baseline: true`)
    load       it goes into every brief of its domain (a must-hold) or every conversation
               (standing)
    kind       it is a rule, or says who someone is (identity)
    checked    it is confirmed and the owner approved it
    use        AIs used it in BASELINE_USES or more conversations in the last 30 days

WHAT A PROPOSAL IS CHECKED AGAINST (`candidates`): the notes most relevant to it (the top
five at RELEVANT or more), every baseline in its area, topic or domains, and every note that
gives a figure for the same subject, wherever it is filed. Checks 1 and 2 (tension.py) read
each pair; a model reading the same pairs (check 3) runs in the app afterwards, and its
verdicts are kept in the ledger by the two texts (`pair_key`).

A CHANGE THAT WOULD APPLY AT ONCE (the owner's own scope, or a capture the policy lets in) is
checked first (`guard`): one that may disagree with a note, or that changes or retires a
baseline, waits for the owner instead.

A REVISION of a baseline needs a reason of a few words, not the one given last time
(`reason_problem`), and the journal records it. A revision of a rule, a standing note or a
must-hold comes with its impact (`impact`): the conversations it went into in 30 days, the
latest requests that received it, and the domains a must-hold covers.
"""
from __future__ import annotations

import datetime as _dt
import re

from . import frontmatter as fm
from . import tension, util

BASELINE_USES = 10     # conversations in the last USE_DAYS that make a note a baseline
USE_DAYS = 30
RELEVANT = 0.45        # router relevance that makes a note worth checking against
RELEVANT_TOP = 5
RECENT_REQUESTS = 3
REASON_WORDS = 4       # a baseline revision's reason, at least this many words
MODEL_PAIRS = 8        # pairs per proposal a model reads, most relevant first

_SUBJECTS: dict[tuple[str, str], list[set[str]]] = {}


def owners(config) -> set[str]:
    approver = config.governance.get("approver") or config.owner
    return {approver} | set(config.governance.get("approvers") or [])


def uses(brain) -> dict[str, int]:
    """{note id: conversations it went into in the last 30 days}, counted by day, as a note
    or as a must-hold's line (the larger of the two, so nothing is counted twice)."""
    since = (util.now().date() - _dt.timedelta(days=USE_DAYS - 1)).isoformat()
    try:
        ledger = brain.ledger
        notes, musts = ledger.usage(since, "note"), ledger.usage(since, "must")
    except Exception:  # no ledger (a read-only copy): use says nothing
        return {}
    return {item: max(notes.get(item, 0), musts.get(item, 0))
            for item in set(notes) | set(musts)}


def why(note, config, used: int = 0) -> str | None:
    """Why a note is a baseline, in plain words, or None."""
    if note is None or not note.live or config.is_focus(note):
        return None
    if fm.as_bool(note.meta.get("baseline")):
        return "you marked it a baseline"
    if note.must_hold:
        return "it is a must-hold"
    if note.standing:
        return "it goes into every conversation"
    if note.kind == "rule":
        return "it is a rule"
    if note.kind == "identity":
        return "it says who you are"
    # Confirmed, and by the owner: they approved it, or checked it themselves (only an
    # approver can verify a note).
    if note.confidence == "confirmed" and (
            str(note.meta.get("approved_by") or "") in owners(config)
            or str(note.meta.get("verified") or "").strip()):
        return "you confirmed it"
    if used >= BASELINE_USES:
        return f"AIs used it in {used} conversations this month"
    return None


def weighty(note) -> bool:
    """A revision of this note shows its impact first: it shapes how every AI works."""
    return note.kind == "rule" or note.must_hold or note.standing


def impact(brain, note) -> dict:
    """How far a revision would reach: conversations in 30 days, the latest requests that
    received the note, and for a must-hold the domains it covers."""
    try:
        reach = brain.ledger.reach(note.id, days=USE_DAYS, limit=RECENT_REQUESTS)
    except Exception:
        reach = {"conversations": 0, "recent": []}
    return {"conversations": reach["conversations"], "recent": reach["recent"],
            "domains": list(note.applies_to) if note.must_hold else []}


def _subjects(note) -> list[set[str]]:
    key = (note.id, note.body_hash)
    found = _SUBJECTS.get(key)
    if found is None:
        if len(_SUBJECTS) > 5000:
            _SUBJECTS.clear()
        found = _SUBJECTS[key] = tension.figure_subjects(note.body)
    return found


def _covers(note, area: str, route_key: str) -> bool:
    """A baseline that holds where a proposal goes: filed in its area, or a must-hold whose
    domains take in its area or topic."""
    if note.area == area:
        return True
    domains = set(note.applies_to) if note.must_hold else set()
    return bool(domains & {"*", area, route_key})


def candidates(brain, text, *, area, topic, chain, partitions=(), exclude=()) -> list[dict]:
    """The notes a proposal's text is checked against, most relevant first: [{"note",
    "score", "found_by", "baseline"}]."""
    st = brain.state()
    config = st.config
    skip = {i for i in exclude if i}
    notes = [n for n in st.router.admitted_notes(chain, partitions)
             if n.id not in skip and not config.is_focus(n)]
    used = uses(brain)
    ranked = st.router.score_notes(text, notes)
    # Every candidate keeps its relevance, so the ones a model reads first (MODEL_PAIRS) are
    # the closest, whichever way they were found.
    scores = {s.item.id: round(s.score, 3) for s in ranked}
    out: dict[str, dict] = {}
    for scored in ranked[:RELEVANT_TOP]:
        if scored.score >= RELEVANT:
            out[scored.item.id] = {"note": scored.item, "score": scores[scored.item.id],
                                   "found_by": "close to it"}
    route_key = f"{area}/{topic}"
    subjects = tension.figure_subjects(text)
    for note in notes:
        if note.id in out:
            continue
        reason = why(note, config, used.get(note.id, 0))
        if reason and _covers(note, area, route_key):
            out[note.id] = {"note": note, "score": scores.get(note.id, 0.0),
                            "found_by": "a baseline where it goes"}
        elif subjects and any(len(mine & theirs) >= 2 for mine in subjects
                              for theirs in _subjects(note)):
            out[note.id] = {"note": note, "score": scores.get(note.id, 0.0),
                            "found_by": "a figure for the same thing"}
    for row in out.values():
        row["baseline"] = why(row["note"], config, used.get(row["note"].id, 0)) or ""
    return sorted(out.values(), key=lambda r: (-r["score"], r["note"].id))


def pair_key(proposed: str, existing: str) -> str:
    """A pair of texts, as the model verdicts are kept: either text changing makes a new
    pair."""
    return util.sha256(util.canonical(proposed) + "\n↔\n" + util.canonical(existing))[:32]


def tensions(brain, text, *, area, topic, chain, partitions=(), exclude=()) -> list[dict]:
    """Checks 1 and 2 against every candidate: [{"id", "title", "why", "baseline",
    "found_by"}], baselines first."""
    found = []
    for row in candidates(brain, text, area=area, topic=topic, chain=chain,
                          partitions=partitions, exclude=exclude):
        note = row["note"]
        reason = tension.tension(text, note.body)
        if reason:
            found.append({"id": note.id, "title": note.title, "why": reason,
                          "baseline": row["baseline"], "found_by": row["found_by"]})
    found.sort(key=lambda r: (not r["baseline"], r["id"]))
    return found


def revised(brain, kind, target) -> tuple | None:
    """(note, why) when a decision on this proposal would revise or retire a baseline: the
    note a change or a retirement targets, or one a new note replaces."""
    st = brain.state()
    ids = [str(target.get("id") or "")] if kind in ("note.update", "note.archive") else []
    ids += [i.strip() for i in str(target.get("supersedes") or "").split(",")
            if i.strip() and i.strip().lower() != "none"]
    used = None
    for note_id in ids:
        note = st.index.note(note_id)
        if note is None:
            continue
        if used is None:
            used = uses(brain)
        reason = why(note, st.config, used.get(note.id, 0))
        if reason:
            return note, reason
    return None


def guard(brain, kind, text, *, base, area, topic, chain, partitions=(), supersedes="",
          note_id="") -> dict | None:
    """Why a change that would apply at once must wait for the owner, or None: it changes,
    retires or replaces a baseline, or it may disagree with a note (checks 1 and 2)."""
    target = {"id": base.id if base is not None else note_id, "supersedes": supersedes or ""}
    found = revised(brain, kind, target)
    if found:
        note, reason = found
        verb = "retires" if kind == "note.archive" else "changes"
        return {"id": note.id, "title": note.title, "baseline": reason,
                "why": f"it {verb} a baseline ({reason})"}
    if kind not in ("note.create", "note.update") or not str(text or "").strip():
        return None
    exclude = {note_id} | {i.strip() for i in str(supersedes or "").split(",")}
    if base is not None:
        exclude.add(base.id)
    for row in tensions(brain, text, area=area, topic=topic, chain=chain,
                        partitions=partitions, exclude=exclude):
        return {"id": row["id"], "title": row["title"], "baseline": row["baseline"],
                "why": f"it may disagree with it: {row['why']}"}
    return None


def previous_reason(brain, note_id: str) -> str:
    """The reason given the last time this baseline was revised, if it ever was."""
    for record in reversed(brain.vault.decisions()):
        revision = record.get("baseline_revised")
        if isinstance(revision, dict) and revision.get("note") == note_id:
            return str(revision.get("reason") or "")
    return ""


def reason_problem(brain, note, reason) -> str | None:
    """What is wrong with a baseline revision's reason, or None."""
    text = " ".join(str(reason or "").split())
    if len(re.findall(r"[\w'-]+", text)) < REASON_WORDS:
        return (f"Say in a few words ({REASON_WORDS} at least) why it changes: the journal "
                "keeps the reason with the revision.")
    if util.canonical(text) == util.canonical(previous_reason(brain, note.id)):
        return "That was the reason last time; say what is different now."
    return None
