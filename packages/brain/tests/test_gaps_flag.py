"""What the Brain did not hold is flagged, never guessed, and shows with the other gaps."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class GapsFlagTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_flagged_question_shows_in_the_gaps_and_can_be_dismissed(self):
        made = self.brain.flag_gap("What is the venue's capacity?", session_id="sess-abc123")
        self.assertEqual(made.data["status"], "flagged")
        (gap,) = [g for g in self.brain.gaps().data["gaps"] if g["kind"] == "flagged"]
        self.assertEqual(gap["request"], "What is the venue's capacity?")
        self.brain.dismiss_gap(gap["key"])
        self.assertFalse([g for g in self.brain.gaps().data["gaps"] if g["kind"] == "flagged"])
        self.assertTrue(self.brain.flag_gap("  ").is_error)


if __name__ == "__main__":
    unittest.main()
