"""Every day the Brain counts is the owner's day, never UTC's.

The Brain stamps moments in UTC (`util.now_iso()`) and counts days on the owner's clock
(`util.today_date()`). Cutting a stamp to its first ten characters reads it as UTC's day: on a New
York evening that is already tomorrow, so a task made that evening was -1 days open and a weekly
check came due a day late. These pin a New York evening, so a run on UTC catches it at any hour.
"""
import datetime as dt
import os
import shutil
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import ladder, state, util  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402
from brainkit.api import Brain  # noqa: E402

REPO = os.path.dirname(os.path.dirname(ROOT))
EVENING = dt.datetime(2026, 10, 14, 0, 30, tzinfo=dt.timezone.utc)  # 20:30 in New York
NEW_YORK = dt.timezone(dt.timedelta(hours=-4))
TODAY = dt.date(2026, 10, 13)


class EveningTests(unittest.TestCase):
    def setUp(self):
        for patch in (mock.patch.object(util, "now", return_value=EVENING),
                      mock.patch.object(util, "local",
                                        side_effect=lambda moment: moment.astimezone(NEW_YORK))):
            patch.start()
            self.addCleanup(patch.stop)
        self.vault = se.copy_vault(os.path.join(REPO, "brains", "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_stamp_is_read_on_the_owners_clock(self):
        self.assertEqual(util.today_date(), TODAY)
        self.assertEqual(util.day_of(util.now_iso()), TODAY)
        self.assertEqual(util.day_of("2026-11-02"), dt.date(2026, 11, 2))  # a date as written
        self.assertIsNone(util.day_of(""))
        self.assertIsNone(util.day_of("next spring"))
        self.assertEqual(util.day_text("2026-10-14T00:30:00Z"), "2026-10-13")
        self.assertEqual(util.day_text(""), "")

    def test_a_task_made_this_evening_is_zero_days_open(self):
        self.brain.hand_off(new_task={"title": "Draft the webinar invite"})
        row = state.rows(self.brain, "tasks")[0]
        self.assertEqual(row.computed["Days open"], 0)

    def test_a_check_in_this_evening_counts_from_today(self):
        owner = self.brain.state().config.owner
        made = ladder.set_goal(self.brain, title="Grow webinar attendance to 150 a session",
                               measure={"kind": "enter", "target": 150}, actor=owner)
        goal = made.data["goal"]["id"]
        done = ladder.check_in(self.brain, goal, call="on_track", value="71", actor=owner)
        self.assertFalse(done.is_error, done.text)
        note = self.brain.state().index.note(goal)
        checks = self.brain.ledger.goal_checks(goal)
        self.assertFalse(ladder.status(note, checks, TODAY)["stale"])
        self.assertFalse(ladder.status(note, checks, TODAY + dt.timedelta(days=7))["stale"])
        self.assertTrue(ladder.status(note, checks, TODAY + dt.timedelta(days=8))["stale"])

    def test_a_weekly_check_run_this_evening_comes_due_a_week_later(self):
        owner = self.brain.state().config.owner
        made = ladder.set_goal(
            self.brain, title="No much-used note goes 180 days unchecked", level="agent",
            kept_by="knowledge-agent", measure={"kind": "at_most", "signal": "notes_overdue",
                                                "target": 0}, actor=owner)
        goal = made.data["goal"]["id"]
        self.assertEqual(len(ladder.run_checks(self.brain, only=[goal])), 1)
        self.assertEqual(ladder.run_checks(self.brain, only=[goal]), [])
        week = TODAY + dt.timedelta(days=7)
        self.assertEqual(len(ladder.run_checks(self.brain, only=[goal], today=week)), 1)


if __name__ == "__main__":
    unittest.main()
