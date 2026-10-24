"""Levels: how far an entry has come, one word on every entry (v4 spec, section 6).

    exhaust     captured or proposed, not kept yet (a waiting proposal)
    tentative   kept, but said with a hedge or a condition, or disputed
    kept        kept by the owner (or their governance), not verified
    confirmed   kept and checked: verified, or confirmed by the owner
    canon       what always holds: a must-hold, or a note the owner marked a baseline

The level is derived from what a note already records; nothing is stored for it. A packet
names each item's level in braces, the Brain map counts entries by level, and the app shows
it on every note.
"""
from __future__ import annotations

ORDER = ("canon", "confirmed", "kept", "tentative", "exhaust")
LABELS = {"canon": "canon", "confirmed": "confirmed", "kept": "kept, not verified",
          "tentative": "tentative", "exhaust": "exhaust"}


def of(note) -> str:
    """The level of one kept note: canon, confirmed, kept or tentative."""
    meta = note.meta or {}
    if note.must_hold or meta.get("baseline") is True \
            or str(meta.get("baseline") or "").lower() == "true":
        return "canon"
    status = str(meta.get("statement_status") or "").strip().lower()
    if status in ("tentative", "conditional", "disputed") or meta.get("disputed"):
        return "tentative"
    if meta.get("verified") or str(meta.get("confidence") or "").lower() == "confirmed":
        return "confirmed"
    return "kept"


def label(level: str) -> str:
    """How a level reads to a person and in a packet: `kept` is "kept, not verified"."""
    return LABELS.get(level, level)


def tag(note) -> str:
    """The level in braces, as a packet item carries it: `{kept, not verified}`."""
    return "{" + label(of(note)) + "}"
