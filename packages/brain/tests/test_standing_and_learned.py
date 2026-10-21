"""A standing permission lets one kind of change from one origin into one area at once; an
undo of a change that went in on its own teaches Auto to ask first for that kind, visibly and
removably (Release 1 plan, M08; design contracts 8 and 9)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import checkpoints, governance
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
FACTS = ["Our studio is on the third floor.", "The studio opens at nine.",
         "We close the studio on Fridays at four.", "The studio has two meeting rooms.",
         "Parking at the studio is on the street."]


class _Brain:
    def setUp(self, governance_fields=None):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        config.setdefault("governance", {}).update(governance_fields or {
            "preset": "careful",
            "standing": [{"type": "fact", "origin": "chat", "area": "work"},
                         {"type": "fact", "origin": "chat", "area": "me", "paused": True}]})
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        self.brain = se.open_brain(self.vault)
        self.facts = iter(FACTS)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def propose(self, area):
        return governance.propose_note(
            self.brain, area=area, topic="studio", text=next(self.facts), title="Studio",
            note_kind="fact", scope="company", capture_origin="chat")



class StandingTest(_Brain, unittest.TestCase):
    def test_a_standing_permission_applies_only_where_it_is_scoped_and_not_paused(self):
        self.assertEqual(self.propose("work").data["status"], "applied")
        self.assertEqual(self.propose("me").data["status"], "pending")  # paused
        self.assertEqual(self.propose("people").data["status"], "pending")  # not covered


class LearnedTest(_Brain, unittest.TestCase):
    def setUp(self):
        super().setUp({"preset": "personal"})  # chat facts go in on their own

    def test_undoing_a_change_teaches_ask_first_and_forgetting_it_restores_the_setting(self):
        made = self.propose("work")
        self.assertEqual(made.data["status"], "applied")
        undone = checkpoints.undo(self.brain, made.data["checkpoint"]["id"], actor="person:me")
        self.assertFalse(undone.is_error, undone.text)
        (rule,) = undone.data["learned"]
        self.assertIn("Ask first before a fact from chat goes into work", rule["says"])
        waits = self.propose("work")
        self.assertEqual(waits.data["status"], "pending")
        self.assertIn("you undid one like it", waits.text)
        self.assertEqual([r["id"] for r in self.brain.learned().data["rules"]], [rule["id"]])
        self.assertFalse(self.brain.forget_learned(rule["id"]).is_error)
        self.assertEqual(self.propose("work").data["status"], "applied")


if __name__ == "__main__":
    unittest.main()
