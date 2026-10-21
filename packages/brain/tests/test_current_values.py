"""Two values for one thing on the same date are a conflict: both are sent, labelled, and
neither is passed off as current. A newer dated value still replaces an older one (Release 1
plan, M04: no newest-wins)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


def _fact(note_id, as_of, body, **extra):
    return {"id": note_id, "area": "work", "topic": "general", "kind": "fact",
            "title": note_id, "summary": body, "as_of": as_of, "body": body, **extra}


class CurrentValueTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def ask(self, notes, request):
        se.add_notes(self.vault, notes)
        brain = se.open_brain(self.vault)
        try:
            return brain.context(request, record=False, include_kernel=False)
        finally:
            brain.close()

    def test_same_date_values_are_both_sent_as_a_conflict(self):
        found = self.ask([
            _fact("seats-a", "2026-10-12", "The workshop room seats 60 people."),
            _fact("seats-b", "2026-10-12", "The workshop room seats 50 people."),
        ], "How many people does the workshop room seat?")
        sent = set(found.data["note_ids"])
        self.assertEqual({"seats-a", "seats-b"} & sent, {"seats-a", "seats-b"})
        self.assertFalse(set(found.data["older_ids"]) & {"seats-a", "seats-b"})
        self.assertEqual(set(found.data["conflict_ids"]), {"seats-a", "seats-b"})
        self.assertIn("neither is settled as current", found.text)

    def test_a_newer_date_still_replaces_the_older_value(self):
        found = self.ask([
            _fact("seats-old", "2026-09-01", "The workshop room seats 40 people."),
            _fact("seats-new", "2026-10-12", "The workshop room seats 60 people."),
        ], "How many people does the workshop room seat?")
        self.assertIn("seats-new", found.data["note_ids"])
        self.assertIn("seats-old", found.data["older_ids"])
        self.assertEqual(found.data["conflict_ids"], [])


if __name__ == "__main__":
    unittest.main()
