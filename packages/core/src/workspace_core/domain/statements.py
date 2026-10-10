"""The one vocabulary of what a statement in the Brain is, in the workspace's words
(brain-logic plan 6). It mirrors the Brain's own (`brainkit.statements`), which the core does
not import; the server's tests keep the two the same."""

from __future__ import annotations

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
# What distillation asks a model for.
DISTILL_KINDS = ("fact", "rule", "preference", "decision", "procedure")
# What the knowledge agent suggests in a conversation.
AGENT_KINDS = ("fact", "rule", "decision", "preference")


def words(kinds: tuple[str, ...]) -> str:
    """Kinds as a sentence names them: "fact, rule or decision"."""
    if len(kinds) < 2:
        return "".join(kinds)
    return ", ".join(kinds[:-1]) + f" or {kinds[-1]}"
