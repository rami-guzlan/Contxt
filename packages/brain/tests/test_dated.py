"""Dated values: a figure that changes (a total, a count, a version) carries the day it was
true; a brief carries the newest and lists the older ones as older values; a newer dated value
is an update, not a disagreement; past its last day, a note is flagged for a check."""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import review, util
from brainkit.api import Brain
from tests import fixture


class DatedValueTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def add(self, text, as_of, **kwargs):
        kwargs.setdefault("scope", "company")
        made = self.brain.propose(layer="state", topic="pipeline", text=text, as_of=as_of,
                                  **kwargs)
        self.assertFalse(made.is_error, made.text)
        if made.data["status"] == "pending":
            self.assertFalse(self.brain.approve(made.data["proposal_id"]).is_error)
        return made.data["id"]

    def test_a_brief_carries_the_newest_value_and_lists_the_older(self):
        older = self.add("The sales pipeline holds 4 open proposals worth $48,000.", "2026-09-01")
        newer = self.add("The sales pipeline holds 6 open proposals worth $71,000.", "2026-10-01")
        data = self.brain.context("How big is the sales pipeline right now?",
                                  record=False, include_kernel=False)
        self.assertIn(newer, data.data["note_ids"])
        self.assertNotIn(older, data.data["note_ids"])
        self.assertEqual(data.data["older_ids"], [older])
        self.assertIn("(as of Oct 1, 2026)", data.text)
        self.assertIn("## Older values (not current)", data.text)
        self.assertIn(f"as of Sep 1, 2026; `{older}`", data.text)
        self.assertNotIn("$48,000", data.text)
        pairs = self.brain.attention().data["dated"]
        self.assertEqual([(p["older"]["id"], p["newer"]["id"]) for p in pairs], [(older, newer)])

    def test_a_newer_dated_value_is_an_update_not_a_disagreement(self):
        older = self.add("The sales pipeline holds 4 open proposals worth $48,000.", "2026-09-01")
        mine = self.brain.propose(layer="state", topic="pipeline", scope="person:alex",
                                  text="The sales pipeline holds 6 open proposals worth $71,000.",
                                  as_of="2026-10-01")
        self.assertEqual(mine.data["status"], "applied", mine.text)
        waiting = self.brain.propose(layer="state", topic="pipeline", scope="company",
                                     text="The sales pipeline holds 7 open proposals worth "
                                          "$80,000.", as_of="2026-10-05")
        row = {r["id"]: r for r in self.brain.review().data["proposals"]}[
            waiting.data["proposal_id"]]
        self.assertEqual(row["tensions"], [])
        self.assertIn(older, [u["id"] for u in row["updates"]])
        undated = self.brain.propose(layer="state", topic="pipeline", scope="person:alex",
                                     text="The sales pipeline holds 3 open proposals worth "
                                          "$30,000.")
        self.assertEqual(undated.data["status"], "pending", undated.text)  # no date: it waits

    def test_past_its_last_day_a_note_is_flagged_for_a_check(self):
        until = (util.today_date() - dt.timedelta(days=1)).isoformat()
        note_id = self.add("The launch discount is 20% on every retainer.", "2026-09-01",
                           valid_until=until)
        recheck = {r["id"]: r["why"] for r in self.brain.attention().data["recheck"]}
        self.assertEqual(recheck[note_id], f"valid until {until}, now past")

    def test_a_date_that_is_not_one_is_refused(self):
        refused = self.brain.propose(layer="state", topic="pipeline", scope="company",
                                     text="The pipeline is $5,000.", as_of="last Tuesday")
        self.assertTrue(refused.is_error)
        self.assertIn("as_of is a date", refused.text)

    def test_two_values_without_dates_are_not_history(self):
        st = self.brain.state()
        self.assertEqual(review.dated_pairs(st), [])


if __name__ == "__main__":
    unittest.main()
