"""Taste, as the owner writes it (Release 1 plan, section 2; design contract 20).

What looks good, feels good and works good to the owner: principles, "this, not that" pairs,
and words to use or avoid, each under one lens and marked usually or always. A taste entry is
an ordinary note with its lens and kind in its front matter, filed under its own topic, so it
is governed, versioned and undone like any note. Learning taste from edits is a later phase:
here an entry exists only because someone wrote it and it was kept, and one edit never makes
an always rule.

Every request to write or make something brings the owner's taste with it (it rides with the
house style), whatever the request is about; a lookup does not.
"""
from __future__ import annotations

from . import governance, util
from .scopes import Scopes

LENSES = ("looks", "feels", "works")
KINDS = ("principle", "pair", "use", "avoid")
STRENGTHS = ("usually", "always")
TOPIC = "taste"


def is_taste(note) -> bool:
    return str(note.meta.get("taste_lens") or "") in LENSES


def home(config) -> str:
    """The area taste is filed in: its own, else how the AI works with you, else the first."""
    areas = config.area_order()
    for wanted in ("taste", "assistant", "me"):
        if wanted in areas:
            return wanted
    return areas[0]


def propose(brain, text, *, lens, kind="principle", strength="usually", not_that="",
            domains=None, principal=None, session_id=None, reason="", op_id=None,
            capture_origin=None, force_pending=False, **cited):
    """Propose one taste entry. It waits, or applies, as the owner's governance says."""
    lens, kind = str(lens or "").strip().lower(), str(kind or "principle").strip().lower()
    strength = str(strength or "usually").strip().lower()
    problems = []
    if lens not in LENSES:
        problems.append(f"lens is one of {', '.join(LENSES)}")
    if kind not in KINDS:
        problems.append(f"kind is one of {', '.join(KINDS)}")
    if strength not in STRENGTHS:
        problems.append(f"strength is one of {', '.join(STRENGTHS)}")
    if kind == "pair" and not str(not_that or "").strip():
        problems.append("a pair says what it is not: give not_that")
    if problems:
        return governance._result("Taste refused: " + "; ".join(problems) + ".",
                                  {"status": "invalid", "problems": problems}, True)
    extra = {"taste_lens": lens, "taste_kind": kind, "taste_strength": strength}
    if str(not_that or "").strip():
        extra["not_that"] = " ".join(str(not_that).split())
    names = [d for d in (domains or []) if str(d).strip()]
    if names:
        extra["taste_domains"] = [" ".join(str(d).split()) for d in names][:8]
    config = brain.state().config
    return governance.propose_note(
        brain, area=home(config), topic=TOPIC, text=text,
        title=util.excerpt(f"{lens.capitalize()}: {text}", 80), note_kind="rule", load="on-demand",
        principal=principal, session_id=session_id, reason=reason, op_id=op_id,
        capture_origin=capture_origin, extra=extra, force_pending=force_pending, **cited)


def profile(st, chain, partitions=()) -> dict:
    """The taste the caller may see, by lens: each entry's text, kind, strength and pair."""
    out: dict[str, list[dict]] = {lens: [] for lens in LENSES}
    for note in st.index.notes.values():
        if not is_taste(note) or not Scopes.admits(note.scope, note.partition, chain,
                                                   partitions):
            continue
        out[note.meta["taste_lens"]].append({
            "id": note.id, "text": note.body.strip(),
            "kind": note.meta.get("taste_kind") or "principle",
            "strength": note.meta.get("taste_strength") or "usually",
            "not_that": note.meta.get("not_that") or "",
            "domains": list(note.meta.get("taste_domains") or [])})
    for rows in out.values():
        rows.sort(key=lambda r: (r["strength"] != "always", r["id"]))
    words = {k: [r["text"] for rows in out.values() for r in rows if r["kind"] == k]
             for k in ("use", "avoid")}
    return {"lenses": out, "words": words,
            "count": sum(len(rows) for rows in out.values())}
