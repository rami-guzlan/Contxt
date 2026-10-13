"""The brain's goals: the owner's answers kept as one private note, set and changed as one
undo point, read back with this brain's examples, and kept out of every request's packet."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import goals
from brainkit.api import Brain
from tests import fixture

ANSWERS = {
    "purpose": "Help me run the studio without dropping client details.",
    "work": "Brand and web design for small companies.",
    "in_motion": "Website redesign\n- Studio podcast",
    "leave_out": "Anything about my family.",
}


class GoalsTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_answers_become_one_private_note_read_back_in_full(self):
        empty = self.brain.goals().data
        self.assertFalse(empty["exists"])
        self.assertEqual([q["id"] for q in empty["questions"]],
                         ["purpose", "work", "slips", "how", "never", "leave_out", "in_motion",
                          "working"])
        self.assertTrue(all(q["why"] and q["example"] for q in empty["questions"]))
        saved = self.brain.set_goals(ANSWERS, actor="person:alex")
        self.assertFalse(saved.is_error, saved.text)
        note = self.brain.state().index.note(goals.GOALS_ID)
        self.assertEqual((note.scope, note.load, note.classification),
                         ("person:alex", "manual", "confidential"))
        self.assertTrue(note.body.startswith("# What this Brain is for"))
        self.assertIn("goals interview", note.meta["evidence"])
        found = self.brain.goals().data
        self.assertEqual(found["answers"], ANSWERS)
        self.assertEqual(found["purpose"], ANSWERS["purpose"])
        self.assertEqual(found["projects"], ["Website redesign", "Studio podcast"])
        self.assertFalse(self.brain.state().snapshot.proposals)  # nothing waits

    def test_the_goals_steer_what_comes_in_not_what_every_request_gets(self):
        self.brain.set_goals(ANSWERS, actor="person:alex")
        kernel = self.brain.kernel().text
        self.assertNotIn(ANSWERS["purpose"], kernel)
        self.assertNotIn(goals.GOALS_ID, kernel)
        packet = self.brain.preview("What should the studio's assistant help me run?").data
        self.assertNotIn(goals.GOALS_ID, [n["id"] for n in packet["notes"]])
        found = self.brain.search("run the studio without dropping client details").data
        self.assertIn(goals.GOALS_ID, [h["id"] for h in found["hits"]])

    def test_a_goal_never_rides_into_a_brief_on_another_note(self):
        """Goals are confidential and load only when asked for: not when a selected note names
        them, and not as a newer value of a figure the brief carries."""
        from brainkit.vault import Vault
        self.brain.set_goals(ANSWERS, actor="person:alex")
        self.brain.close()
        v = Vault(self.vault)
        levels = fixture.BRAIN["structure"]["scope_levels"]
        kinds = fixture.BRAIN["structure"]["partition_kinds"]
        for meta, body in [
            fixture.note("facts-revenue-now", "facts", "services", "company",
                         "Monthly studio revenue is 32,000 dollars. Where we want it to go is "
                         f"in `{goals.GOALS_ID}`; it contradicts nothing here.",
                         as_of="2026-08-01"),
            fixture.note("facts-revenue-goal", "facts", "services", "person:alex",
                         "Monthly studio revenue is 50,000 dollars by June.",
                         load="manual", as_of="2026-10-01", classification="confidential")]:
            v.write_note(v.note_path(meta, levels, kinds), dict(meta), body)
        self.brain = Brain(self.vault, embeddings=False)
        res = self.brain.context("What is our monthly studio revenue?",
                                 principal="person:alex")
        data = res.data
        carried = (set(data.get("note_ids") or []) | set(data.get("related_ids") or [])
                   | set(data.get("pointer_ids") or []))
        self.assertIn("facts-revenue-now", carried)
        self.assertNotIn("facts-revenue-goal", carried)
        self.assertNotIn(goals.GOALS_ID, carried)
        self.assertNotIn("50,000", res.text)
        self.assertNotIn(ANSWERS["purpose"], res.text)

    def test_changing_them_is_one_undo_point(self):
        self.brain.set_goals(ANSWERS, actor="person:alex")
        changed = self.brain.set_goals(dict(ANSWERS, purpose="Help me grow the studio."),
                                       actor="person:alex")
        self.assertFalse(changed.is_error, changed.text)
        point = changed.data["checkpoint"]
        self.assertEqual(point["label"], "Your goals for this Brain")
        self.brain.undo(point["id"], actor="person:alex")
        self.assertEqual(self.brain.goals().data["purpose"], ANSWERS["purpose"])
        same = self.brain.set_goals(ANSWERS, actor="person:alex")
        self.assertEqual(same.data["status"], "unchanged")

    def test_examples_follow_the_kind_of_brain(self):
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["starter"] = "programmer"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        first = self.brain.goals().data["questions"][0]
        self.assertEqual(first["example"],
                         goals.QUESTIONS[0]["examples"]["programmer"])

    def test_refusals(self):
        self.assertTrue(self.brain.set_goals({"work": "Design."},
                                             actor="person:alex").is_error)
        self.assertTrue(self.brain.set_goals({"purpose": "x", "mood": "y"},
                                             actor="person:alex").is_error)
        self.assertTrue(self.brain.set_goals({"purpose": "x" * 601},
                                             actor="person:alex").is_error)
        self.assertTrue(self.brain.set_goals(ANSWERS, actor="person:sam").is_error)

    def test_parse_reads_back_what_compose_wrote(self):
        self.assertEqual(goals.parse(goals.compose(ANSWERS)), ANSWERS)


if __name__ == "__main__":
    unittest.main()
