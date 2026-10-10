"""The goal ladder (goals plan G1): goals as notes, check-ins and journals, computed checks
with one card per slip, the knowledge agent's starter goals, and the shared plan file."""
from __future__ import annotations

import datetime as dt
import os
import shutil
import unittest
from unittest import mock

from brainkit import ladder, measures
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


class LadderTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def owner(self):
        return self.brain.state().config.owner

    def webinar(self, **extra):
        done = ladder.set_goal(
            self.brain, title="Grow webinar attendance to 150 a session",
            why="Webinars are our best source of qualified conversations.",
            measure={"kind": "enter", "target": 150, "unit": "a session"}, due="2026-12-15",
            actor=self.owner(), **extra)
        self.assertFalse(done.is_error, done.text)
        return done.data["goal"]

    def test_no_goals_means_the_ladder_says_so(self):
        found = ladder.ladder(self.brain)
        self.assertFalse(found["has_goals"])
        self.assertEqual(found["yours"], [])

    def test_your_goal_is_a_manual_note_set_as_one_undo_point(self):
        made = ladder.set_goal(self.brain, title="Grow webinar attendance to 150 a session",
                               why="Best source of conversations.", actor=self.owner())
        self.assertFalse(made.is_error, made.text)
        self.assertTrue(made.data["checkpoint"])
        note = self.brain.state().index.note(made.data["goal"]["id"])
        self.assertEqual((note.kind, note.load, note.meta["level"]), ("goal", "manual", "yours"))
        self.assertEqual(note.meta["goal_status"], "active")
        self.assertIn("Why: Best source of conversations.", note.body)
        found = ladder.ladder(self.brain)
        self.assertTrue(found["has_goals"])
        self.assertEqual(found["check_ins_due"], 1)
        # A goal never reaches a request's brief on its own.
        brief = self.brain.context("How do I grow webinar attendance?", record=False)
        self.assertNotIn("Best source of conversations", brief.text)

    def test_a_goal_is_refused_until_it_can_be_kept(self):
        refused = ladder.set_goal(self.brain, title="Keep the accounts current", level="agent",
                                  cadence="hourly", serves=["no-such-goal"],
                                  actor=self.owner())
        self.assertTrue(refused.is_error)
        for words in ("names the agent", "measure code can compute", "cadence is one of",
                      "no goal 'no-such-goal'"):
            self.assertIn(words, refused.text)
        bad = ladder.set_goal(self.brain, title="x",
                              measure={"kind": "at_most", "signal": "nope"},
                              actor=self.owner())
        self.assertTrue(bad.is_error)
        self.assertIn("no signal 'nope'", bad.text)

    def test_a_check_in_sets_your_status_for_a_cadence_and_then_goes_stale(self):
        goal = self.webinar()
        done = ladder.check_in(self.brain, goal["id"], call="on_track", value="71",
                               line="Two partner promos booked", actor=self.owner())
        self.assertFalse(done.is_error, done.text)
        shown = done.data["goal"]
        self.assertEqual((shown["status"], shown["now"], shown["target"]),
                         ("on_track", 71.0, 150))
        self.assertFalse(shown["check_in_due"])
        entry = self.brain.vault.goal_journal(goal["id"])[-1]
        self.assertEqual((entry["kind"], entry["call"], entry["line"]),
                         ("check_in", "on_track", "Two partner promos booked"))
        note = self.brain.state().index.note(goal["id"])
        checks = self.brain.ledger.goal_checks(goal["id"])
        today = dt.date.today()
        later = ladder.status(note, checks, today + dt.timedelta(days=8))
        self.assertEqual((later["status"], later["stale"]), ("on_track", True))
        gone = ladder.status(note, checks, today + dt.timedelta(days=15))
        self.assertEqual(gone["status"], "not_checked_in")
        refused = ladder.check_in(self.brain, goal["id"], call="great", actor=self.owner())
        self.assertTrue(refused.is_error)

    def test_a_computed_measure_that_disagrees_flags_your_call_without_changing_it(self):
        goal = self.webinar()
        ladder.check_in(self.brain, goal["id"], call="on_track", value=71, actor=self.owner())
        self.brain.ledger.add_goal_check(goal["id"], status="off_track", value=64,
                                         source="code")
        note = self.brain.state().index.note(goal["id"])
        found = ladder.status(note, self.brain.ledger.goal_checks(goal["id"]))
        self.assertEqual(found["status"], "on_track")
        self.assertIn("The measure says 64 against 150", found["flag"])

    def test_an_agent_goal_slip_makes_exactly_one_card(self):
        made = ladder.set_goal(
            self.brain, title="Nothing waits in Catch up over a week", level="agent",
            kept_by="knowledge-agent", cadence="daily",
            measure={"kind": "at_most", "signal": "waiting", "target": 0},
            actor=self.owner())
        self.assertFalse(made.is_error, made.text)
        goal = made.data["goal"]["id"]
        values = iter([0, 1, 1, 6, 6, 0])
        with mock.patch.object(measures.SIGNALS["waiting"], "compute",
                               lambda *_: float(next(values))):
            statuses, raised = [], []
            for _ in range(6):
                result = ladder.run_checks(self.brain, force=True, only=[goal])[0]
                statuses.append(result["status"])
                raised.append(result["card"])
                if len(statuses) == 4:
                    self.assertEqual(len(ladder.cards(self.brain)), 1)
        self.assertEqual(statuses, ["on_track", "needs_attention", "off_track", "off_track",
                                    "off_track", "on_track"])
        self.assertEqual(raised, [False, False, True, False, False, False])
        self.assertEqual(ladder.cards(self.brain), [])

    def test_checks_run_on_their_cadence(self):
        made = ladder.set_goal(
            self.brain, title="No much-used note goes 180 days unchecked", level="agent",
            kept_by="knowledge-agent", measure={"kind": "at_most", "signal": "notes_overdue",
                                                "target": 0}, actor=self.owner())
        goal = made.data["goal"]["id"]
        self.assertEqual(len(ladder.run_checks(self.brain, only=[goal])), 1)
        self.assertEqual(ladder.run_checks(self.brain, only=[goal]), [])
        week = dt.date.today() + dt.timedelta(days=7)
        self.assertEqual(len(ladder.run_checks(self.brain, only=[goal], today=week)), 1)

    def test_the_knowledge_agents_four_goals_turn_on_in_one_tap(self):
        done = ladder.turn_on_starters(self.brain, actor=self.owner())
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(len(done.data["made"]), 4)
        found = ladder.ladder(self.brain)
        self.assertEqual(len(found["agents"]), 4)
        self.assertTrue(all(s["on"] for s in found["starters"]))
        self.assertFalse(found["has_goals"])  # agent goals alone keep goal surfaces hidden
        checked = {r["goal"] for r in ladder.run_checks(self.brain)}
        # Must-hold recall waits for the private eval set: no check, no data.
        self.assertNotIn("goal-rules-reach", checked)
        self.assertIn("goal-notes-checked", checked)
        again = ladder.turn_on_starters(self.brain, actor=self.owner())
        self.assertEqual(again.data["made"], [])

    def test_only_shared_blocks_reach_an_ai(self):
        goal = self.webinar()
        saved = ladder.write_plan(self.brain, goal["id"], [
            {"title": "Wish and outcome", "text": "150 a session, half from target accounts."},
            {"title": "Obstacles and plan", "text": "If sign-ups stall, add a partner promo."},
        ], actor=self.owner())
        self.assertFalse(saved.is_error, saved.text)
        opened = self.brain.note(goal["id"])
        self.assertIn("half from target accounts", opened.text)
        self.assertIn("## Obstacles and plan", opened.text)
        self.assertIn("Shared plan: get_note", ladder.context(self.brain, goal["id"]))
        cleared = ladder.write_plan(self.brain, goal["id"], [], actor=self.owner())
        self.assertFalse(cleared.is_error)
        self.assertNotIn("half from target accounts", self.brain.note(goal["id"]).text)
        self.assertEqual(self.brain.vault.goal_plan(goal["id"]), "")

    def test_changing_a_goal_and_pausing_it(self):
        goal = self.webinar()
        changed = ladder.change_goal(self.brain, goal["id"],
                                     {"title": "Grow webinar attendance to 120 a session",
                                      "cadence": "monthly"}, actor=self.owner())
        self.assertFalse(changed.is_error, changed.text)
        self.assertEqual((changed.data["goal"]["title"], changed.data["goal"]["cadence"]),
                         ("Grow webinar attendance to 120 a session", "monthly"))
        paused = ladder.change_goal(self.brain, goal["id"], {"status": "paused"},
                                    actor=self.owner())
        self.assertEqual(paused.data["goal"]["status"], "paused")
        refused = ladder.check_in(self.brain, goal["id"], call="on_track", actor=self.owner())
        self.assertTrue(refused.is_error)
        bad = ladder.change_goal(self.brain, goal["id"], {"cadence": "hourly"},
                                 actor=self.owner())
        self.assertTrue(bad.is_error)
        not_a_goal = self.brain.update("company-numbers", {"cadence": "weekly"})
        self.assertTrue(not_a_goal.is_error)
        self.assertIn("only a goal has cadence", not_a_goal.text)

    def test_a_decision_joins_the_journal_and_changes_nothing_else(self):
        goal = self.webinar()
        done = ladder.journal_note(self.brain, goal["id"], "Moved the third session to "
                                   "December 3.", actor=self.owner())
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(self.brain.vault.goal_journal(goal["id"])[-1]["kind"], "decision")
        self.assertEqual(ladder.view(self.brain, self.brain.state().index.note(goal["id"]))
                         ["status"], "not_checked_in")

    def test_the_signal_library_shows_values_now(self):
        found = {s["name"]: s for s in ladder.signals(self.brain)}
        self.assertTrue(found["notes_overdue"]["available"])
        self.assertIsInstance(found["notes_overdue"]["now"], float)
        self.assertFalse(found["must_hold_recall"]["available"])
        self.assertIn("eval set", found["must_hold_recall"]["waits_for"])


if __name__ == "__main__":
    unittest.main()
