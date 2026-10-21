"""Taste, as the owner writes it: entries by lens, kept like any note, and sent with every
request to write or make something (Release 1 plan; design contract 20)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import destinations, governance
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class TasteTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "invoice-days", "area": "work", "topic": "money", "kind": "fact",
             "title": "Invoice days", "summary": "When invoices go out.",
             "body": "Invoices go out on the 1st and the 15th."}])
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def keep(self, made):
        self.assertFalse(made.is_error, made.text)
        if made.data.get("proposal_id"):
            kept = governance.approve(self.brain, made.data["proposal_id"], actor="person:me")
            self.assertFalse(kept.is_error, kept.text)
        return made.data["id"]

    def test_entries_are_kept_by_lens_and_a_pair_needs_its_other_side(self):
        self.keep(self.brain.propose_taste("Say the thing in the headline.", lens="works"))
        self.keep(self.brain.propose_taste("Warm, plain", lens="feels", kind="pair",
                                           not_that="breezy, salesy", strength="always"))
        self.assertTrue(self.brain.propose_taste("Bold", lens="looks", kind="pair").is_error)
        found = self.brain.taste().data
        self.assertEqual(found["count"], 2)
        self.assertEqual(found["lenses"]["feels"][0]["not_that"], "breezy, salesy")
        self.assertEqual(found["lenses"]["feels"][0]["strength"], "always")

    def test_writing_brings_the_taste_and_a_lookup_does_not(self):
        entry = self.keep(self.brain.propose_taste("Say the thing in the headline.",
                                                   lens="works"))
        writing = self.brain.context("Write a short post announcing our new invoice days.",
                                     record=False, include_kernel=False).data
        self.assertIn(entry, writing["note_ids"])
        lookup = self.brain.context("When do invoices go out?", record=False,
                                    include_kernel=False).data
        self.assertNotIn(entry, lookup["note_ids"])

    def test_a_distilled_piece_can_go_to_taste_and_waits(self):
        made = destinations.propose(self.brain, "taste", "Never say world-class.",
                                    lens="works", kind="avoid")
        self.assertEqual(made.data["status"], "pending")


if __name__ == "__main__":
    unittest.main()
