"""Capture: notice durable context in what a person says, and remind the agent to keep it.

The person should never have to ask for something to be remembered. When a message states
something that will still matter later (a rule, a correction, a preference, a decision, a
changed fact, a procedure, a lasting document), the brain says so in the packet, and the
Claude Code hook says so on the raw message. The agent then proposes it; governance decides
what becomes live.

DETECTION ONLY EVER NUDGES. It never writes anything, so it favours precision: a missed cue
costs one reminder, a false one costs a line of noise in every packet that trips it. It is
generic English and names no organization, product or person.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

MAX_SENTENCE = 300

_FLAGS = re.IGNORECASE
_DETERMINERS = r"(?:we|i|they|he|she|the (?:client|team|board|owner|ceo|boss|customer|partner|" \
               r"committee|company|business))"
_DECISION_VERB = r"(?:(?:has|have|had|just|finally|officially|now)\s+)*" \
                 r"(?:decided|agreed|approved|signed off|confirmed|chose)\b"

# (kind, pattern) in order: the first kind whose pattern matches a sentence wins.
PATTERNS = [
    ("procedure", re.compile(
        r"\b(?:here'?s|here is) how (?:we|you|i|to)\b|"
        r"\b(?:our|the) (?:process|workflow|procedure|checklist|playbook|steps?) "
        r"(?:for|to|is|are|when)\b|\bstep 1\b", _FLAGS)),
    ("reference", re.compile(
        r"\b(?:i'?ve|i have|we'?ve|we have) attached\b|\battached (?:is|are) (?:the|our|a|an)\b|"
        r"\bhere'?s (?:our|the) (?:updated |new |latest |current |final )?(?:brand guide|"
        r"style guide|guide|playbook|template|deck|document|doc|brief|spec|handbook|manual|"
        r"policy|price list|rate card)\b|"
        r"\b(?:keep|save|file|store) (?:this|it|these|them) (?:for|as|in)\b", _FLAGS)),
    ("decision", re.compile(rf"\b{_DETERMINERS}\s+{_DECISION_VERB}", _FLAGS)),
    ("decision", re.compile(rf"\b[A-Z][a-z]+\s+{_DECISION_VERB}")),
    ("decision", re.compile(
        r"\b(?:is|are) going to be (?:the|our) (?:basis|base|foundation|core|backbone|home|"
        r"source of truth|standard|default|center|centre)\b|"
        r"\bwill be (?:the|our) (?:basis|base|foundation|core|backbone|source of truth|standard|"
        r"default)\b|\b(?:the|our) (?:plan|goal|strategy|direction) is\b|"
        r"\b(?:we|i) plan to\b", _FLAGS)),
    ("rule", re.compile(
        r"\bit(?:'s| is) (?:really |very |so )?important (?:that|this|to|for|we)\b|"
        r"\b(?:the|our) (?:top )?priority is\b|"
        r"\b(?:from now on|going forward|moving forward|from here on|in (?:the )?future|"
        r"next time|every time|each time|whenever)\b|"
        r"^(?:always|never)\b(?! mind)|"
        r"\b(?:we|you|i|they) (?:should |must |will |need to )?(?:always|never)\b|"
        r"\b(?:always|never) (?:use|say|write|call|mention|put|add|include|send|publish|post|"
        r"start|end|refer|lead|open|close|sign)\b", _FLAGS)),
    ("correction", re.compile(
        r"^(?:actually|correction|not quite|nope|no,)\b|"
        r"\bthat'?s (?:wrong|not right|incorrect|outdated|out of date|not true)\b|"
        r"\b(?:don'?t|do not|stop|quit) (?:ever )?(?:using|use|saying|say|writing|write|"
        r"calling|call|mentioning|mention|putting|put|adding|add|including|include|sending|"
        r"send)\b.*\b(?:anymore|any more|again|ever)\b", _FLAGS)),
    ("preference", re.compile(
        r"\bi(?: really)? (?:prefer|like it when|want you to|hate it when|dislike|"
        r"don'?t like|do not like)\b|\bi'?d rather\b|\bi would rather\b", _FLAGS)),
    ("memory", re.compile(
        r"\b(?:please )?(?:remember|keep in mind|don'?t forget|do not forget|make a note|"
        r"take note|note that)\b|\bfor (?:future )?reference\b|\bfor the record\b|\bfyi\b|"
        r"\bheads up\b", _FLAGS)),
    ("fact", re.compile(
        r"\b(?:is|are) now\b|\b(?:has|have) changed\b|\bchanged to\b|\brenamed\b|"
        r"\bmoved to\b|\bno longer\b|\breplaced (?:by|with)\b|\bour new\b", _FLAGS)),
]

# Kinds that describe how to work: a sentence tied to the draft at hand is a one-off edit.
_STANDING_KINDS = {"rule", "correction", "preference"}
_ONE_OFF = re.compile(
    r"\b(?:in |for )?(?:this|that) (?:post|one|draft|version|paragraph|email|sentence|section|"
    r"slide|caption|reply|message|time)\b|\bfor now\b|\bjust this\b|\bright here\b", _FLAGS)
_IDIOMS = re.compile(r"\bnever mind\b|\bnevermind\b", _FLAGS)
_POLITE_ASK = re.compile(r"^(?:can|could|would|will) you (?:please )?(?:remember|note|keep|"
                         r"save|file|store)\b", _FLAGS)
_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+")

TOOL_FOR = {"procedure": "propose_skill", "reference": "add_file"}


@dataclass(frozen=True)
class Candidate:
    kind: str          # rule | correction | preference | decision | memory | fact | procedure |
    #                    reference
    cue: str           # the words that tripped it
    sentence: str      # the sentence to quote, clipped

    @property
    def tool(self) -> str:
        return TOOL_FOR.get(self.kind, "propose_note")


def sentences(text: str) -> list[str]:
    out = []
    for part in _SPLIT.split(str(text or "")):
        part = part.strip(" \t-*•")
        if part:
            out.append(part)
    return out


def _clip(sentence: str) -> str:
    flat = " ".join(sentence.split())
    return flat if len(flat) <= MAX_SENTENCE else flat[:MAX_SENTENCE - 3].rstrip() + "..."


def classify(sentence: str) -> Candidate | None:
    """The first capture cue in one sentence, or None for an ordinary request."""
    if not sentence or _IDIOMS.search(sentence):
        return None
    question = sentence.rstrip().endswith("?")
    if question and not _POLITE_ASK.search(sentence):
        return None
    for kind, pattern in PATTERNS:
        match = pattern.search(sentence)
        if not match:
            continue
        if kind in _STANDING_KINDS and _ONE_OFF.search(sentence):
            return None
        return Candidate(kind=kind, cue=match.group(0).strip(), sentence=_clip(sentence))
    return None


def detect(text: str, limit: int = 3) -> list[Candidate]:
    """Sentences in `text` that state something durable, at most `limit`, in order."""
    out, seen = [], set()
    for sentence in sentences(text):
        candidate = classify(sentence)
        if candidate is None:
            continue
        key = " ".join(candidate.sentence.lower().split())
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
        if len(out) >= limit:
            break
    return out


def nudge(candidates) -> str:
    """Markdown telling the agent what looks durable and how to keep it. Empty when nothing."""
    candidates = list(candidates or [])
    if not candidates:
        return ""
    lines = ["Possible durable context in this message:"]
    lines += [f'- "{c.sentence}" ({c.kind})' for c in candidates]
    tools = list(dict.fromkeys(c.tool for c in candidates))
    lines += ["",
              "If it will still be true next month, applies beyond this task, is not already in "
              "the brain, and you can say who said it, capture it now with "
              + " / ".join(f"`{t}`" for t in tools)
              + " (quote the words in `evidence`). Do not ask first: shared knowledge waits "
              "for the owner's review, and a one-off instruction only needs doing. Project "
              "progress goes to `record_focus_update` instead."]
    return "\n".join(lines)
