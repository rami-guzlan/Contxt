"""Moving in: bring what an AI app already knows (its memory of the person, an instruction
file, anything pasted) into the Brain, and show how it lands.

`preview` has the Brain read the sources without writing anything: each idea sorted by kind,
placed in a topic, and checked against what the Brain holds (already known, might disagree)
and for private detail. `keep` proposes the ideas the person chose. They wait for the owner's
yes like any suggestion: in Catch up, as quick groups, or one at a time when they disagree
with a note or hold private detail. Each says where it came from (`import:<source>`), and a
password or a key is never proposed at all.
"""

from __future__ import annotations

import re
from typing import Any

from workspace_core.domain.policy import Principal
from workspace_core.errors import ValidationFailed

from .brain import proposer
from .onboarding import DEFAULT_OWNER
from .runtime import Runtime

KINDS = ("chatgpt", "claude", "cursor", "instructions", "paste")
MAX_SOURCES = 8
KEEP = ("new", "disagree", "private")  # what can be kept; the rest the Brain already has
TITLE_WORDS = 9


def title_of(text: str) -> str:
    """A few plain words naming an idea: its first clause, without the closing stop."""
    first = re.split(r"(?<=[.!?;:])\s|,\s(?=and |but |so )", " ".join(str(text).split()))[0]
    words = first.rstrip(".!?;:,").split()
    title = " ".join(words[:TITLE_WORDS])
    return title + ("…" if len(words) > TITLE_WORDS else "")


def _sources(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValidationFailed("Paste or drop at least one source.", field="sources")
    if len(value) > MAX_SOURCES:
        raise ValidationFailed(f"Bring in at most {MAX_SOURCES} sources at a time.")
    out = []
    for item in value:
        if not isinstance(item, dict):
            raise ValidationFailed("Each source is {kind, text}.", field="sources")
        kind = str(item.get("kind") or "paste").strip().lower()
        if kind not in KINDS:
            raise ValidationFailed(f"A source is one of {', '.join(KINDS)}.", field="kind")
        text = str(item.get("text") or "")
        if not text.strip():
            raise ValidationFailed("One of the sources is empty.", field="sources")
        out.append({"kind": kind, "text": text, "label": str(item.get("label") or "")[:80]})
    return out


class MovingIn:
    def __init__(self, rt: Runtime) -> None:
        self.rt = rt

    def preview(self, who: Principal, sources: Any) -> dict[str, Any]:
        """What the Brain makes of the sources, stage by stage, writing nothing."""
        who.require("brain.read")
        return self.rt.brain.move_in(_sources(sources), name=self._name(who))

    def keep(self, who: Principal, sources: Any, *, ids: list[str] | None = None) -> dict[str, Any]:
        """Propose the ideas worth keeping (all of them, or the ones `ids` names). The Brain
        reads the sources again, so what is proposed is what it found, not what a page sent."""
        who.require("brain.propose")
        clean = _sources(sources)
        found = self.rt.brain.move_in(clean, name=self._name(who))
        wanted = {str(i) for i in ids} if ids else None
        labels = {s["id"]: s["label"] for s in found.get("sources") or []}
        owner = str(self.rt.brain.status().get("principal") or "") or None
        day = self.rt.clock.now().date().isoformat()
        items: list[dict[str, Any]] = []
        chosen: list[dict[str, Any]] = []
        secrets = 0
        for idea in found.get("ideas") or []:
            if idea.get("status") not in KEEP:
                continue
            if wanted is not None and idea["id"] not in wanted:
                continue
            if idea.get("secret"):
                secrets += 1  # a password or a key: never kept
                continue
            match = idea.get("match") or {}
            extra = (
                {"private": idea["private"], "classification": "confidential"}
                if idea.get("private")
                else None
            )
            label = labels.get(idea["source"]) or "what an AI app knew"
            items.append(
                {
                    "title": title_of(idea["text"]),
                    "statement": idea["text"],
                    "kind": idea.get("kind") or "fact",
                    "scope": owner if idea.get("personal") else None,
                    "evidence": f"Moved in from {label} on {day}: “{idea['original']}”",
                    "sources": [],
                    "topic": idea.get("topic") or None,
                    "origin": f"import:{idea.get('source_kind') or 'paste'}",
                    "contradicts": [match["id"]]
                    if idea["status"] == "disagree" and match.get("id")
                    else None,
                    "extra": extra,
                }
            )
            chosen.append(idea)
        made = self.rt.brain.propose_many(items, proposer=proposer(who)) if items else []
        proposed = [
            {"idea": idea["id"], "proposal_id": result.proposal_id, "status": result.status}
            for idea, result in zip(chosen, made, strict=False)
        ]
        refused = [
            {"idea": idea["id"], "message": result.message}
            for idea, result in zip(chosen, made, strict=False)
            if result.status == "refused"
        ]
        with self.rt.write() as tx:
            tx.emit(
                "brain.moved_in",
                actor_id=who.actor_id,
                subject_type="brain",
                subject_id="move-in",
                data={
                    "sources": [s["kind"] for s in clean],
                    "ideas": len(found.get("ideas") or []),
                    "proposed": sum(1 for p in proposed if p["status"] == "pending"),
                },
            )
        return {
            "stages": found.get("stages") or {},
            "proposed": [p for p in proposed if p["status"] == "pending"],
            "already": [p for p in proposed if p["status"] == "duplicate"],
            "refused": refused,
            "secrets_left_out": secrets,
        }

    @staticmethod
    def _name(who: Principal) -> str:
        """How a note about the person names them: their first name, once they gave one."""
        name = " ".join(str(who.name or "").split())
        return "" if not name or name == DEFAULT_OWNER else name.split(" ")[0]
