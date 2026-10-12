"""Checking outputs against must-holds (brain-logic plan 9): before a Work run finishes, and
when an AI records an output, its text is checked against the must-holds of its domain.

Deterministic checks come first, made by code from each must-hold's own words:
- a phrase it forbids ("Never say 15+ years", "don't write 'world-class'"): quoted text, or the
  words after never / do not / don't / avoid up to the end of the clause;
- a figure it rules out ("never 15+ years": the figure with its unit);
- dashes, when the rule is about em or en dashes (and "spaced hyphens").

A model check for the rest is a hook the app may turn on (`model_check`): it sees the rule and
the text, never who wrote either. A violation sends a Work run back once, through the finishing
gate, and flags a recorded output. Nothing is ever changed by the check itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DASHES = re.compile(r"[—–]|\s-\s")
QUOTED = re.compile(r"[\"“‘']([^\"”’']{2,80})[\"”’']")
FORBID = re.compile(
    r"\b(?:never|do not|don't|avoid|no)\s+(?:say|write|use|call (?:it|us)|mention|claim|"
    r"quote)?\s*(.{2,60}?)(?:[.;,:]|$| or | and | but | instead)", re.IGNORECASE)
FIGURE = re.compile(r"\d[\d,.]*\s*\+?\s*(?:%|percent|years?|months?|days?|x)?", re.IGNORECASE)
TOO_COMMON = {"it", "this", "that", "them", "anything", "something", "a", "the", "em dashes",
              "en dashes", "dashes"}


@dataclass
class Violation:
    note: str
    rule: str
    found: str
    kind: str  # phrase | figure | dash

    def to_dict(self) -> dict:
        return {"note": self.note, "rule": self.rule, "found": self.found, "kind": self.kind}


def checks(note) -> list[tuple[str, re.Pattern]]:
    """(kind, pattern) for one must-hold, from its own words."""
    text = str(note.must_text or note.body or "")
    low = text.lower()
    out: list[tuple[str, re.Pattern]] = []
    if re.search(r"\b(?:em|en)[ -]dash", low) or "spaced hyphen" in low:
        out.append(("dash", DASHES))
    phrases = [m.group(1).strip() for m in QUOTED.finditer(text)]
    if not phrases:
        phrases = [m.group(1).strip(" '\"") for m in FORBID.finditer(text)]
    for phrase in phrases:
        clean = " ".join(phrase.split())
        if not clean or clean.lower() in TOO_COMMON or len(clean) < 3:
            continue
        figure = FIGURE.fullmatch(clean)
        kind = "figure" if figure or re.search(r"\d", clean) else "phrase"
        pattern = re.escape(clean).replace(r"\ ", r"\s*")
        out.append((kind, re.compile(rf"(?<!\w){pattern}(?!\w)", re.IGNORECASE)))
    return out


def check(text: str, notes) -> list[Violation]:
    """Every deterministic violation of these must-holds in the text."""
    out = []
    for note in notes:
        for kind, pattern in checks(note):
            found = pattern.search(str(text or ""))
            if found:
                out.append(Violation(note=note.id, rule=str(note.must_text or note.title or ""),
                                     found=found.group(0).strip() or found.group(0),
                                     kind=kind))
    return out


def must_holds_for(brain, text: str, *, domains=None) -> list:
    """The must-holds whose domain the text (or the run's domains) puts in play; with no domain
    in play, every must-hold that names a phrase to avoid."""
    st = brain.state()
    low = str(text or "").lower()
    found = []
    for note in st.index.notes.values():
        if not note.must_hold or not note.live:
            continue
        words = [w.lower() for w in (note.triggers or []) + (note.applies_to or []) if w]
        if domains and any(d in (note.applies_to or []) for d in domains):
            found.append(note)
        elif not words or any(w in low for w in words) or checks(note):
            found.append(note)
    return found
