"""Reviewing proposals: what each one would change, before anyone decides.

For every waiting proposal, the entries it names (the ones it replaces, and the ones its
proposer says it contradicts), the live entries it nearly repeats without naming them, the
other waiting proposals that say much the same thing, and whatever would make approving it
go wrong: an entry that changed since the proposal was written, one replaced twice, one that
is already archived. A proposal whose topic was guessed, or that opens a new topic, comes with
the closest existing topics, so the owner can move it while approving.

Nearness to live entries is the router's own relevance (the same evidence a packet is built
from). Nearness between two proposals is a cosine over their words, weighted by how rare
each word is among the Brain's entries, so two notes about the same business are not
duplicates merely for sharing its vocabulary.

The analysis is kept until the vault changes: a review page can ask for it on every render.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from . import governance, util

OVERLAP = 0.6     # a live entry this near is worth showing beside the proposal
CLOSE = 0.75      # this near, it may well say the same thing
DUPLICATE = 0.6   # two waiting proposals this alike probably say one thing twice
BODY_LIMIT = 4000


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _ids(value) -> list[str]:
    return [part.strip() for part in re.split(r"[,\s]+", str(value or ""))
            if part.strip() and part.strip().lower() != "none"]


def _stems(text) -> Counter:
    return Counter(util.stem(w) for w in util.terms(text) if w not in util.STOPWORDS)


def similarity(a: str, b: str, idf: dict, unseen: float = 1.0) -> float:
    """Cosine of two texts' words, each weighted by its rarity (`idf`, else `unseen`)."""
    return _cosine(_vector(_stems(a), idf, unseen), _vector(_stems(b), idf, unseen))


def _vector(counts: Counter, idf: dict, unseen: float) -> dict:
    return {t: (1 + math.log(n)) * idf.get(t, unseen) for t, n in counts.items()}


def _cosine(left: dict, right: dict) -> float:
    if not left or not right:
        return 0.0
    dot = sum(left[t] * right[t] for t in left.keys() & right.keys())
    norm = math.sqrt(sum(w * w for w in left.values())) * math.sqrt(
        sum(w * w for w in right.values()))
    return dot / norm if norm else 0.0


NEGATION = re.compile(r"\b(?:never|not|no|don't|do not|doesn't|does not|avoid|stop|without|"
                      r"cannot|can't|mustn't|must not|shouldn't|should not|won't)\b")
NUMBER = re.compile(r"\b\d[\d,.]*\b")


def _sentences(text) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")) if s.strip()]


def contradiction(proposed: str, existing: str) -> str | None:
    """Why a proposal may contradict an entry, or None. The two sentences that share the most
    words are compared: one negating what the other states ("never X" against "always X"),
    or the two giving different figures for the same thing, is a contradiction to settle."""
    best = None
    for left in _sentences(proposed):
        left_terms = set(_stems(left))
        for right in _sentences(existing):
            shared = len(left_terms & set(_stems(right)))
            if shared >= 3 and (best is None or shared > best[0]):
                best = (shared, left, right)
    if best is None:
        return None
    _, left, right = best
    if bool(NEGATION.search(left.lower())) != bool(NEGATION.search(right.lower())):
        return f"one says \u201c{util.excerpt(left, 90)}\u201d, the other \u201c{util.excerpt(right, 90)}\u201d"
    figures_left, figures_right = set(NUMBER.findall(left)), set(NUMBER.findall(right))
    if figures_left and figures_right and figures_left != figures_right:
        return (f"different figures: \u201c{util.excerpt(left, 90)}\u201d against "
                f"\u201c{util.excerpt(right, 90)}\u201d")
    return None


def near_duplicates(st, threshold=DUPLICATE) -> list[tuple[str, str, float]]:
    """Live notes in the same area whose words are this alike: probably one thing said twice
    (a rule restated when it was captured again). Pairs, most alike first."""
    bm25 = st.index.note_bm25
    groups: dict[str, list] = {}
    for note in st.index.notes.values():
        if not st.config.is_focus(note):
            groups.setdefault(note.area, []).append(note)
    out = []
    for group in groups.values():
        group.sort(key=lambda n: n.id)
        vectors = [_vector(_stems(f"{n.title} {n.summary} {n.body}"), bm25.idf, bm25.unseen_idf)
                   for n in group]
        for i, left in enumerate(group):
            for j in range(i + 1, len(group)):
                score = _cosine(vectors[i], vectors[j])
                if score >= threshold:
                    out.append((left.id, group[j].id, round(score, 3)))
    out.sort(key=lambda row: -row[2])
    return out


def _entry(note, **extra) -> dict:
    return {"id": note.id, "title": note.title, "summary": note.summary,
            "route_key": note.route_key, "live": note.live,
            "body": note.body[:BODY_LIMIT], **extra}


def _missing(note_id) -> dict:
    return {"id": note_id, "title": note_id, "summary": "", "route_key": "", "live": False,
            "body": "", "missing": True}


def _text(proposal) -> str:
    target = proposal.target
    return "\n".join(str(v) for v in (target.get("title"), target.get("summary"), proposal.body)
                     if v)


def analyze(brain, **_ignored):
    st = brain.state()
    cached = getattr(brain, "_review", None)
    if cached is not None and cached[0] == st.fingerprint:
        return cached[1]
    caller = brain.caller(st=st)
    if not isinstance(caller, tuple):
        return caller
    chain, _ = caller
    index = st.index
    proposals = sorted(st.snapshot.proposals.values(), key=lambda p: (p.created, p.id))
    topics = {n.route_key for n in index.notes.values()}
    bm25 = getattr(index, "note_bm25", None)
    idf = dict(getattr(bm25, "idf", {}) or {})
    unseen = float(getattr(bm25, "unseen_idf", 1.0) or 1.0)
    texts = {p.id: _text(p) for p in proposals}
    replaced_by: dict[str, list[str]] = {}
    rows = []
    for proposal in proposals:
        target = proposal.target
        kind = proposal.kind
        area = target.get("area") or target.get("layer")
        route_key = f"{area}/{target.get('topic')}" if area else ""
        row = {"id": proposal.id, "kind": kind, "title": str(target.get("title") or ""),
               "route_key": route_key, "placement": str(target.get("placement") or "chosen"),
               "change": ("new" if kind == "note.create" else "update" if kind == "note.update"
                          else "retire" if kind == "note.archive"
                          else "file" if kind == "file.add" else "skill"),
               "replaces": [], "conflicts": [], "overlaps": [], "duplicates": [],
               "new_topic": False, "suggested": [], "base_changed": False, "problems": []}
        named = []
        if kind in ("note.update", "note.archive"):
            named = [str(target.get("id") or "")]
        elif kind == "note.create":
            named = _ids(target.get("supersedes"))
        for note_id in named:
            note = index.note(note_id, include_archived=True)
            row["replaces"].append(_entry(note) if note else _missing(note_id))
            replaced_by.setdefault(note_id, []).append(proposal.id)
        for note_id in _ids(proposal.meta.get("conflicts")):
            note = index.note(note_id, include_archived=True)
            row["conflicts"].append(_entry(note) if note else _missing(note_id))
        if kind in ("note.update", "note.archive") and row["replaces"]:
            current = index.note(named[0])
            base = proposal.meta.get("base_hash")
            if current is None:
                row["problems"].append(f"{named[0]} is no longer live; reject this proposal.")
            elif base and current.body_hash != base:
                row["base_changed"] = True
                row["problems"].append("The entry changed since this was proposed; compare "
                                       "the current text before approving.")
        for entry in row["replaces"]:
            if kind == "note.create" and entry.get("missing"):
                row["problems"].append(f"It replaces {entry['id']}, which no longer exists.")
            elif kind == "note.create" and not entry["live"]:
                row["problems"].append(f"It replaces “{entry['title']}”, which is already "
                                       "archived.")
        if kind in ("note.create", "note.update"):
            for flag in util.text_flags(proposal.body):
                row["problems"].append(f"Its text {flag}.")
        if kind == "file.add" and proposal.meta.get("replaces"):
            row["replaces_file"] = str(proposal.meta["replaces"])
        if kind in ("skill.create", "skill.update"):
            name = str(target.get("name") or "")
            row["skill"] = {"name": name, "category": str(target.get("category") or ""),
                            "description": str(target.get("description") or "")}
            if kind == "skill.update":
                current = index.skills.get(name)
                if current is None:
                    row["problems"].append(f"Skill {name} no longer exists; reject this "
                                           "proposal.")
                else:
                    # What it is now, to compare with what the proposal makes it.
                    row["skill_before"] = {"description": current.description,
                                           "when_to_use": current.when_to_use,
                                           "triggers": current.triggers,
                                           # whole: a change to a long skill is
                                           # compared with all of it
                                           "body": current.body}
                    base = proposal.meta.get("base_hash")
                    if base and current.body_hash != base:
                        row["base_changed"] = True
                        row["problems"].append("The skill changed since this was proposed; "
                                               "compare the current text before approving.")
        if kind == "note.create" and texts[proposal.id]:
            partitions = []
            if target.get("partition"):
                partitions = st.scopes.partition_chain(str(target["partition"]), chain) or []
            skip = set(named) | {c["id"] for c in row["conflicts"]}
            notes = [n for n in st.router.admitted_notes(chain, partitions)
                     if n.id not in skip and not st.config.is_focus(n)]
            for scored in st.router.score_notes(texts[proposal.id], notes)[:3]:
                if scored.score >= OVERLAP:
                    clash = contradiction(proposal.body, scored.item.body)
                    row["overlaps"].append(_entry(scored.item, score=round(scored.score, 3),
                                                  close=scored.score >= CLOSE,
                                                  may_contradict=bool(clash),
                                                  contradiction=clash or ""))
                    if clash:
                        row["problems"].append(
                            f"It may contradict \u201c{scored.item.title}\u201d: {clash}. "
                            "Decide which is current before approving.")
            row["new_topic"] = bool(route_key) and route_key not in topics
            if row["new_topic"] or row["placement"] == "guessed":
                row["suggested"] = [s for s in governance.suggest_placement(
                    brain, texts[proposal.id], chain, partitions) if s["topic"] != route_key]
        rows.append(row)
    by_id = {row["id"]: row for row in rows}
    comparable = [p for p in proposals if p.kind in ("note.create", "note.update")
                  and texts[p.id]]
    vectors = {p.id: _vector(_stems(texts[p.id]), idf, unseen) for p in comparable}
    for i, left in enumerate(comparable):
        for right in comparable[i + 1:]:
            score = _cosine(vectors[left.id], vectors[right.id])
            if score >= DUPLICATE:
                for one, other in ((left, right), (right, left)):
                    by_id[one.id]["duplicates"].append(
                        {"id": other.id, "title": str(other.target.get("title") or other.id),
                         "score": round(score, 3)})
    for note_id, ids in replaced_by.items():
        if len(ids) > 1:
            for proposal_id in ids:
                others = ", ".join(i for i in ids if i != proposal_id)
                by_id[proposal_id]["problems"].append(
                    f"{note_id} is also replaced by {others}; approve only one of them.")
    result = _result(f"{len(rows)} proposal(s) analyzed.", {"proposals": rows})
    brain._review = (st.fingerprint, result)
    return result
