"""Proof (brain-logic plan 10.6): the drift eval, the four-week soak and the alignment tax hold
their bars on the demo Brains with stand-ins."""
from __future__ import annotations

import os
import unittest

from brainkit import proof

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
VAULT = os.path.join(ROOT, "brains", "knowledge-company", "vault")


class DriftTest(unittest.TestCase):
    def test_re_anchoring_keeps_a_bounded_reader_on_its_contract(self):
        found = proof.drift()
        with_, without = found["with"], found["without"]
        self.assertEqual((with_["must_holds_in_view"], with_["finished"]), (1.0, 1.0))
        # The one objective lost with re-anchoring is a distractor in the last few calls,
        # closer to the end than the cadence: the residual risk the gate's check must catch.
        lost = [r for r in found["rows"] if r["anchoring"] and not r["objective_kept"]]
        self.assertTrue(all(r["late_distractor"] for r in lost), lost)
        self.assertLessEqual(len(lost), 1)
        self.assertLess(without["objective_kept"], with_["objective_kept"])
        self.assertLess(without["must_holds_in_view"], with_["must_holds_in_view"])
        self.assertEqual(without["finished"], 0.0)


class SoakTest(unittest.TestCase):
    def test_four_weeks_stay_stable_and_say_what_moved(self):
        found = proof.soak(VAULT, weeks=4)
        summary = found["summary"]
        self.assertTrue(summary["kernel_stable"])
        self.assertEqual(summary["moved_unexplained"], 0)
        self.assertEqual(summary["stale_left"], 0)
        self.assertEqual(summary["stale_caught"], 4)
        self.assertEqual(summary["exceptions_flagged_week"], 3)
        self.assertLessEqual(summary["max_cards_per_goal_week"], 1)
        # Items left waiting slip twice (needs attention, then off track): one card, once.
        weeks = {r["week"]: r for r in found["weeks"]}
        self.assertEqual(weeks[3]["statuses"]["goal-nothing-waits"], "needs_attention")
        self.assertEqual(weeks[4]["cards_by_goal"].get("goal-nothing-waits"), 1)
        self.assertTrue(all(r["correction_named"] for r in found["weeks"]))


class AlignmentTaxTest(unittest.TestCase):
    def test_the_tax_is_counted_and_later_briefs_pay_less(self):
        found = proof.alignment_tax(VAULT)
        self.assertGreater(found["first_share"], 0)
        self.assertLess(found["first_share"], 1)
        self.assertLess(found["later_share"], found["first_share"])
        self.assertLess(found["check_ms"], 50)


if __name__ == "__main__":
    unittest.main()
