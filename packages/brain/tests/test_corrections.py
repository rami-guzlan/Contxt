"""A correction made from a receipt says what went wrong, and only proposes: a fact is never
changed by it (Release 1 plan, M07). Wrong, outdated or misread items get a "Still true?"
card; missing context, irrelevant items, budget cuts and ignored context are recorded
against the receipt, for review and evaluation."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import corrections, governance
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class CorrectionTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "invoice-days", "area": "work", "topic": "money", "kind": "fact",
             "title": "Invoice days", "summary": "When invoices go out.",
             "body": "Invoices go out on the 1st and the 15th of each month."}])
        self.brain = se.open_brain(self.vault)
        found = self.brain.context("When do invoices go out?", session_id=None)
        self.packet = found.data["packet_id"]

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_outdated_information_raises_a_still_true_card_and_changes_nothing(self):
        made = corrections.correct(self.brain, self.packet, "outdated", item="invoice-days",
                                   note="Invoices moved to the 5th.")
        self.assertFalse(made.is_error, made.text)
        self.assertEqual(made.data["outcome"], "challenge")
        waiting = [p for p in governance.inbox(self.brain).data["proposals"]
                   if p["kind"] == "note.challenge"]
        self.assertEqual(len(waiting), 1)
        note = self.brain.state().index.note("invoice-days")
        self.assertIn("1st and the 15th", note.body)

    def test_an_item_that_was_not_in_the_receipt_is_refused(self):
        made = corrections.correct(self.brain, self.packet, "wrong_information",
                                   item="someone-else")
        self.assertTrue(made.is_error)

    def test_missing_context_is_recorded_against_the_receipt(self):
        made = corrections.correct(self.brain, self.packet, "missing",
                                   note="It should know the late fee.")
        self.assertEqual(made.data["outcome"], "recorded")
        listed = corrections.listed(self.brain, packet_id=self.packet)
        self.assertEqual([(c["kind"], c["note"]) for c in listed],
                         [("missing", "It should know the late fee.")])

    def test_an_unknown_kind_or_receipt_is_refused(self):
        self.assertTrue(corrections.correct(self.brain, self.packet, "nonsense").is_error)
        self.assertTrue(corrections.correct(self.brain, "pk_none", "missing").is_error)


if __name__ == "__main__":
    unittest.main()
