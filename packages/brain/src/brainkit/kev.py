"""Typed checks inside the knowledge agent (brain-logic plan 17.5): is this stale, is it a
duplicate, does it contradict that, is it worth suggesting, which tier. Kev answers them, faster
and calibrated, when the model service is ready and Kev qualified for that kind of question
(5.11.15); otherwise code answers (the review's similarity and contradiction checks, the note's
own shelf life) and says so. The 4B agent writes only what needs words.

Every answer is {"kind", "answer", "score", "by"}: `by` is "kev" or "code", and the agent's run
record keeps it.
"""
from __future__ import annotations

from . import models_client, review, util

KINDS = ("stale", "duplicate", "contradicts", "worth", "tier")
TIERS = ("alignment", "knowledge", "state", "episodes")
DUPLICATE = review.DUPLICATE  # the review's mark: this alike, two notes say the same


def _kev():
    """The decider when the service is ready and Kev qualified, else None."""
    try:
        status = models_client.status()
    except Exception:  # no service, no Kev: code answers
        return None, {}
    if not status.ready or "decide" not in (status.roles or {}):
        return None, {}
    return models_client.Decider(status), dict(status.qualified or {})


def check(brain, kind: str, note, other=None) -> dict:
    """One typed check about a note (and another, for duplicate and contradicts)."""
    if kind not in KINDS:
        raise ValueError(f"A typed check is one of {', '.join(KINDS)}.")
    decider, qualified = _kev()
    if decider is not None and qualified.get(kind, False):
        try:
            return _ask_kev(decider, kind, note, other)
        except (models_client.ServiceError, OSError, ValueError, KeyError):
            pass
    return _code(brain, kind, note, other)


def _ask_kev(decider, kind, note, other) -> dict:
    text = util.excerpt(note.body, 600)
    if kind == "tier":
        question = models_client.choice(f"Which tier does this note belong in? {text}",
                                        {t: t for t in TIERS})
    else:
        words = {
            "stale": f"Is this still current, not replaced by anything newer? {text}",
            "duplicate": f"Do these say the same thing? A: {text} B: "
                         f"{util.excerpt(other.body, 600) if other else ''}",
            "contradicts": f"Do these contradict each other? A: {text} B: "
                           f"{util.excerpt(other.body, 600) if other else ''}",
            "worth": f"Is a change to this note worth the owner's attention? {text}",
        }[kind]
        question = models_client.noul(words)
    answers = decider.ask({"note": note.id}, {kind: question})
    found = models_client.probabilities(answers.get(kind)) or {}
    if not found:
        raise ValueError("no answer")
    best = max(found, key=found.get)
    answer = best if kind == "tier" else best in ("yes", "true")
    if kind == "stale":
        answer = not answer  # the question asks whether it is still current
    return {"kind": kind, "answer": answer, "score": round(float(found[best]), 3), "by": "kev"}


def _code(brain, kind, note, other) -> dict:
    st = brain.state()
    if kind == "stale":
        why = note.stale_reason(util.today_date(), st.config.review_days_for(note))
        return {"kind": kind, "answer": bool(why), "score": 1.0 if why else 0.0, "by": "code"}
    if kind in ("duplicate", "contradicts") and other is not None:
        if kind == "duplicate":
            bm25 = st.index.note_bm25
            score = review.similarity(note.body, other.body, bm25.idf, bm25.unseen_idf)
            return {"kind": kind, "answer": score >= DUPLICATE, "score": round(score, 3),
                    "by": "code"}
        found = review.contradiction(note.body, other.body)
        return {"kind": kind, "answer": bool(found), "score": 1.0 if found else 0.0,
                "by": "code"}
    if kind == "tier":
        return {"kind": kind, "answer": note.tier, "score": 1.0, "by": "code"}
    # Worth suggesting: a note AIs use, or one that is a rule or a must-hold.
    weighty = note.must_hold or note.kind == "rule"
    return {"kind": kind, "answer": weighty, "score": 1.0 if weighty else 0.5, "by": "code"}


def line(result: dict) -> str:
    """A typed check as the candidate's text carries it."""
    answer = result["answer"]
    shown = answer if isinstance(answer, str) else ("yes" if answer else "no")
    return f"Typed check ({result['by']}): {result['kind']}? {shown} ({result['score']})"
