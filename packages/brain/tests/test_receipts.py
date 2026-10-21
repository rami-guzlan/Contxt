"""A request's receipt is exactly what was delivered: sent, opened after, did not fit, already
held, unknown, and the tokens with how they were counted (Release 1 plan, M07)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class ReceiptTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "invoice-days", "area": "work", "topic": "money", "kind": "fact",
             "title": "Invoice days", "summary": "When invoices go out.",
             "body": "Invoices go out on the 1st and the 15th of each month."},
            {"id": "accountant", "area": "work", "topic": "money", "kind": "fact",
             "title": "Our accountant", "summary": "Who does the books.",
             "body": "Our accountant is Lena Park at Park and Hale."}])
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_the_receipt_lists_what_was_sent_and_what_was_opened_after(self):
        packet = self.brain.context("When do invoices go out?")
        self.brain.note("accountant", session_id=packet.data["session_id"])
        found = self.brain.receipt(packet.data["packet_id"])
        self.assertFalse(found.is_error, found.text)
        receipt = found.data
        self.assertIn("invoice-days", [s["id"] for s in receipt["sent"]])
        self.assertIn("Brain map", [s["title"] for s in receipt["sent"]])
        self.assertEqual([o["id"] for o in receipt["opened"]], ["accountant"])
        self.assertGreater(receipt["tokens"]["total"], receipt["tokens"]["packet"])
        self.assertIn(receipt["tokens"]["counted"].split(" ")[0], ("exact", "estimated"))
        self.assertFalse(receipt["complete"])
        self.assertIn("not proof", found.text)

    def test_a_receipt_does_not_change_after_later_requests(self):
        packet = self.brain.context("When do invoices go out?")
        before = self.brain.receipt(packet.data["packet_id"]).data
        self.brain.context("Who does the books?", session_id=packet.data["session_id"])
        self.brain.note("accountant", session_id=packet.data["session_id"])
        self.assertEqual(self.brain.receipt(packet.data["packet_id"]).data, before)

    def test_a_request_nothing_matched_says_so_under_unknown(self):
        packet = self.brain.context("What is the airspeed of a laden swallow?")
        receipt = self.brain.receipt(packet.data["packet_id"]).data
        self.assertEqual(receipt["unknown"], ["Nothing in the Brain matched this request."])

    def test_an_unknown_receipt_says_so(self):
        found = self.brain.receipt("pkt-missing")
        self.assertTrue(found.is_error)


if __name__ == "__main__":
    unittest.main()
