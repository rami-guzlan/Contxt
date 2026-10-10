"""The one vocabulary of what a statement in the Brain is, in the workspace's words
(brain-logic plan 6). It mirrors the Brain's own (`brainkit.statements`), which the core does
not import; the server's tests keep the two the same."""

from __future__ import annotations

import hashlib

# What a person, a run or the knowledge agent may propose: the Brain's kinds, with a rule's
# subtypes (a preference, a convention) in a person's words.
PROPOSAL_KINDS = (
    "fact",
    "rule",
    "preference",
    "convention",
    "decision",
    "procedure",
    "identity",
    "state",
    "goal",
)
# Who said it: the owner; the owner's AI, by inference; another person (in a meeting or an
# email); a document; a synced system; an agent's run.
SAID_BY = ("owner", "owner-ai", "person", "document", "system", "agent")
# What distillation asks a model for.
DISTILL_KINDS = ("fact", "rule", "preference", "decision", "procedure")
# What the knowledge agent suggests in a conversation.
AGENT_KINDS = ("fact", "rule", "decision", "preference")


def fingerprint(text: str) -> str:
    """The same text, whatever its spacing and case: what hash dedupe compares (7.1)."""
    plain = " ".join(str(text or "").lower().split())
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()[:32]


def words(kinds: tuple[str, ...]) -> str:
    """Kinds as a sentence names them: "fact, rule or decision"."""
    if len(kinds) < 2:
        return "".join(kinds)
    return ", ".join(kinds[:-1]) + f" or {kinds[-1]}"
