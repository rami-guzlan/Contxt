"""The sheets the Brain keeps by itself are worked out from what it holds, when read
(Release 1 plan, M11): Project status, and Open loops this week."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import focus
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class DerivedTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        self.brain = se.open_brain(self.vault)
        made = focus.create_focus(self.brain, "Spring launch", "Launch the spring line.")
        assert not made.is_error, made.text
        focus.record_update(self.brain, "Spring launch", "Photos are booked.",
                            {"next": "Write the launch email"})

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_project_status_reads_each_projects_latest_update_and_next_step(self):
        found = self.brain.get_state(sheet="project-status")
        self.assertFalse(found.is_error, found.text)
        (row,) = found.data["rows"]
        self.assertEqual((row["Project"], row["Latest"], row["Next up"]),
                         ("Spring launch", "Photos are booked.", "Write the launch email"))
        self.assertTrue(found.data["derived"])
        self.assertIn("Spring launch [active]: Photos are booked.", found.text)

    def test_open_loops_is_empty_when_nothing_is_due_and_both_are_on_the_map(self):
        self.assertIn("Nothing here right now", self.brain.get_state(sheet="open-loops").text)
        lines = self.brain.brain_map().data["lines"]
        self.assertIn("sheet Project status: Status, Latest, Next up, Days quiet", lines)


if __name__ == "__main__":
    unittest.main()
