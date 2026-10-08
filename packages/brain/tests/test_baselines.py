"""Baselines: the notes a change must not quietly overturn (baseline.py), the guard that holds
what would go in on its own when it may disagree with a note, and the reason a revision of a
baseline needs."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import baseline, review
from brainkit.api import Brain
from tests import fixture

PAIRS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evals", "tension_pairs.json")


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def why(self, note_id, used=0):
        st = self.brain.state()
        return baseline.why(st.index.note(note_id), st.config, used)

    def test_what_makes_a_note_a_baseline(self):
        self.assertEqual(self.why("rules-style-001"), "it goes into every conversation")
        self.assertEqual(self.why("rules-style-002"), "it is a rule")
        self.assertIsNone(self.why("facts-services-002"))
        self.assertEqual(self.why("facts-services-002", used=12),
                         "AIs used it in 12 conversations this month")
        self.brain.decide([{"id": "facts-services-002", "action": "update",
                            "fields": {"baseline": "true"}}])
        self.assertEqual(self.why("facts-services-002"), "you marked it a baseline")
        self.brain.decide([{"id": "facts-services-002", "action": "update",
                            "fields": {"baseline": ""}}])
        self.assertIsNone(self.why("facts-services-002"))
        self.brain.verify("facts-services-002", confidence="confirmed")
        self.assertEqual(self.why("facts-services-002"), "you confirmed it")

    def test_a_change_that_would_go_in_on_its_own_waits_when_it_may_disagree(self):
        held = self.brain.propose(layer="facts", topic="services", scope="person:alex",
                                  text="Web design projects run twelve weeks from kickoff to "
                                       "launch.")
        self.assertEqual(held.data["status"], "pending", held.text)
        self.assertEqual(held.data["held"]["id"], "facts-services-002")
        self.assertIn("would have applied at once, but it waits", held.text)
        row = {r["id"]: r for r in self.brain.review().data["proposals"]}[
            held.data["proposal_id"]]
        self.assertEqual(row["held"]["id"], "facts-services-002")
        self.assertIn("facts-services-002", [t["id"] for t in row["tensions"]])
        calm = self.brain.propose(layer="facts", topic="services", scope="person:alex",
                                  text="Alex books client calls in the mornings.")
        self.assertEqual(calm.data["status"], "applied", calm.text)

    def test_a_change_to_a_baseline_in_your_own_scope_waits_for_a_reason(self):
        first = self.brain.propose(layer="rules", topic="style", scope="person:alex",
                                   text="I want plain-text drafts, never Word files.")
        self.assertEqual(first.data["status"], "applied", first.text)
        note_id = first.data["id"]
        self.assertEqual(self.why(note_id), "it is a rule")
        change = self.brain.propose(target_id=note_id, text="I want Markdown drafts.")
        self.assertEqual(change.data["status"], "pending", change.text)
        self.assertIn("changes a baseline", change.data["held"]["why"])
        refused = self.brain.approve(change.data["proposal_id"], reason="newer")
        self.assertTrue(refused.is_error)
        self.assertEqual(refused.data["status"], "needs_reason")
        kept = self.brain.approve(change.data["proposal_id"],
                                  reason="Markdown pastes cleanly into every tool")
        self.assertFalse(kept.is_error, kept.text)
        (record,) = [r for r in self.brain.vault.decisions() if r.get("baseline_revised")]
        self.assertEqual(record["baseline_revised"]["note"], note_id)
        self.assertEqual(record["baseline_revised"]["reason"],
                         "Markdown pastes cleanly into every tool")

    def test_a_review_shows_the_baseline_a_proposal_changes_with_its_impact(self):
        made = self.brain.propose(target_id="rules-style-002",
                                  text="Headlines use sentence case and stay under twelve words.")
        row = {r["id"]: r for r in self.brain.review().data["proposals"]}[
            made.data["proposal_id"]]
        found = row["baseline"]
        self.assertEqual((found["id"], found["change"], found["why"]),
                         ("rules-style-002", "revise", "it is a rule"))
        self.assertEqual(found["impact"], {"conversations": 0, "recent": [], "domains": []})
        self.assertEqual(found["min_words"], baseline.REASON_WORDS)


class NothingUnseenTests(unittest.TestCase):
    def test_nothing_that_applies_at_once_contradicts_a_baseline_unseen(self):
        """Every contradiction in the labeled set, its first half a rule: the second, proposed
        in the owner's own scope, either waits (checks 1 and 2) or, having gone in, is among
        what a model reads next (check 3), the rule among its pairs."""
        with open(PAIRS, encoding="utf-8") as handle:
            pairs = [p for p in json.load(handle)["pairs"] if p["relation"] == "contradicts"]
        held = read_later = 0
        for pair in pairs:
            with self.subTest(pair=pair["b"]):
                vault = fixture.build()
                brain = Brain(vault, embeddings=False)
                try:
                    made = brain.propose(layer="rules", topic="delivery", scope="company",
                                         text=pair["a"], note_kind="rule")
                    self.assertFalse(brain.approve(made.data["proposal_id"]).is_error)
                    rule_id = made.data["id"]
                    res = brain.propose(layer="rules", topic="delivery", scope="person:alex",
                                        text=pair["b"])
                    if res.data["status"] == "pending":
                        self.assertTrue(res.data.get("held"), res.text)
                        held += 1
                        continue
                    self.assertEqual(res.data["status"], "applied", res.text)
                    batches = review.pending_checks(brain, limit=50)
                    seen = {(b["subject"], p["id"]) for b in batches for p in b["pairs"]}
                    self.assertIn((f"note:{res.data['id']}", rule_id), seen)
                    read_later += 1
                finally:
                    brain.close()
                    fixture.remove(vault)
        self.assertEqual(held + read_later, len(pairs))
        self.assertGreaterEqual(held, len(pairs) // 2)
        print(f"\n{held} of {len(pairs)} held by checks 1 and 2, {read_later} read by a model "
              "after going in")


if __name__ == "__main__":
    unittest.main()
