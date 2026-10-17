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

THE BASELINE CHECK. Each note proposal is read against the notes baseline.candidates picks
(the most relevant, the baselines where it goes, the notes giving a figure for the same
thing): checks 1 and 2 (tension.py) at once, and a model (check 3) when the app has one to
ask, its verdicts kept in the ledger. What may disagree is listed under `tensions`; a proposal
that changes, retires, replaces or disagrees with a baseline carries that baseline, with its
impact when it is a rule, a standing note or a must-hold (`baseline`).

The analysis is kept until the vault changes or a model's verdict comes in: a review page can
ask for it on every render.
"""
from __future__ import annotations

import datetime as _dt
import math
import re
from collections import Counter

from . import baseline, governance, tension, util

OVERLAP = 0.6     # a live entry this near is worth showing beside the proposal
CLOSE = 0.75      # this near, it may well say the same thing
DUPLICATE = 0.6   # two waiting proposals this alike probably say one thing twice
BODY_LIMIT = 4000
# What a model may say about two notes (check 3): the proposal contradicts the note, narrows
# it (an exception or a narrower case), extends it (adds to it), agrees with it, or is about
# something else.
RELATIONS = ("contradicts", "narrows", "extends", "agrees", "unrelated")
CLEARS = ("extends", "agrees", "unrelated")  # a model's reading that settles checks 1 and 2
WENT_IN_DAYS = 14  # what went in on its own is read by a model for this long afterwards


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
# Figures written as words count as figures ("twelve weeks" against "six to eight weeks");
# "one" stays out, it is as often a pronoun ("the one we chose").
NUMBER_WORDS = {word: str(value) for value, word in enumerate(
    "zero . two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty".split()) if word != "."}
NUMBER_WORDS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
                     "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
                     "dozen": "12"})


def _figures(text: str) -> set[str]:
    """The figures a sentence gives, written as digits or as words."""
    found = {f.replace(",", "") for f in NUMBER.findall(text)}
    found |= {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in NUMBER_WORDS}
    return found


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
    figures_left, figures_right = _figures(left), _figures(right)
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


def _verdict(found) -> dict | None:
    """A model's kept verdict on a pair, as the review shows it."""
    if not found or found.get("relation") not in RELATIONS:
        return None
    detail = found.get("detail") or {}
    return {"relation": found["relation"], "proposed": str(detail.get("proposed") or ""),
            "existing": str(detail.get("existing") or ""),
            "settle": str(detail.get("settle") or ""), "at": found.get("at")}


def _baseline_row(brain, note, why, used, *, change, tension_why="") -> dict:
    """A baseline a proposal would change, as the card that settles it needs it."""
    meta = note.meta
    return {"id": note.id, "title": note.title, "body": note.body[:BODY_LIMIT],
            "kind": note.kind, "load": note.load, "why": why, "change": change,
            "tension": tension_why, "approved_by": str(meta.get("approved_by") or ""),
            "approved_at": util.day_text(meta.get("approved_at")), "added": note.added,
            "revised": util.day_text(meta.get("revised")), "verified": note.verified,
            "uses": int(used.get(note.id, 0)), "weighty": baseline.weighty(note),
            "impact": baseline.impact(brain, note) if baseline.weighty(note) else None,
            "previous_reason": baseline.previous_reason(brain, note.id),
            "min_words": baseline.REASON_WORDS}


def _partitions(st, target, chain) -> list:
    if target.get("partition"):
        return st.scopes.partition_chain(str(target["partition"]), chain) or []
    return []


def _stamp(brain) -> str:
    try:
        return brain.ledger.verdicts_stamp()
    except Exception:
        return ""


def analyze(brain, **_ignored):
    st = brain.state()
    stamp = _stamp(brain)
    cached = getattr(brain, "_review", None)
    if cached is not None and cached[0] == (st.fingerprint, stamp):
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
    used = baseline.uses(brain) if proposals else {}
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
                          else "challenge" if kind == "note.challenge"
                          else "file" if kind == "file.add" else "skill"),
               "replaces": [], "conflicts": [], "overlaps": [], "duplicates": [],
               "tensions": [], "updates": [], "baseline": None, "checks": None,
               "scheduled": None,
               "held": None, "new_topic": False, "suggested": [], "base_changed": False,
               "problems": []}
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
        found_in = str(proposal.target.get("instruction_from") or "").strip()
        if found_in:
            # Brain-logic plan 7.1: an instruction found inside content is reported, never
            # kept as a rule; the card says where it came from.
            row["problems"].append(
                f"An instruction found in {found_in}: kept as what it says, not as your rule. "
                "Make it a rule only if it is yours.")
        unheard = str(proposal.target.get("unheard_quote") or "").strip()
        if unheard and proposal.target.get("unheard_in") == "work":
            row["problems"].append(
                f"The quote “{unheard}” is not in what that work read: it is kept as the AI's "
                "inference, not its source's words.")
        elif unheard:
            row["problems"].append(
                f"The quote “{unheard}” is not in what you said in that conversation: it is "
                "kept as the AI's inference, not your words.")
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
        if kind == "note.challenge":
            challenged = index.note(str(target.get("id") or ""), include_archived=True)
            row["challenged"] = (_entry(challenged) if challenged is not None
                                 else _missing(str(target.get("id") or "")))
            row["challenge"] = {k: str(target.get(k) or "")
                                for k in ("claim", "evidence", "source")}
            row["route_key"] = challenged.route_key if challenged is not None else ""
            if challenged is None or not challenged.live:
                row["problems"].append("The note it challenges is no longer live; reject it.")
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
        partitions = _partitions(st, target, chain)
        skip = set(named) | {c["id"] for c in row["conflicts"]}
        cleared: set[str] = set()
        if kind in ("note.create", "note.update") and proposal.body.strip():
            pairs = baseline.candidates(brain, proposal.body, area=area or "",
                                        topic=str(target.get("topic") or ""), chain=chain,
                                        partitions=partitions, exclude=skip)
            asked = {r["note"].id: baseline.pair_key(proposal.body, r["note"].body)
                     for r in pairs[:baseline.MODEL_PAIRS]}
            verdicts = _known(brain, asked.values())
            as_of = util.parse_date(target.get("as_of"))
            for pair in pairs:
                note = pair["note"]
                if baseline.newer_value(proposal.body, as_of.isoformat() if as_of else "",
                                        note):
                    # The same figure, dated later: an update, which keeping it may retire.
                    row["updates"].append(_entry(note, as_of=note.dated))
                    continue
                found = tension.tension(proposal.body, note.body)
                verdict = _verdict(verdicts.get(asked.get(note.id, "")))
                if verdict and verdict["relation"] in CLEARS:
                    cleared.add(note.id)
                if (found and note.id not in cleared) or (
                        verdict and verdict["relation"] in ("contradicts", "narrows")):
                    row["tensions"].append(_entry(
                        note, why=found or "", found_by=pair["found_by"],
                        baseline=pair["baseline"], model=verdict))
            row["tensions"].sort(key=lambda t: (not t["baseline"], t["id"]))
            row["checks"] = {"pairs": len(asked),
                             "read": sum(1 for key in asked.values() if key in verdicts),
                             "model": ("none" if not asked else "done"
                                       if all(key in verdicts for key in asked.values())
                                       else "waiting")}
        revised = baseline.revised(brain, kind, target)
        if revised:
            row["baseline"] = _baseline_row(
                brain, revised[0], revised[1], used,
                change="retire" if kind == "note.archive" else "revise")
        else:
            hit = next((t for t in row["tensions"] if t["baseline"]), None)
            if hit is not None and index.note(hit["id"]) is not None:
                settle = (hit.get("model") or {}).get("settle") or ""
                row["baseline"] = _baseline_row(brain, index.note(hit["id"]), hit["baseline"],
                                                used, change="disagree",
                                                tension_why=hit["why"] or settle)
        if proposal.meta.get("scheduled_for"):
            row["scheduled"] = {"for": str(proposal.meta["scheduled_for"]),
                                "by": str(proposal.meta.get("scheduled_by") or ""),
                                "reason": str(proposal.meta.get("scheduled_reason") or "")}
        if proposal.meta.get("tension"):
            row["held"] = {"id": str(proposal.meta["tension"]),
                           "why": str(proposal.meta.get("tension_why") or "")}
        if kind == "note.create" and texts[proposal.id]:
            notes = [n for n in st.router.admitted_notes(chain, partitions)
                     if n.id not in skip and not st.config.is_focus(n)]
            tensions = {t["id"]: t for t in row["tensions"]}
            for scored in st.router.score_notes(texts[proposal.id], notes)[:3]:
                if scored.score >= OVERLAP:
                    found = tensions.get(scored.item.id)
                    clash = (found or {}).get("why") or ""
                    row["overlaps"].append(_entry(scored.item, score=round(scored.score, 3),
                                                  close=scored.score >= CLOSE,
                                                  may_contradict=found is not None,
                                                  contradiction=clash))
            for found in row["tensions"]:
                clash = found["why"] or (found.get("model") or {}).get("settle") or ""
                row["problems"].append(
                    f"It may contradict \u201c{found['title']}\u201d"
                    + (f": {clash}" if clash else "") + ". Decide which is current before "
                    "approving.")
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
    brain._review = ((st.fingerprint, stamp), result)
    return result


def dated_pairs(st) -> list[dict]:
    """Live dated notes (`as_of`, or state notes) that give different values for the same
    thing: the newer, the older, and the older's date. Keeping both is history; retiring the
    older is tidier."""
    notes = sorted((n for n in st.index.notes.values()
                    if (n.as_of or n.kind == "state") and not st.config.is_focus(n)
                    and tension.measures(n.body)), key=lambda n: (n.dated, n.id))
    out = []
    for i, older in enumerate(notes):
        for newer in notes[i + 1:]:
            if newer.dated > older.dated and tension.same_measure(older.body, newer.body):
                out.append({"key": f"older:{older.id}|{newer.id}", "older": _entry(older),
                            "newer": _entry(newer), "older_as_of": older.dated,
                            "newer_as_of": newer.dated})
    return out


def _known(brain, keys) -> dict:
    try:
        return brain.ledger.verdicts(keys)
    except Exception:
        return {}


def went_in(brain, *, days=WENT_IN_DAYS) -> list:
    """Live notes that went in on their own (own scope, or a capture the policy let in) in
    the last `days` days, newest first: a model reads them against the Brain afterwards."""
    since = (util.now() - _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    st = brain.state()
    out, seen = [], set()
    for record in reversed(brain.vault.decisions()):
        if str(record.get("at") or "") < since:
            break
        if record.get("action") != "auto-applied" or record.get("kind") not in (
                "note.create", "note.update"):
            continue
        note = st.index.note(str(record.get("note") or ""))
        if note is not None and note.id not in seen and not st.config.is_focus(note):
            seen.add(note.id)
            out.append((note, record))
    return out


def _went_in_pairs(brain, note, chain) -> dict:
    st = brain.state()
    pairs = baseline.candidates(brain, note.body, area=note.area, topic=note.topic,
                                chain=chain, partitions=_partitions(st, note.meta, chain),
                                exclude={note.id})
    return {baseline.pair_key(note.body, r["note"].body): r for r in
            pairs[:baseline.MODEL_PAIRS]}


def pending_checks(brain, *, limit: int = 4) -> list[dict]:
    """What a model should read next (check 3), oldest first: [{"subject", "title", "text",
    "pairs": [{"key", "id", "title", "text"}]}]. Waiting note proposals come first, then
    what went in on its own lately; a pair already read is not asked again."""
    st = brain.state()
    caller = brain.caller(st=st)
    if not isinstance(caller, tuple):
        return []
    chain, _ = caller
    out: list[dict] = []

    def add(subject, title, text, found):
        known = _known(brain, found)
        todo = [{"key": key, "id": r["note"].id, "title": r["note"].title,
                 "text": r["note"].body[:BODY_LIMIT]}
                for key, r in found.items() if key not in known]
        if todo:
            out.append({"subject": subject, "title": title, "text": text[:BODY_LIMIT],
                        "pairs": todo})

    for proposal in sorted(st.snapshot.proposals.values(), key=lambda p: (p.created, p.id)):
        if len(out) >= limit:
            return out
        if proposal.kind not in ("note.create", "note.update") or not proposal.body.strip():
            continue
        target = proposal.target
        skip = set(_ids(target.get("supersedes"))) | set(_ids(proposal.meta.get("conflicts")))
        if proposal.kind == "note.update":
            skip.add(str(target.get("id") or ""))
        pairs = baseline.candidates(
            brain, proposal.body, area=str(target.get("area") or target.get("layer") or ""),
            topic=str(target.get("topic") or ""), chain=chain,
            partitions=_partitions(st, target, chain), exclude=skip)
        add(f"proposal:{proposal.id}", str(target.get("title") or proposal.id), proposal.body,
            {baseline.pair_key(proposal.body, r["note"].body): r
             for r in pairs[:baseline.MODEL_PAIRS]})
    for note, _record in went_in(brain):
        if len(out) >= limit:
            break
        add(f"note:{note.id}", note.title, note.body, _went_in_pairs(brain, note, chain))
    if len(out) < limit and bool(st.config.governance.get("cross_check", True)):
        # The weekly cross-check's few pairs (dissent.py), after everything waiting.
        from . import dissent
        out += dissent.cross_pairs(brain)[: limit - len(out)]
    return out


def went_in_disagreements(brain) -> list[dict]:
    """What went in on its own that a model then read as contradicting a note: the note,
    the one it disagrees with, the model's reading, and the undo point that takes it back."""
    from .recap import _undo_points
    st = brain.state()
    caller = brain.caller(st=st)
    if not isinstance(caller, tuple):
        return []
    chain, _ = caller
    found = went_in(brain)
    if not found:
        return []
    points = None
    out = []
    for note, record in found:
        pairs = _went_in_pairs(brain, note, chain)
        verdicts = _known(brain, pairs)
        for key, pair in pairs.items():
            verdict = _verdict(verdicts.get(key))
            if not verdict or verdict["relation"] != "contradicts":
                continue
            if points is None:
                points = _undo_points(brain)
            other = pair["note"]
            out.append({"key": f"wentin:{note.id}|{other.id}",
                        "note": _entry(note, at=str(record.get("at") or "")),
                        "with": _entry(other, baseline=pair["baseline"]),
                        "model": verdict,
                        "checkpoint": points.get(str(record.get("proposal") or ""))})
            break
    return out
