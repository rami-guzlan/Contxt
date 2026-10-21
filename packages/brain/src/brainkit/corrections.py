"""Corrections made from a receipt (Release 1 plan, M07): what went wrong, in one of seven
kinds, and never a change to a fact by itself.

    wrong_information       an item it was sent says something false
    wrong_interpretation    the reading of a source was wrong
    outdated                an item it was sent no longer holds
    not_relevant            an item it was sent did not belong to this request
    missing                 something it needed was not in the receipt
    cut_for_budget          an item that did not fit was needed
    answer_ignored_context  the answer did not use what it was sent

The first three, about an item the receipt sent, raise a "Still true?" card on that note:
a challenge that waits for the owner (dissent.py). The rest are kept against the receipt
in the ledger, where retrieval review and evaluation read them; nothing tunes itself on
them. Presence in a receipt is not proof that an item caused the answer.
"""
from __future__ import annotations

from . import util

KINDS = ("wrong_information", "wrong_interpretation", "outdated", "not_relevant",
         "missing", "cut_for_budget", "answer_ignored_context")
CHALLENGE = ("wrong_information", "wrong_interpretation", "outdated")
NEEDS_ITEM = CHALLENGE + ("not_relevant", "cut_for_budget")
WORDS = {"wrong_information": "says something false", "wrong_interpretation":
         "the source was read wrongly", "outdated": "no longer holds"}


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def correct(brain, packet_id, kind, *, item="", note="", principal=None):
    """Record one correction to one receipt; an item correction raises a challenge."""
    from . import dissent, receipts
    kind = str(kind or "").strip().lower()
    if kind not in KINDS:
        return _result(f"A correction is one of {', '.join(KINDS)}.", {"status": "invalid"},
                       True)
    found = receipts.build(brain, str(packet_id or ""))
    if found is None:
        return _result(f"No receipt {packet_id!r}.", {"status": "missing"}, True)
    item = str(item or "").strip()
    note = " ".join(str(note or "").split())[:600]
    if kind in NEEDS_ITEM:
        pool = found["did_not_fit"] if kind == "cut_for_budget" else (
            found["sent"] + found["opened"])
        if item not in {str(r.get("id")) for r in pool}:
            where = "did not fit" if kind == "cut_for_budget" else "was sent or opened"
            return _result(f"{item or 'That item'} is not among what {where} in this receipt.",
                           {"status": "invalid"}, True)
    who = brain.principal(principal)
    brain.ledger.add_correction(note or kind.replace("_", " "), session_id=found["session_id"],
                                packet_id=found["id"], suspect=item, by=who, kind=kind)
    if kind in CHALLENGE:
        made = dissent.propose(
            brain, item, claim=note or f"This note {WORDS[kind]}.",
            evidence=f"Corrected from receipt {found['id']} ({found['request'][:120]})",
            source=f"receipt:{found['id']}", principal=who,
            reason=f"a correction: {kind.replace('_', ' ')}")
        if made.is_error and made.data.get("status") != "duplicate":
            return made
        return _result(f"Recorded. {made.text}",
                       {"status": "recorded", "outcome": "challenge", "kind": kind,
                        "proposal_id": made.data.get("proposal_id"), "id": item})
    return _result("Recorded against this receipt. Nothing in the Brain changed.",
                   {"status": "recorded", "outcome": "recorded", "kind": kind, "id": item})


def listed(brain, *, packet_id="", kind="", since=""):
    """The corrections made from receipts, oldest first."""
    rows = list(reversed(brain.ledger.corrections(status=None, since=since)))
    return [{"at": r["at"], "kind": r.get("kind") or "", "item": r.get("suspect") or "",
             "note": r.get("text") or "", "packet_id": r.get("packet_id") or "",
             "by": r.get("by") or ""}
            for r in rows if r.get("kind")
            and (not packet_id or r.get("packet_id") == packet_id)
            and (not kind or r.get("kind") == kind)]


def summary(brain, *, days=30) -> dict:
    """How many of each kind in the last `days` days: the review's starting point."""
    import datetime as dt
    since = (util.today_date() - dt.timedelta(days=days)).isoformat()
    counts: dict[str, int] = {}
    for row in listed(brain, since=since):
        counts[row["kind"]] = counts.get(row["kind"], 0) + 1
    return counts
