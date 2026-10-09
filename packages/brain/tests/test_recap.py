"""The recap since a moment, and conversations served by week."""
import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import governance, util
from brainkit.api import Brain
from tests import fixture

NEW_YORK = dt.timezone(dt.timedelta(hours=-4))  # summer time, as in October


class RecapTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.start = util.now_iso()

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_what_went_in_what_was_decided_and_what_came_in(self):
        self.brain.set_policies({"preset": "personal"}, actor="person:alex")
        went = self.brain.propose(layer="facts", topic="services", scope="company",
                                  text="Motion retainers renew every quarter.",
                                  session_id="sess-abc123", capture_origin="chat")
        self.assertEqual(went.data["status"], "applied", went.text)
        approved = self.brain.propose(layer="facts", topic="services", scope="company",
                                      text="Brand projects start with a two week audit.",
                                      source="workspace:human:Alex (act_1)")
        governance.approve(self.brain, approved.data["proposal_id"])
        self.brain.propose(layer="rules", topic="style", scope="company",
                           text="Always end a client email with the next step.",
                           session_id="sess-abc123", capture_origin="chat")
        self.brain.focus_update("state-focus-website-redesign", "Case studies drafted",
                                {"current": "Writing the case studies"})
        recap = self.brain.recap(self.start).data
        (item,) = recap["went_in"]
        self.assertEqual((item["id"], item["source"], item["capture"], item["live"]),
                         (went.data["id"], "chat", "fact:chat", True))
        self.assertTrue(item["checkpoint"])
        self.assertEqual(recap["decided"], {"approved": 1})
        came = recap["came_in"]
        self.assertEqual(came["by_source"]["chat"], 2)  # one went in, one waits
        self.assertEqual(came["by_source"]["you"], 1)  # approved from the app
        self.assertEqual(came["waiting"], 1)
        self.assertEqual(came["total"], 3)
        (project,) = recap["projects"]
        self.assertEqual((project["id"], project["updates"], project["last"]["summary"]),
                         ("state-focus-website-redesign", 1, "Case studies drafted"))
        later = self.brain.recap("2999-01-01T00:00:00Z").data
        self.assertEqual((later["went_in"], later["came_in"]["total"]), ([], 0))

    def test_an_undone_change_has_no_undo_point_left(self):
        self.brain.set_policies({"preset": "personal"}, actor="person:alex")
        went = self.brain.propose(layer="facts", topic="services", scope="company",
                                  text="Motion retainers renew every quarter.",
                                  session_id="sess-abc123", capture_origin="chat")
        self.brain.undo(went.data["checkpoint"]["id"], actor="person:alex")
        (item,) = self.brain.recap(self.start).data["went_in"]
        self.assertEqual((item["checkpoint"], item["live"]), (None, False))

    def test_conversations_by_week(self):
        # The weeks are the owner's days. The clock and the time zone are pinned to 9 pm in
        # New York, when UTC is already on the next day, so this holds at any hour anywhere.
        with mock.patch.object(util, "local", lambda moment: moment.astimezone(NEW_YORK)), \
                mock.patch.object(util, "now") as clock:
            clock.return_value = dt.datetime(2026, 10, 1, 1, 0, tzinfo=dt.timezone.utc)
            self.brain.context("Headline rules?", session_id="sess-week000")  # Sept 30, 9 pm
            clock.return_value = dt.datetime(2026, 10, 8, 1, 0, tzinfo=dt.timezone.utc)
            self.brain.context("How long do web projects take?", session_id="sess-week001")
            self.brain.context("And motion work?", session_id="sess-week001")
            self.brain.context("Headline rules?", session_id="sess-week002")  # Oct 7, 9 pm
            self.assertEqual(util.today(), "2026-10-07")
            weeks = self.brain.weekly(4).data["weeks"]
        self.assertEqual(len(weeks), 4)
        self.assertEqual((weeks[-1]["start"], weeks[-1]["end"]), ("2026-10-01", "2026-10-07"))
        self.assertEqual((weeks[-1]["conversations"], weeks[-1]["packets"]), (2, 3))
        self.assertEqual((weeks[-2]["conversations"], weeks[-2]["packets"]), (1, 1))
        self.assertEqual(sum(w["conversations"] for w in weeks[:-2]), 0)


if __name__ == "__main__":
    unittest.main()
