"""What goes in on its own pauses after a daily cap and says so; the rest waits in Catch up
(Release 1 plan, M08 and design contract 9)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import governance
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class AutoCapTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        config.setdefault("governance", {})["auto_daily_cap"] = 2
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    HABITS = {3: "I drink green tea in the morning.", 5: "I keep my desk clear on Fridays.",
              7: "I read fiction before bed.", 9: "I walk to the market on Saturdays."}

    def propose(self, n, origin="chat"):
        return governance.propose_note(
            self.brain, area="me", topic="habits", text=self.HABITS[n],
            title=f"Habit {n}", scope="person:me", capture_origin=origin)

    def test_past_the_cap_changes_wait_and_say_auto_is_paused(self):
        first, second, third = (self.propose(n) for n in (3, 5, 7))
        self.assertEqual([r.data.get("status") for r in (first, second)],
                         ["applied", "applied"])
        self.assertEqual(third.data["status"], "pending")
        self.assertTrue(third.data["paused"])
        self.assertIn("Auto is paused", third.text)
        self.assertEqual(governance.auto_applied_since(self.brain), 2)

    def test_the_owners_own_changes_in_the_app_are_not_capped(self):
        for n in (3, 5):
            self.propose(n)
        self.assertEqual(self.propose(9, origin="app").data["status"], "applied")


if __name__ == "__main__":
    unittest.main()
