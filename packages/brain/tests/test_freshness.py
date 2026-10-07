"""Freshness and confidence: context that ages is marked, ranked lower, and re-verified by a person.

Spec section 05: time-sensitive context gets a review interval; expiry does not delete it, it
marks it stale and lowers its retrieval priority until someone verifies it again. Confidence
is plain language: confirmed, inferred, disputed or unknown.
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit.api import Brain
from brainkit.model import Note
from brainkit.vault import Vault
from tests import fixture

TODAY = dt.date.today()
LONG_AGO = (TODAY - dt.timedelta(days=200)).isoformat()


def note(meta, body="text"):
    return Note(id=meta.get("id", "n"), area="facts", topic="services", scope="company",
                status="approved", load="on-demand", body=body, path="x.md", meta=meta)


class StalenessTests(unittest.TestCase):
    def test_no_dates_means_not_stale(self):
        self.assertIsNone(note({"added": "2020-01-01"}).stale_reason(TODAY))

    def test_a_review_interval_runs_from_the_last_verification(self):
        old = note({"verified": LONG_AGO, "review_days": "90"})
        self.assertIn(f"not verified since {LONG_AGO}", old.stale_reason(TODAY))
        recent = note({"verified": (TODAY - dt.timedelta(days=10)).isoformat(),
                       "review_days": 90})
        self.assertIsNone(recent.stale_reason(TODAY))
        # Without a verification date the interval runs from when the note was added.
        self.assertIsNotNone(note({"added": LONG_AGO, "review_days": 30}).stale_reason(TODAY))

    def test_a_review_date_in_the_past_makes_it_stale(self):
        due = note({"review_by": (TODAY - dt.timedelta(days=1)).isoformat()})
        self.assertIn("review was due", due.stale_reason(TODAY))

    def test_marked_stale_until_verified(self):
        self.assertEqual(note({"stale": True}).stale_reason(TODAY), "marked stale")
        self.assertEqual(note({"stale": "true"}).stale_reason(TODAY), "marked stale")

    def test_the_older_review_cycle_count_is_not_read_as_days(self):
        # brain-kit v1 counted `review_every` in review cycles; it never marks a note stale.
        self.assertIsNone(note({"added": LONG_AGO, "review_every": "4"}).stale_reason(TODAY))
        self.assertEqual(note({"affirmed": "2026-05-01", "added": "2026-01-01"}).verified,
                         "2026-05-01")

    def test_confidence_is_plain_language_or_nothing(self):
        self.assertEqual(note({"confidence": "Disputed"}).confidence, "disputed")
        self.assertIsNone(note({"confidence": "very sure"}).confidence)
        self.assertEqual(note({"verified": "2026-09-01"}).verified, "2026-09-01")
        self.assertEqual(note({"added": "2026-08-01"}).verified, "2026-08-01")


class FreshnessInPacketsTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        v = Vault(self.vault)
        levels = fixture.BRAIN["structure"]["scope_levels"]
        kinds = fixture.BRAIN["structure"]["partition_kinds"]
        for meta, body in (
            (dict(id="facts-identity-weeks", layer="facts", topic="services", scope="company",
                  status="approved", load="on-demand", added="2025-01-01", verified=LONG_AGO,
                  review_days="60"),
             "Brand identity projects take four weeks from kickoff to handoff."),
            (dict(id="facts-identity-rounds", layer="facts", topic="services", scope="company",
                  status="approved", load="on-demand", added="2025-01-01",
                  verified=TODAY.isoformat(), review_days="60"),
             "Brand identity projects include two rounds of revisions after kickoff."),
            (dict(id="facts-retainer", layer="facts", topic="services", scope="company",
                  status="approved", load="on-demand", added="2025-01-01",
                  confidence="disputed"),
             "The monthly retainer covers eight hours of design support."),
        ):
            v.write_note(v.note_path(meta, levels, kinds), meta, body)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_a_stale_note_is_still_delivered_but_flagged(self):
        result = self.brain.context("How many weeks do brand identity projects take?",
                                    record=False)
        self.assertIn("facts-identity-weeks", result.data["note_ids"])
        self.assertIn("stale: not verified since", result.text)
        self.assertIn("verify before relying on it", result.text)

    def test_a_stale_note_ranks_below_an_equally_relevant_fresh_one(self):
        result = self.brain.context("brand identity projects kickoff", record=False,
                                    explain=True)
        scores = {row["id"]: row for row in result.data["trace"]["note_scores"]}
        stale, fresh = scores["facts-identity-weeks"], scores["facts-identity-rounds"]
        self.assertTrue(stale["stale"])
        self.assertLess(stale["adj"] / stale["rel"], fresh["adj"] / fresh["rel"])

    def test_disputed_notes_say_so(self):
        result = self.brain.context("What does the monthly retainer cover?", record=False)
        self.assertIn("facts-retainer", result.data["note_ids"])
        self.assertIn("(disputed)", result.text)

    def test_note_reads_carry_freshness(self):
        data = self.brain.note("facts-identity-weeks").data
        self.assertEqual(data["verified"], LONG_AGO)
        self.assertTrue(data["stale"].startswith("not verified since"))
        self.assertEqual(self.brain.note("facts-retainer").data["confidence"], "disputed")

    def test_the_owner_verifies_and_it_is_logged(self):
        refused = self.brain.verify("facts-identity-weeks", actor="person:sam")
        self.assertTrue(refused.is_error)
        done = self.brain.verify("facts-identity-weeks", confidence="confirmed")
        self.assertFalse(done.is_error, done.text)
        data = self.brain.note("facts-identity-weeks").data
        self.assertEqual(data["verified"], TODAY.isoformat())
        self.assertIsNone(data["stale"])
        self.assertEqual(data["confidence"], "confirmed")
        last = self.brain.vault.decisions()[-1]
        self.assertEqual((last["action"], last["note"]), ("verified", "facts-identity-weeks"))

    def test_a_minor_edit_does_not_renew_freshness(self):
        before = self.brain.note("facts-retainer").data["meta"].get("revised")
        done = self.brain.decide([{"id": "facts-retainer", "action": "edit", "minor": True,
                                   "body": "The monthly retainer covers eight hours of design "
                                           "support each month."}], label="Typo")
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(self.brain.note("facts-retainer").data["meta"].get("revised"), before)
        self.assertTrue(self.brain.vault.decisions()[-1]["minor"])
        self.brain.decide([{"id": "facts-retainer", "action": "edit",
                            "body": "The monthly retainer covers ten hours of design support."}])
        self.assertTrue(self.brain.note("facts-retainer").data["meta"].get("revised"))

    def test_marking_stale_or_disputed_needs_a_reason_and_the_owner(self):
        self.assertTrue(self.brain.mark("facts-identity-rounds", "stale").is_error)  # no reason
        marked = self.brain.mark("facts-identity-rounds", "stale",
                                 reason="The revision policy changed in September")
        self.assertFalse(marked.is_error, marked.text)
        self.assertEqual(self.brain.note("facts-identity-rounds").data["stale"], "marked stale")
        disputed = self.brain.mark("facts-identity-rounds", "disputed", reason="Sam disagrees")
        self.assertFalse(disputed.is_error, disputed.text)
        self.assertEqual(self.brain.note("facts-identity-rounds").data["confidence"],
                         "disputed")
        self.assertTrue(self.brain.mark("facts-identity-rounds", "gone", reason="x").is_error)
        self.assertTrue(self.brain.mark("facts-identity-rounds", "stale", reason="x",
                                        actor="person:sam").is_error)
        self.assertEqual(self.brain.vault.decisions()[-1]["reason"], "Sam disagrees")


if __name__ == "__main__":
    unittest.main()
