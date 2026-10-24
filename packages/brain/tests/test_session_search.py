"""Session search: past conversations found by what they asked and were given, each with its
id, date, app and what it was given (v4 spec, section 6)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class SessionSearchTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "run-of-show", "area": "work", "topic": "general", "kind": "fact",
             "title": "Run of show", "body": "Session 1 opens with Dana Ruiz."},
            {"id": "floor-notes", "area": "work", "topic": "general", "kind": "fact",
             "title": "Floor Notes", "body": "Episode 12 is about kitchens."}])
        self.brain = se.open_brain(self.vault)
        self.brain.client = "Claude Code"
        self.first = self.brain.context("Draft the run of show for session 1")
        self.brain.client = "Cursor"
        self.brain.context("Outline Floor Notes episode 12")

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_search_finds_the_conversation_with_its_id_date_app_and_what_it_was_given(self):
        found = self.brain.sessions_search("run of show")
        sessions = found.data["sessions"]
        self.assertEqual(len(sessions), 1)
        hit = sessions[0]
        self.assertEqual(hit["session_id"], self.first.data["session_id"])
        self.assertEqual(hit["app"], "Claude Code")
        self.assertTrue(hit["date"])
        self.assertEqual(hit["did"], "Draft the run of show for session 1")
        self.assertTrue(any(g.startswith("Brain map · ") for g in hit["given"]))
        self.assertTrue(any(g.startswith("Run of show") for g in hit["given"]))
        self.assertEqual(hit["receipts"], [self.first.data["packet_id"]])

    def test_words_that_no_conversation_used_find_nothing(self):
        self.assertEqual(self.brain.sessions_search("lighthouse budget").data["sessions"], [])

    def test_a_search_needs_words(self):
        self.assertTrue(self.brain.sessions_search("  ").is_error)


if __name__ == "__main__":
    unittest.main()
