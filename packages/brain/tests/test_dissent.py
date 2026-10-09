"""Dissent: a challenge to a note waits for the owner; accepted, the note is disputed and keeps
the challenge as its other view, which planning work sees; turned down, it does not come back
on the same evidence. The weekly cross-check finds beliefs something in the Brain says
otherwise about."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import dissent
from brainkit.api import Brain
from tests import fixture

CLAIM = "Web design projects now run ten to twelve weeks from kickoff to launch."
EVIDENCE = "The 2026 project tracker shows eleven weeks on average across nine projects."


class DissentTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def challenge(self, claim=CLAIM, evidence=EVIDENCE):
        return self.brain.challenge("facts-services-002", claim=claim, evidence=evidence,
                                    source="Project tracker, October 2026")

    def test_a_challenge_waits_and_accepting_it_disputes_the_note(self):
        made = self.challenge()
        self.assertEqual(made.data["status"], "pending", made.text)
        row = {r["id"]: r for r in self.brain.review().data["proposals"]}[
            made.data["proposal_id"]]
        self.assertEqual((row["change"], row["challenged"]["id"]),
                         ("challenge", "facts-services-002"))
        self.assertEqual(row["challenge"]["claim"], CLAIM)
        self.assertEqual(self.challenge().data["status"], "duplicate")
        self.assertFalse(self.brain.approve(made.data["proposal_id"]).is_error)
        note = self.brain.state().index.note("facts-services-002")
        self.assertEqual(note.confidence, "disputed")
        self.assertEqual(note.meta["other_view"], CLAIM)
        self.assertEqual(note.meta["other_view_evidence"], EVIDENCE)
        self.assertIn("six to eight weeks", note.body)  # the note itself is unchanged
        record = self.brain.vault.decisions()[-1]
        self.assertEqual((record["action"], record["kind"]), ("approved", "note.challenge"))

    def test_a_challenge_turned_down_needs_new_evidence(self):
        made = self.challenge()
        self.brain.reject(made.data["proposal_id"], "Still six to eight weeks for most")
        again = self.challenge()
        self.assertTrue(again.is_error)
        self.assertEqual(again.data["status"], "refused")
        self.assertIn("Still six to eight weeks for most", again.text)
        fresh = self.challenge(evidence="Three of the last four launches took twelve weeks.")
        self.assertEqual(fresh.data["status"], "pending", fresh.text)

    def test_planning_work_sees_the_other_view_and_a_lookup_sees_a_flag(self):
        made = self.challenge()
        self.brain.approve(made.data["proposal_id"])
        plan = self.brain.context("Plan the timeline and invoices for a new web design project",
                                  record=False, include_kernel=False)
        self.assertIn("facts-services-002", plan.data["note_ids"])
        self.assertIn(f"Contested: {CLAIM[:-1]}.", plan.text)
        lookup = self.brain.context("How long do web design projects run?", record=False,
                                    include_kernel=False)
        self.assertIn("facts-services-002", lookup.data["note_ids"])
        self.assertIn("(disputed)", lookup.text)
        self.assertNotIn("Contested:", lookup.text)

    def test_the_cross_check_finds_a_belief_the_brain_says_otherwise_about(self):
        self.brain.decide([{"id": "facts-services-002", "action": "update",
                            "fields": {"baseline": "true"}}])
        waiting = self.brain.propose(layer="facts", topic="services", scope="company",
                                     text="Web design projects run twelve weeks from kickoff "
                                          "to launch.")
        self.assertEqual(waiting.data["status"], "pending")
        found = {f["id"]: f for f in self.brain.cross_check().data["findings"]}
        finding = found["facts-services-002"]
        self.assertEqual(finding["evidence"]["kind"], "proposal")
        self.assertEqual(finding["found_by"], "words and figures")
        self.assertTrue(finding["baseline"])

    def test_the_cross_checks_model_pairs_are_three_a_week(self):
        self.brain.decide([{"id": "facts-services-002", "action": "update",
                            "fields": {"baseline": "true"}}])
        pairs = dissent.cross_pairs(self.brain)
        self.assertLessEqual(sum(len(b["pairs"]) for b in pairs), dissent.CROSS_MODEL_PAIRS)
        self.assertTrue(pairs and all(p["key"].startswith(dissent.CROSS)
                                      for b in pairs for p in b["pairs"]))
        self.brain.record_checks([{"key": f"{dissent.CROSS}k{i}", "relation": "agrees",
                                   "detail": {}} for i in range(dissent.CROSS_MODEL_PAIRS)])
        self.assertEqual(dissent.cross_pairs(self.brain), [])

    def test_the_external_challenger_tests_a_few_beliefs_never_disputed_ones(self):
        made = self.challenge()
        self.brain.approve(made.data["proposal_id"])
        found = self.brain.challenge_targets(3).data["targets"]
        self.assertTrue(1 <= len(found) <= 3)
        self.assertNotIn("facts-services-002", [t["id"] for t in found])
        self.assertTrue(all(t["claim"] for t in found))

    def test_policies_name_the_cross_check_and_the_challenger(self):
        policy = self.brain.policies().data
        self.assertEqual((policy["cross_check"], policy["challenger"]), (True, False))


if __name__ == "__main__":
    unittest.main()
