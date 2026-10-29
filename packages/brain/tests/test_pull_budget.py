"""Opening notes after a packet is budgeted per request, and nothing is paid for twice
(Release 1 plan, section 10.3)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class PullBudgetTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
        config["pulls"] = {"items": 2, "tokens": 1500}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        se.add_notes(self.vault, [
            {"id": f"note-{i}", "area": "work", "topic": "general", "kind": "fact",
             "title": f"Note {i}", "summary": f"Fact number {i}.", "body": f"Fact number {i}."}
            for i in range(4)])
        self.brain = se.open_brain(self.vault)
        self.session = self.brain.context("What do we know?").data["session_id"]

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def open(self, note_id, **extra):
        return self.brain.note(note_id, session_id=self.session, **extra)

    def test_a_note_opened_twice_is_not_sent_again_unless_asked_in_full(self):
        self.assertIn("Fact number 0.", self.open("note-0").text)
        again = self.open("note-0")
        self.assertEqual(again.data["status"], "already_delivered")
        self.assertNotIn("Fact number 0.", again.text)
        self.assertIn("Fact number 0.", self.open("note-0", full=True).text)

    def test_past_the_budget_only_names_come_back_until_the_next_packet(self):
        self.open("note-0")
        self.open("note-1")
        over = self.open("note-2")
        self.assertTrue(over.is_error)
        self.assertEqual(over.data["status"], "over_pull_budget")
        self.assertIn("Note 2", over.text)
        self.assertNotIn("Fact number 2.", over.text)
        self.brain.context("Anything else?", session_id=self.session)
        self.assertIn("Fact number 2.", self.open("note-2").text)

    def test_the_packet_says_what_may_still_be_opened(self):
        found = self.brain.context("Anything else?", session_id=self.session)
        self.assertIn("Pull budget: 2 more items (about 1,500 tokens)", found.text)


if __name__ == "__main__":
    unittest.main()
