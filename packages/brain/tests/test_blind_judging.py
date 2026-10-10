"""Blind judging (brain-logic plan 9): a model check reads the two texts without who proposed
them, so its verdict on a seeded pair is the same when the proposer is hidden or swapped."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import review
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")

PAIRS = [
    ("Webinar slides use the light template.", "Webinar slides use the dark template."),
    ("Posts go out on Mondays.", "LinkedIn posts go out on Tuesdays and Thursdays."),
    ("The booth rental costs 900 dollars.", "The trade show booth rental costs 1200 dollars."),
]


def asked(proposer: str | None) -> list[dict]:
    """What the model check is asked about the seeded pairs, with `proposer` (None: hidden)."""
    vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
    brain = Brain(vault, embeddings=False)
    try:
        owner = brain.state().config.owner
        for _new, old in PAIRS:
            made = brain.propose(area="marketing", topic="style", text=old, note_kind="rule",
                                 principal=owner, force_pending=True)
            brain.approve(made.data["proposal_id"], actor=owner)
        for new, _old in PAIRS:
            extra = {"proposed_by": proposer} if proposer else None
            brain.propose(area="marketing", topic="style", text=new, note_kind="rule",
                          principal=owner, force_pending=True, extra=extra)
        checks = review.pending_checks(brain, limit=10)
        return sorted(({"text": c["text"],
                        "pairs": sorted((p["key"], p["text"]) for p in c["pairs"])}
                       for c in checks), key=lambda c: c["text"])
    finally:
        brain.close()
        shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


class BlindJudgingTest(unittest.TestCase):
    def test_the_check_is_the_same_whoever_proposed_it(self):
        hidden = asked(None)
        self.assertTrue(hidden and all(c["pairs"] for c in hidden), hidden)
        self.assertEqual(asked("owner"), hidden)
        self.assertEqual(asked("claude-code"), hidden)
        flat = repr(hidden)
        for who in ("claude-code", "proposed_by", "approved_by", "principal"):
            self.assertNotIn(who, flat)


if __name__ == "__main__":
    unittest.main()
