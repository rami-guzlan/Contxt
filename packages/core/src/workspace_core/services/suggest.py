"""Suggested skills, found by code and no model: what is asked again and again with no skill to
follow, and saved prompts run often, are worth writing down as skills ("show it once, write it
down, hand it off").

Asks come from the Brain's request log (what AI apps asked it, the last 30 days), those it
routed to no skill. Two asks are alike when the Brain's local model reads them as meaning the
same (cosine), or, with no model here, when they share most of their words. Three alike make
a suggestion. Accepting one opens New skill with the asks as examples; "Not now" sets it aside.
"""

from __future__ import annotations

import builtins
import hashlib
import math
import re
from datetime import timedelta
from typing import Any

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.domain.policy import Principal

from .notes import cut
from .prompts import Prompts
from .runtime import Runtime

WINDOW = timedelta(days=30)
ALIKE = 3  # asks (or runs of a saved prompt) that make a suggestion
MEANING = 0.86  # cosine on the Brain's local model that reads as the same ask
WORDS = 0.5  # shared words (Jaccard) that read as the same ask, with no model here
MIN_WORDS = 3
WORD = re.compile(r"[a-z0-9]+")
STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "the",
        "this",
        "to",
        "with",
        "you",
        "your",
        "can",
        "could",
        "would",
        "will",
    ]
)


def _words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 1}


def _cosine(a: builtins.list[float], b: builtins.list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


class SkillSuggestions:
    def __init__(self, rt: Runtime, prompts: Prompts) -> None:
        self.rt = rt
        self.prompts = prompts

    def list(self, who: Principal) -> dict[str, Any]:
        """{"suggestions": [...], "matched_by": "meaning" | "words"}, most asked first."""
        who.require("brain.read")
        dismissed = set(self._settings().get("skill_suggestions_dismissed") or [])
        out: builtins.list[dict[str, Any]] = []
        for saved in self.prompts.list(who):
            if saved.uses >= ALIKE:
                out.append(
                    {
                        "kind": "prompt",
                        "key": f"prompt:{saved.id}",
                        "title": saved.title,
                        "count": saved.uses,
                        "examples": [saved.body],
                        "apps": [],
                        "last": saved.last_used,
                        "prompt_id": saved.id,
                        "ask": f'Make a skill from my saved prompt "{saved.title}": '
                        + cut(saved.body, 600),
                    }
                )
        asks, matched = self._asks()
        out += asks
        kept = [s for s in out if s["key"] not in dismissed]
        return {"suggestions": sorted(kept, key=lambda s: -s["count"]), "matched_by": matched}

    def dismiss(self, who: Principal, key: str) -> None:
        """Set a suggestion aside; it does not come back."""
        who.require("brain.read")
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            gone = list(settings.get("skill_suggestions_dismissed") or [])
            if key not in gone:
                gone = [*gone, str(key)[:80]][-200:]
            settings["skill_suggestions_dismissed"] = gone
            tx.update(schema.workspaces, row, {"settings": settings})

    # ---------------------------------------------------------------- inside

    def _settings(self) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return dict(row["settings"] or {})

    def _asks(self) -> tuple[builtins.list[dict[str, Any]], str]:
        cutoff = iso(self.rt.clock.now() - WINDOW)
        rows = self.rt.brain.requests(limit=300).get("requests") or []
        asks = [
            r
            for r in rows
            if str(r.get("at") or "") >= cutoff
            and not r.get("skill")
            and not any(p.get("kind") == "skill" for p in r.get("got") or [])
            and len(_words(str(r.get("request") or ""))) >= MIN_WORDS
        ]
        texts = [" ".join(str(r["request"]).split())[:500] for r in asks]
        vectors = self.rt.brain.embed(texts) if texts else None
        words = [_words(t) for t in texts]

        def alike(i: int, j: int) -> bool:
            if vectors:
                return _cosine(vectors[i], vectors[j]) >= MEANING
            shared = len(words[i] & words[j]) / max(1, len(words[i] | words[j]))
            return shared >= WORDS

        groups: builtins.list[builtins.list[int]] = []
        for index in range(len(texts)):
            home = next((g for g in groups if alike(g[0], index)), None)
            if home is None:
                groups.append([index])
            else:
                home.append(index)
        out = []
        for members in groups:
            if len(members) < ALIKE:
                continue
            examples = list(dict.fromkeys(texts[i] for i in members))[:5]
            out.append(
                {
                    "kind": "asks",
                    "key": "asks:" + _key(texts[members[0]]),
                    "title": cut(texts[members[0]], 120),
                    "count": len(members),
                    "examples": examples,
                    "apps": sorted({str(asks[i].get("app") or "") for i in members} - {""}),
                    "last": max(str(asks[i].get("at") or "") for i in members),
                    "prompt_id": None,
                    "ask": "Write a skill for what I keep asking for, like: "
                    + "; ".join(f'"{e}"' for e in examples[:3]),
                }
            )
        return out, "meaning" if vectors else "words"
