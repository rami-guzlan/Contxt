"""A must-hold comes in by meaning only when its domain is about as close to the request as
the request's best note: a domain clearly less like the request than its best note is
another part of the same Brain's work (general-retrieval plan, look-alike must-holds)."""
from __future__ import annotations

import os
import shutil
import unittest
from unittest import mock

from brainkit import router
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class RelativeMustHoldTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "wine-deliveries", "area": "work", "topic": "suppliers", "kind": "fact",
             "title": "Wine deliveries", "summary": "When the wine rep delivers.",
             "body": "The wine rep delivers on Mondays before noon."},
            {"id": "allergy-check", "area": "me", "topic": "kitchen", "kind": "rule",
             "title": "Allergy check", "summary": "Allergy orders are checked at the pass.",
             "load": "domain", "applies_to": "me", "must_text":
             "Every allergy order is checked at the pass before it goes out.",
             "body": "Every allergy order is checked at the pass before it goes out."}])
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def must_holds(self, domain_cosine):
        sims = {"note:wine-deliveries": 0.80, "domain:allergy-check": domain_cosine}
        with mock.patch.object(router.Router, "similarity", return_value=sims):
            data = self.brain.context("Draft an email to our wine rep about deliveries",
                                      record=False, include_kernel=False).data
        return set(data.get("must_hold_ids") or [])

    def test_a_domain_well_below_the_best_note_stays_out(self):
        self.assertTrue(router.Policy().must_hold_relative)
        self.assertNotIn("allergy-check", self.must_holds(0.66))

    def test_a_domain_as_close_as_the_best_note_comes_in(self):
        self.assertIn("allergy-check", self.must_holds(0.79))


if __name__ == "__main__":
    unittest.main()
