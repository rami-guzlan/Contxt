"""Triage (brain-logic plan 7.2, step 2): before the owner's chosen model distills something
brought in, a cheaper model reads it in parts and says which parts may hold something durable.
Only those reach distillation, so a long transcript of small talk costs one cheap call instead
of a full reading.

Off until it is measured (decision 7: code, then Haiku 5.5 or a local model that passed the
qualification set, then the chosen model): the distillation settings name the model that
triages (`triage`), or none. Under the regulated preset only a local model triages, or the text
is redacted first (decision 7). Its answer is checked like any other: a part it does not name
is left out, a malformed answer keeps everything.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from workspace_core.services import prepass

from .models import Models

log = logging.getLogger(__name__)
MAX_PARTS = 60  # parts one triage call reads; a longer text keeps its tail whole
PART_CHARS = 700  # of each part shown to the triage model
PROMPT = """You sort the parts of something a person brought into their Brain, before a more \
careful model reads it. For each numbered part, decide whether it may hold something durable: \
a fact, a decision, a rule or preference, a procedure, a value with its date, or anything about \
the person's goals and projects that will still be true next month. Small talk, greetings, \
logistics of the call itself and chatter are not durable. When unsure, keep the part.

Answer with JSON only: {"keep": [the numbers of the parts to keep]}.

The parts:
"""


class Triage:
    """A cheap first reading, through one of the models the app can ask."""

    def __init__(self, models: Models, who: Any | None = None) -> None:
        self.models = models
        self.who = who

    def keep(self, model_id: str, text: str, *, redacting: bool = False) -> list[int] | None:
        """The parts (indexes into prepass.split) worth distilling, or None to read it all."""
        kept_text, _dropped = prepass.clean(text)
        parts = prepass.split(kept_text)
        if len(parts) < 3:
            return None  # too short to be worth a triage call
        shown = parts[:MAX_PARTS]
        body = "\n\n".join(
            f"[{i}] {prepass.redact(p.text) if redacting else p.text}"[:PART_CHARS]
            for i, p in enumerate(shown)
        )
        try:
            choice = self.models.choose(model_id)
            owner = self.who or self.models.runners.ws.owner()
            answer = self.models.ask(owner, choice, PROMPT + body, json_only=True, job="triage")
        except Exception:  # a triage that cannot run reads it all, as before
            log.warning("Triage could not run; distillation reads everything", exc_info=True)
            return None
        kept = read_answer(answer, len(shown))
        if kept is None:
            return None
        return sorted(set(kept) | set(range(len(shown), len(parts))))


def read_answer(answer: str, parts: int) -> list[int] | None:
    """The kept part numbers from a triage answer, or None when it cannot be read."""
    found = re.search(r"\{.*\}", str(answer or ""), re.S)
    if not found:
        return None
    try:
        data = json.loads(found.group(0))
    except ValueError:
        return None
    keep = data.get("keep") if isinstance(data, dict) else None
    if not isinstance(keep, list):
        return None
    return [int(i) for i in keep if isinstance(i, int) and 0 <= i < parts]
