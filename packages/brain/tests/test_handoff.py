"""Tasks and handoffs (goals plan 5, G2): the Tasks sheet, `hand_off`'s four moves and its
rules, the card, pending handoffs in a first brief, and the T-41 story end to end with a
stand-in agent: a goal slips, its agent opens a task, saves, hands it to Claude Code, and a
fresh session picks up from the card and redoes nothing."""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from unittest import mock

from brainkit import handoff, ladder, measures, state
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


class HandoffTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.owner = self.brain.state().config.owner
        self.out = tempfile.mkdtemp()

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)

    def output(self, name="draft.md"):
        path = os.path.join(self.out, name)
        open(path, "w", encoding="utf-8").write("done")
        self.brain.record_output(path, title="the draft")
        return path

    def test_you_open_a_task_and_pass_it_on_with_a_card(self):
        made = self.brain.hand_off(new_task={"title": "Build the follow-up email",
                                             "project": "q4-webinar-series"})
        self.assertFalse(made.is_error, made.text)
        task = made.data["task"]
        self.assertEqual((task["id"], task["owner"], task["status"]), ("T-1", "you", "open"))
        refused = self.brain.hand_off(task="T-1", to="Claude Code")
        self.assertTrue(refused.is_error)
        self.assertIn("done_when and next_step", refused.text)
        passed = self.brain.hand_off(task="T-1", to="Claude Code, repo site",
                                     done_when="The email is drafted and waits for review",
                                     next_step="Draft it from the webinar recap",
                                     done_so_far="Picked the recap as the source; "
                                                 "token=abcdef123456 used for the CRM")
        self.assertFalse(passed.is_error, passed.text)
        self.assertEqual(passed.data["task_status"], "handed_off")
        card = passed.data["card"]
        self.assertIn("Objective (Q4 webinar series)", card)
        self.assertIn("Next step: Draft it from the webinar recap", card)
        self.assertNotIn("abcdef123456", card)
        self.assertLessEqual(len(card) // 4, handoff.CARD_TOKENS)
        brief = self.brain.context("Start my day").text
        self.assertIn("## Waiting to be picked up", brief)
        self.assertIn('T-1 Build the follow-up email (Handed off, for Claude Code, repo site)',
                      brief)

    def test_only_hand_off_moves_owner_and_status(self):
        self.brain.hand_off(new_task={"title": "Tidy the pricing skill"})
        done = self.brain.update_state([{"sheet": "tasks", "row": "T-1", "column": "Status",
                                         "value": "done"}])
        self.assertIn("changes only through hand_off", done.text)
        self.assertEqual(handoff.task(self.brain, "T-1")["status"], "open")

    def test_finishing_needs_evidence_and_blocking_needs_a_reason(self):
        self.brain.hand_off(new_task={"title": "Write the recap",
                                      "project": "q4-webinar-series"})
        self.assertIn("needs a reason", self.brain.hand_off(task="T-1",
                                                             status="blocked").text)
        self.assertIn("Done needs evidence", self.brain.hand_off(
            task="T-1", status="done", evidence=["nowhere.md"]).text)
        path = self.output()
        finished = self.brain.hand_off(task="T-1", status="done", evidence=[path])
        self.assertFalse(finished.is_error, finished.text)
        self.assertEqual(finished.data["task_status"], "done")
        updates = self.brain.state().index.focuses["q4-webinar-series"].updates
        self.assertIn("T-1 done: Write the recap", updates[-1].summary)

    def test_a_save_that_says_nothing_new_changes_nothing(self):
        self.brain.hand_off(new_task={"title": "Check the numbers"})
        self.brain.hand_off(task="T-1", next_step="Open the sheet")
        again = self.brain.hand_off(task="T-1", next_step="Open the sheet")
        self.assertEqual(again.data["status"], "unchanged")

    def test_agents_never_open_tasks_for_your_goals(self):
        goal = ladder.set_goal(self.brain, title="Grow webinar attendance",
                               actor=self.owner).data["goal"]["id"]
        refused = self.brain.hand_off(new_task={"title": "Promote", "goal": goal},
                                      caller="agent:knowledge-agent")
        self.assertTrue(refused.is_error)
        self.assertIn("suggest a next step", refused.text)
        noted = self.brain.hand_off(goal=goal, goal_note="Found three promo slots")
        self.assertFalse(noted.is_error, noted.text)
        self.assertEqual(self.brain.vault.goal_journal(goal)[-1]["kind"], "progress")

    def test_the_first_claim_wins(self):
        self.brain.hand_off(new_task={"title": "Fix the figure"})
        self.brain.hand_off(task="T-1", to="agent:accounts", done_when="Fixed",
                            next_step="Fix it")
        mine = self.brain.hand_off(task="T-1", claim=True, caller="agent:accounts")
        self.assertFalse(mine.is_error, mine.text)
        other = self.brain.hand_off(task="T-1", claim=True, caller="agent:writer")
        self.assertTrue(other.is_error)
        self.assertIn("already has T-1", other.text)

    def test_the_t41_story(self):
        """A goal slips; its agent opens a task, works it, saves and hands it to Claude
        Code; a fresh session picks up from the card, redoes nothing and finishes."""
        ladder.turn_on_starters(self.brain, actor=self.owner)
        values = iter([0.0, 6.0])
        with mock.patch.object(measures.SIGNALS["notes_overdue"], "compute",
                               lambda *_: next(values)):
            ladder.run_checks(self.brain, force=True, only=["goal-notes-checked"])
            slipped = ladder.run_checks(self.brain, force=True, only=["goal-notes-checked"])
        task_id = slipped[0]["task"]
        self.assertEqual(task_id, "T-1")
        item = handoff.task(self.brain, task_id)
        self.assertEqual((item["owner"], item["status"], item["goal"]),
                         ("agent:knowledge-agent", "working", "goal-notes-checked"))
        saved = self.brain.hand_off(task=task_id, caller="agent:knowledge-agent",
                                    done_so_far="Verified 6 notes; 4 need updates",
                                    decisions="The pricing note stays as it is",
                                    goal_note="Verified 6 notes; 4 need updates")
        self.assertFalse(saved.is_error, saved.text)
        passed = self.brain.hand_off(task=task_id, caller="agent:knowledge-agent",
                                     to="Claude Code",
                                     done_when="The 4 notes are updated and proposed",
                                     next_step="Update the 4 notes named in the log",
                                     load="customers-pains, q4-webinar-series")
        self.assertEqual(passed.data["task_status"], "handed_off")
        # A fresh session, from the card alone.
        fresh = self.brain.context("pick up T-1", context=task_id).text
        self.assertIn("## Your task", fresh)
        self.assertIn("Done so far: Verified 6 notes; 4 need updates", fresh)
        self.assertIn("Decisions made: The pricing note stays as it is", fresh)
        self.assertIn("Next step: Update the 4 notes named in the log", fresh)
        claimed = self.brain.hand_off(task=task_id, claim=True, tool="Claude Code")
        self.assertEqual(claimed.data["task_status"], "working")
        finished = self.brain.hand_off(task=task_id, status="done", tool="Claude Code",
                                       evidence=[self.output("notes.md")])
        self.assertEqual(finished.data["task_status"], "done")
        journal = [e["text"] for e in self.brain.vault.goal_journal("goal-notes-checked")]
        self.assertTrue(any("Verified 6 notes" in t for t in journal))
        self.assertTrue(any("T-1 done" in t for t in journal))
        log = [e.get("column") for e in handoff.task(self.brain, task_id)["log"]]
        self.assertIn("Owner", log)
        self.assertIn("Card", log)

    def test_the_tasks_sheet_is_built_in(self):
        self.brain.hand_off(new_task={"title": "Anything"})
        sheet = state.sheet(self.brain, "tasks")
        self.assertTrue(sheet.builtin)
        self.assertEqual([c.name for c in sheet.columns if c.computed],
                         ["Days open", "Since update"])
        row = state.rows(self.brain, "tasks")[0]
        self.assertEqual(row.computed["Days open"], 0)


if __name__ == "__main__":
    unittest.main()
