"""G4, the goals plan's evals (its section 11), as seeded tests on a demo Brain: the
disagreement flag exactly when a measure and your call disagree, goals optional, the project's
objective at the top of every task brief, measures against a reference computation, check-in
noise, the handoff card's size, and no secret in a card, a goal note or a plan file. The
evals that need a model, a person or real use (the coach's turns and time, check-in time,
board restraint, objectives judged blind, agents saving at the right moments) wait for them."""
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import unittest

from brainkit import handoff, ladder, measures, proof, util
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")
SECRET = "sk-ant-api03-" + "Z" * 40


class G4Test(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.owner = self.brain.state().config.owner

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_the_disagreement_flag_shows_exactly_when_measure_and_call_disagree(self):
        made = ladder.set_goal(self.brain, title="Nothing waits a week",
                               measure={"kind": "at_most", "signal": "waiting", "target": 0,
                                        "unit": "items"}, actor=self.owner)
        note = self.brain.state().index.note(made.data["goal"]["id"])
        today = util.today_date()
        stamp = (today - dt.timedelta(days=1)).isoformat() + "T09:00:00Z"
        cases = 0
        for call in ladder.CALLS:
            for computed in ("on_track", "needs_attention", "off_track"):
                checks = [{"source": "you", "status": call, "at": stamp, "value": None},
                          {"source": "code", "status": computed, "at": stamp, "value": 2.0}]
                shown = ladder.status(note, checks, today)
                disagree = (computed == "on_track") != (call == "on_track")
                self.assertEqual(bool(shown.get("flag")), disagree, (call, computed))
                self.assertEqual(shown["status"], call)  # your call stands
                cases += 1
        self.assertEqual(cases, 9)

    def test_goals_are_optional_and_never_reach_a_brief_unasked(self):
        found = ladder.ladder(self.brain)
        self.assertFalse(found["has_goals"])
        self.assertEqual(ladder.cards(self.brain), [])
        ladder.set_goal(self.brain, title="Grow webinar attendance to 150 a session",
                        why="Webinars are our best source of conversations.",
                        actor=self.owner)
        st = self.brain.state()
        for request in proof.REQUESTS:
            brief = self.brain.context(request, record=False)
            kinds = {st.index.note(i).kind for i in brief.data.get("note_ids") or []
                     if st.index.note(i) is not None}
            self.assertNotIn("goal", kinds, request)
            self.assertNotIn("best source of conversations", brief.text)

    def test_every_task_brief_in_a_project_opens_with_its_objective_in_60_tokens(self):
        # Near the 60-word limit for an objective, so the brief has to cut it.
        long = ("Forty qualified conversations at the spring fair, each logged for sales with "
                "the plant, the role, the shift pattern, the current training gaps, the budget "
                "owner, the decision date and the next step agreed at the stand, so that every "
                "lead reaches Sam within two days of the fair with what was promised and "
                "nothing has to be asked again.")
        made = self.brain.focus_create("Spring Fair", "Our stand at the spring trade fair.",
                                       objective=long)
        self.assertFalse(made.is_error, made.text)
        for request in ("Plan the spring fair stand", "Draft the spring fair invitation",
                        "List what the spring fair booth needs"):
            brief = self.brain.context(request, focus=made.data["id"], record=False)
            task = brief.text.split("## Task", 1)[1].strip().splitlines()[0]
            self.assertTrue(task.startswith("Objective of the project Spring Fair: "), task)
            aim = task.split(": ", 1)[1]
            self.assertLessEqual(util.tokens(aim), 62, aim)

    def test_measures_match_a_reference_computation(self):
        owner = self.owner
        for n in range(3):
            self.brain.propose(area="marketing", topic=f"waits-{n}", text=f"Waiting {n}.",
                               note_kind="fact", principal=owner, force_pending=True)
        self.brain.correction("That's wrong.")
        self.brain.hand_off(new_task={"title": "Book two partner promos", "milestone": True})
        self.brain.hand_off(new_task={"title": "Draft the recap"})
        st = self.brain.state()
        reference = {
            "waiting": float(sum(1 for p in st.snapshot.proposals.values()
                                 if (util.today_date() - util.parse_date(p.created[:10]))
                                 .days > 7)),
            "corrections": float(len(self.brain.ledger.corrections(
                status=None, since=(util.today_date() - dt.timedelta(days=7)).isoformat()))),
            "milestones": float(sum(1 for t in handoff.tasks(self.brain, status="done")
                                    if t["milestone"])),
            "sent_back": 0.0,
        }
        for signal, expected in reference.items():
            found = measures.value(self.brain, {"kind": "at_most", "signal": signal})
            self.assertEqual(found, expected, signal)
        self.assertEqual(reference["corrections"], 1.0)

    def test_a_steady_status_says_nothing_and_a_slip_makes_one_card(self):
        made = ladder.set_goal(self.brain, title="Nothing waits", level="agent",
                               kept_by="knowledge-agent",
                               measure={"kind": "at_most", "signal": "corrections",
                                        "target": 0, "unit": "corrections"},
                               actor=self.owner)
        goal = made.data["goal"]["id"]
        for _ in range(3):
            self.brain.correction("That's wrong.")
        runs = [ladder.run_checks(self.brain, force=True, only=[goal]) for _ in range(4)]
        cards = [sum(1 for c in run if c["card"]) for run in runs]
        self.assertEqual(sum(cards), 1, [[(c["status"], c["card"]) for c in r] for r in runs])
        self.assertEqual(len(ladder.cards(self.brain)), 1)

    def test_the_handoff_card_stays_near_250_tokens(self):
        made = self.brain.hand_off(new_task={"title": "Refresh the pricing skill"})
        task = made.data["task"]["id"]
        done = self.brain.hand_off(
            task=task, to="Claude Code",
            done_when="The pricing skill quotes this year's seat price and passes its replay.",
            next_step="Open the skill, update the price table, run the replay, save.",
            done_so_far="Found the old price in two places; the skill's test fails on it. "
                        * 3,
            decisions="Keep the per-seat model; quote prices without tax",
            open_questions="Is the volume discount still 10%?")
        self.assertFalse(done.is_error, done.text)
        card = handoff.render(self.brain, handoff.task(self.brain, task))
        self.assertLessEqual(util.tokens(card), 260, card)

    def test_no_secret_reaches_a_card_a_goal_note_or_a_plan_file(self):
        made = ladder.set_goal(self.brain, title="Grow the list",
                               why=f"Because the key {SECRET} unlocks it", actor=self.owner)
        goal = made.data["goal"]["id"]
        ladder.check_in(self.brain, goal, call="on_track", line=f"token: {SECRET}",
                        actor=self.owner)
        ladder.write_plan(self.brain, goal, [{"title": "Notes", "text": f"use {SECRET}"}],
                          actor=self.owner)
        task = self.brain.hand_off(new_task={"title": "Use the key"}).data["task"]["id"]
        self.brain.hand_off(task=task, to="Claude Code", done_when="Done",
                            next_step="Go", done_so_far=f"The key is {SECRET}")
        texts = [self.brain.state().index.note(goal).body,
                 self.brain.vault.goal_plan(goal),
                 handoff.render(self.brain, handoff.task(self.brain, task)),
                 str(self.brain.vault.goal_journal(goal))]
        for text in texts:
            self.assertNotIn(SECRET, text)
            self.assertIsNone(re.search(r"sk-ant-api03-Z{8,}", text))


if __name__ == "__main__":
    unittest.main()
