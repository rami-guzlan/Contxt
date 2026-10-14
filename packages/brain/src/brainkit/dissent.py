"""Dissent: challenges to what the Brain believes, and where they show.

A CHALLENGE is a governed proposal (`note.challenge`) that targets a note with a claim, the
evidence for it and where that evidence comes from. It always waits for the owner. Approved,
the note's confidence becomes disputed and the challenge stays with it as its other view
(`other_view`, with its evidence and source); rejected, the journal keeps the reason, and the
same claim is not raised again on the same evidence (`propose`).

CONTESTED IN BRIEFS (packets.py): a disputed note with an other view brings it along into
planning, strategy and decision work ("Contested: ..."); for a lookup it stays a flag.

THE INTERNAL CROSS-CHECK (`cross_check`, on unless the owner turns it off): it takes the notes
AIs use most and the baselines longest since checked, and reads each against what the Brain
already holds: other notes, quoted sections of filed documents, and proposals that say
otherwise, waiting or rejected in the last REJECTED_DAYS days. Checks 1 and 2 read every pair;
the owner's own AI reads at most CROSS_MODEL_PAIRS pairs a week (`cross_pairs`), and its
verdict wins over checks 1 and 2. Catch up shows at most one finding a week: one belief to
look at, with its evidence.

THE EXTERNAL CHALLENGER (off until the owner turns it on, `challenger`) argues each week
against one to three high-impact beliefs (`targets`: the most used, the longest since checked,
the baselines). The app runs it; what it finds comes back as challenges.
"""
from __future__ import annotations

import datetime as _dt
import re

from . import baseline, tension, util

KIND = "note.challenge"
MAX_CLAIM = 600
MAX_EVIDENCE = 2000
TARGETS = 15            # beliefs the cross-check reads each time
EVIDENCE_NOTES = 8      # other notes read against each belief
EVIDENCE_SECTIONS = 3   # quoted sections of filed documents read against each belief
SECTION_BAR = 0.35      # how close a section must be to a belief to be read against it
REJECTED_DAYS = 90      # rejected proposals that still count as evidence
CROSS_MODEL_PAIRS = 3   # pairs a week the owner's own AI reads for the cross-check
CROSS = "x:"            # how the cross-check's model verdicts are kept apart in the ledger
DELIBERATE = re.compile(
    r"\b(?:plan|planning|strateg\w*|decid\w*|decision\w*|should (?:we|i)|recommend\w*|"
    r"priorit\w*|roadmap|approach|options?|choose|trade-?offs?|pitch|proposal|whether)\b",
    re.IGNORECASE)


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _clean(text, limit) -> str:
    return " ".join(str(text or "").split())[:limit]


def rejected_before(brain, note_id, claim, evidence) -> dict | None:
    """The journal record of a rejected challenge to this note with this claim and this
    evidence, if there is one: raising it again needs new evidence."""
    key = (util.canonical(claim), util.canonical(evidence))
    for record in reversed(brain.vault.decisions()):
        if record.get("action") != "rejected" or record.get("kind") != KIND:
            continue
        target = record.get("target") or {}
        if str(target.get("id") or "") != note_id:
            continue
        if (util.canonical(target.get("claim")), util.canonical(target.get("evidence"))) == key:
            return record
    return None


def propose(brain, note_id, *, claim, evidence, source="", principal=None, session_id=None,
            reason=""):
    """Raise a challenge to a note: it waits for the owner. `reason` says who raised it
    (the app names the model or person behind it)."""
    st = brain.state()
    who = brain.principal(principal)
    note = st.index.note(str(note_id or ""))
    claim, evidence = _clean(claim, MAX_CLAIM), _clean(evidence, MAX_EVIDENCE)
    source = _clean(source, 300)
    problems = []
    if note is None or not note.live:
        problems.append(f"no live note {note_id!r} to challenge")
    if not claim:
        problems.append("say what you claim instead")
    if not evidence:
        problems.append("give the evidence for it")
    if problems:
        return _result("Challenge refused: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    waiting = next((p for p in st.snapshot.proposals.values()
                    if p.kind == KIND and p.target.get("id") == note.id
                    and util.canonical(p.target.get("claim")) == util.canonical(claim)), None)
    if waiting is not None:
        return _result(f"The same challenge already waits for review ({waiting.id}).",
                       {"status": "duplicate", "proposal_id": waiting.id, "id": note.id})
    before = rejected_before(brain, note.id, claim, evidence)
    if before is not None:
        why = f": {before['reason']}" if before.get("reason") else ""
        return _result(
            f"This challenge to {note.id} was turned down on {util.day_text(before.get('at'))}{why}. "
            "Raise it again with new evidence.",
            {"status": "refused", "id": note.id, "rejected_at": before.get("at")}, True)
    proposal_id = f"challenge-{note.id}-{util.short_hash(claim + util.now_iso(), 4)}"
    header = {"kind": KIND, "status": "pending", "created": util.now_iso(), "proposer": who,
              "reason": _clean(reason, 200) or "a challenge to a note",
              "session": session_id or ""}
    target = {"id": note.id, "title": note.title, "scope": note.scope, "claim": claim,
              "evidence": evidence, "source": source}
    body = f"{claim}\n\nEvidence: {evidence}" + (f"\n\nSource: {source}" if source else "")
    relpath = brain.vault.write_proposal(proposal_id, header, target, body)
    outcome = brain.after_write([brain.vault.path(relpath)], f"Challenge {note.id}")
    return _result(
        f"Challenge to {note.id} proposed for review. The note stays as it is until the owner "
        "decides.",
        {"status": "pending", "proposal_id": proposal_id, "id": note.id, "path": relpath,
         "commit": outcome.get("commit")})


def apply(brain, proposal, *, actor):
    """The owner accepts a challenge: the note is disputed, and the challenge is its other
    view."""
    note = brain.state().index.note(str(proposal.target.get("id") or ""))
    if note is None or not note.live:
        return _result(f"{proposal.target.get('id')} is no longer live; reject this challenge.",
                       {"status": "conflict"}, True)
    claim = str(proposal.target.get("claim") or "")
    evidence = str(proposal.target.get("evidence") or "")
    source = str(proposal.target.get("source") or "")
    meta = dict(note.meta, confidence="disputed", other_view=claim,
                other_view_evidence=evidence, disputed_on=util.today(), updated=util.today())
    if source:
        meta["other_view_source"] = source
    else:
        meta.pop("other_view_source", None)
    brain.vault.write_note(note.path, meta, note.body)
    record = {"at": util.now_iso(), "action": "approved", "by": actor, "proposal": proposal.id,
              "kind": KIND, "note": note.id, "path": note.path, "claim": claim,
              "evidence": evidence, "source": source,
              "proposer": proposal.meta.get("proposer") or actor,
              "session": str(proposal.meta.get("session") or ""),
              "file_hash": brain.vault.file_hash(note.path)}
    decisions = brain.vault.append_decision(record)
    brain.vault.remove_file(proposal.path)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions),
                                 brain.vault.path(proposal.path)],
                                f"Disputed {note.id}: a challenge accepted")
    return _result(f"{note.id} is now disputed; the challenge stays with it as the other view.",
                   {"status": "approved", "id": note.id, "title": note.title,
                    "commit": outcome.get("commit")})


def deliberate(route) -> bool:
    """Planning, strategy or decision work (where a contested note's other view comes along),
    rather than a lookup."""
    return route.task_type in ("combined", "workflow") or bool(
        DELIBERATE.search(str(route.request or "")))


def contested(note) -> str:
    """A disputed note's other view, as a brief shows it, or ""."""
    view = str(note.meta.get("other_view") or "").strip()
    if note.confidence != "disputed" or not view:
        return ""
    evidence = str(note.meta.get("other_view_evidence") or "").strip()
    return f"Contested: {view.rstrip('.')}." + (f" Evidence: {util.excerpt(evidence, 220)}"
                                                if evidence else "")


# ---------------------------------------------------------------------- the cross-check
def beliefs(brain, limit=TARGETS) -> list:
    """What the cross-check reads: the notes AIs used most this month and the baselines longest
    since checked, most used first."""
    st = brain.state()
    used = baseline.uses(brain)
    live = [n for n in st.index.notes.values() if not st.config.is_focus(n)]
    most_used = sorted((n for n in live if used.get(n.id)),
                       key=lambda n: (-used[n.id], n.id))[:limit]
    longest = sorted((n for n in live if baseline.why(n, st.config, used.get(n.id, 0))),
                     key=lambda n: (n.verified or "", n.id))[:limit]
    out, seen = [], set()
    for note in most_used + longest:
        if note.id not in seen:
            seen.add(note.id)
            out.append(note)
    return out[:limit]


def _evidence(brain, note, chain) -> list[dict]:
    """What might say otherwise about a note: [{"kind", "id", "title", "text"}]."""
    st = brain.state()
    out = []
    for row in baseline.candidates(brain, note.body, area=note.area, topic=note.topic,
                                   chain=chain, exclude={note.id})[:EVIDENCE_NOTES]:
        other = row["note"]
        out.append({"kind": "note", "id": other.id, "title": other.title, "text": other.body})
    sections = list(getattr(st.index, "sections", {}).values())
    if sections:
        for scored in st.router.score_sections(note.body, sections)[:EVIDENCE_SECTIONS]:
            if scored.score >= SECTION_BAR:
                section = scored.item
                title = st.index.file_title(section.path)
                out.append({"kind": "file", "id": section.id,
                            "title": f"{title}: {section.heading}" if section.heading else title,
                            "text": section.text})
    for proposal in st.snapshot.proposals.values():
        if proposal.kind in ("note.create", "note.update") and proposal.body.strip() \
                and proposal.target.get("id") != note.id:
            out.append({"kind": "proposal", "id": proposal.id,
                        "title": str(proposal.target.get("title") or proposal.id),
                        "text": proposal.body})
    since = (util.now() - _dt.timedelta(days=REJECTED_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for record in brain.vault.decisions():
        if record.get("action") == "rejected" and str(record.get("at") or "") >= since \
                and record.get("kind") in ("note.create", "note.update") and record.get("body"):
            target = record.get("target") or {}
            if target.get("id") == note.id:
                continue
            out.append({"kind": "rejected", "id": str(record.get("proposal") or ""),
                        "title": str(target.get("title") or record.get("proposal") or ""),
                        "text": str(record["body"])})
    # The closest first, whatever kind it is: what a model reads each week is the likeliest.
    bm25 = getattr(st.index, "note_bm25", None)
    idf = dict(getattr(bm25, "idf", {}) or {})
    unseen = float(getattr(bm25, "unseen_idf", 1.0) or 1.0)
    from .review import similarity
    out.sort(key=lambda item: -similarity(item["text"], note.body, idf, unseen))
    return out


def cross_check(brain) -> list[dict]:
    """Findings: [{"key", "id", "title", "body", "baseline", "why", "found_by", "evidence"}],
    baselines first, then the most used. A model's verdict on a pair (`cross_pairs`) wins over
    checks 1 and 2: "contradicts" makes a finding, a reading that clears it removes one."""
    st = brain.state()
    caller = brain.caller(st=st)
    if not isinstance(caller, tuple):
        return []
    chain, _ = caller
    used = baseline.uses(brain)
    try:
        ledger = brain.ledger
    except Exception:
        ledger = None
    out = []
    for note in beliefs(brain):
        pool = _evidence(brain, note, chain)
        keys = {CROSS + baseline.pair_key(item["text"], note.body): item for item in pool}
        verdicts = ledger.verdicts(keys) if ledger is not None else {}
        for key, item in keys.items():
            relation = (verdicts.get(key) or {}).get("relation")
            found = tension.tension(item["text"], note.body)
            if relation == "contradicts":
                detail = (verdicts[key].get("detail") or {})
                why = str(detail.get("settle") or found or "your AI read them as disagreeing")
                by = "your AI"
            elif found and relation not in ("agrees", "unrelated", "extends", "narrows"):
                why, by = found, "words and figures"
            else:
                continue
            out.append({"key": f"belief:{note.id}", "id": note.id, "title": note.title,
                        "body": note.body, "uses": used.get(note.id, 0),
                        "baseline": baseline.why(note, st.config, used.get(note.id, 0)) or "",
                        "why": why, "found_by": by,
                        "verified": note.verified,
                        "evidence": {k: item[k] for k in ("kind", "id", "title")}
                        | {"text": util.excerpt(item["text"], 600)}})
            break
    # Baselines first, then the most used, then the longest since checked.
    out.sort(key=lambda f: (not f["baseline"], -f["uses"], f["verified"] or "", f["id"]))
    return out


def cross_pairs(brain, *, limit=CROSS_MODEL_PAIRS) -> list[dict]:
    """Pairs for the owner's own AI to read this week (at most `limit` a week, counted from
    the verdicts kept), as `review.pending_checks` hands them out: one belief and its closest
    evidence."""
    try:
        ledger = brain.ledger
        week = (util.now() - _dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
        left = limit - ledger.verdicts_since(week, prefix=CROSS)
        stamp = ledger.verdicts_stamp()
    except Exception:
        return []
    if left <= 0:
        return []
    st = brain.state()
    # The worker asks every few seconds: the pairs are worked out again only when the Brain
    # or a verdict changes.
    cached = getattr(brain, "_cross_pairs", None)
    if cached is not None and cached[0] == (st.fingerprint, stamp, left):
        return cached[1]
    caller = brain.caller(st=st)
    if not isinstance(caller, tuple):
        return []
    chain, _ = caller
    out = []
    for note in beliefs(brain):
        pool = _evidence(brain, note, chain)[:EVIDENCE_NOTES]
        keys = {CROSS + baseline.pair_key(item["text"], note.body): item for item in pool}
        known = ledger.verdicts(keys)
        todo = [{"key": key, "id": item["id"], "title": item["title"],
                 "text": util.excerpt(item["text"], 1500)}
                for key, item in keys.items() if key not in known][:left]
        if todo:
            # The belief is the statement read; the evidence is what it is read against.
            out.append({"subject": f"belief:{note.id}", "title": note.title, "text": note.body,
                        "pairs": todo})
            left -= len(todo)
        if left <= 0:
            break
    brain._cross_pairs = ((st.fingerprint, stamp, limit - ledger.verdicts_since(
        week, prefix=CROSS)), out)
    return out


# ---------------------------------------------------------------------- the external challenger
def targets(brain, limit=3) -> list[dict]:
    """The beliefs the external challenger argues against this week: the most used in briefs,
    the longest since checked, the baselines. Each only as the claim under test."""
    st = brain.state()
    used = baseline.uses(brain)
    today = util.today_date()

    def weight(note) -> float:
        checked = util.parse_date(note.verified)
        age = (today - checked).days / 30 if checked else 6.0
        return (2 * used.get(note.id, 0) + min(age, 12)
                + (5 if baseline.why(note, st.config, used.get(note.id, 0)) else 0))

    live = [n for n in st.index.notes.values()
            if not st.config.is_focus(n) and n.confidence != "disputed"]
    ranked = sorted(live, key=lambda n: (-weight(n), n.id))[:max(1, min(int(limit), 3))]
    return [{"id": n.id, "claim": util.excerpt(n.body, 600), "title": n.title}
            for n in ranked]
