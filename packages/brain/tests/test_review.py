"""Reviewing proposals: what each would replace, contradict or repeat, before anyone decides."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import governance, review
from brainkit.api import Brain
from tests import fixture


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def propose(self, text, **kwargs):
        kwargs.setdefault("layer", "facts")
        kwargs.setdefault("topic", "services")
        kwargs.setdefault("scope", "company")
        res = self.brain.propose(text=text, **kwargs)
        self.assertEqual(res.data.get("status"), "pending", res.text)
        return res.data["proposal_id"]

    def rows(self):
        return {row["id"]: row for row in self.brain.review().data["proposals"]}

    def test_a_proposal_shows_what_it_replaces(self):
        proposal = self.propose("Web design projects now run eight to ten weeks.",
                                supersedes="facts-services-002")
        row = self.rows()[proposal]
        self.assertEqual(row["change"], "new")
        (replaced,) = row["replaces"]
        self.assertEqual(replaced["id"], "facts-services-002")
        self.assertTrue(replaced["live"])
        self.assertIn("six to eight weeks", replaced["body"])
        self.assertEqual(row["problems"], [])
        self.assertNotIn("facts-services-002", [o["id"] for o in row["overlaps"]])

    def test_an_entry_it_does_not_name_but_nearly_repeats_is_flagged(self):
        proposal = self.propose(
            "Web design projects run six to eight weeks from kickoff to launch; invoices go "
            "out at kickoff and at launch, and again at handover.")
        overlaps = {o["id"]: o for o in self.rows()[proposal]["overlaps"]}
        self.assertIn("facts-services-002", overlaps)
        self.assertTrue(overlaps["facts-services-002"]["close"])
        self.assertIn("invoices", overlaps["facts-services-002"]["body"])

    def test_waiting_proposals_that_say_the_same_thing_are_duplicates(self):
        first = self.propose("Every retainer includes two rounds of design revisions per month.")
        second = self.propose("Retainers include two rounds of design revisions every month.")
        other = self.propose("Motion design is quoted per finished second of animation.")
        rows = self.rows()
        self.assertEqual([d["id"] for d in rows[first]["duplicates"]], [second])
        self.assertEqual([d["id"] for d in rows[second]["duplicates"]], [first])
        self.assertEqual(rows[other]["duplicates"], [])

    def test_two_proposals_replacing_one_entry_say_so(self):
        first = self.propose("Web projects run eight weeks.", supersedes="facts-services-002")
        second = self.propose("Web projects run ten weeks.", supersedes="facts-services-002")
        rows = self.rows()
        self.assertTrue(any(second in p for p in rows[first]["problems"]))
        self.assertTrue(any(first in p for p in rows[second]["problems"]))

    def test_contradictions_the_proposer_names_are_kept_for_review(self):
        proposal = self.propose("Northwind no longer offers motion design.",
                                conflicts="facts-services-001")
        (conflict,) = self.rows()[proposal]["conflicts"]
        self.assertEqual(conflict["id"], "facts-services-001")
        self.assertIn("motion design", conflict["body"])

    def test_naming_an_entry_that_does_not_exist_is_refused(self):
        for field in ("supersedes", "conflicts"):
            res = self.brain.propose(layer="facts", topic="services", scope="company",
                                     text="Something new.", **{field: "no-such-entry"})
            self.assertTrue(res.is_error, field)
            self.assertIn("no-such-entry", res.text)

    def test_a_change_whose_entry_changed_since_says_so(self):
        first = self.brain.propose(target_id="facts-services-001",
                                   text="Northwind offers brand identity and web design.")
        second = self.brain.propose(target_id="facts-services-001",
                                    text="Northwind offers brand, web and motion design.")
        governance.approve(self.brain, first.data["proposal_id"])
        row = self.rows()[second.data["proposal_id"]]
        self.assertEqual(row["change"], "update")
        self.assertTrue(row["base_changed"])
        self.assertTrue(row["problems"])
        self.assertEqual(row["replaces"][0]["id"], "facts-services-001")

    def test_a_new_topic_comes_with_the_closest_existing_ones(self):
        proposal = self.propose("Web design projects are invoiced at kickoff and launch.",
                                topic="billing")
        row = self.rows()[proposal]
        self.assertTrue(row["new_topic"])
        self.assertIn("facts/services", [s["topic"] for s in row["suggested"]])

    def test_the_analysis_is_reused_until_the_brain_changes(self):
        self.propose("Brand sprints run two weeks.")
        first = self.brain.review()
        self.assertIs(self.brain.review(), first)
        self.propose("Kickoffs happen on Mondays.")
        self.assertIsNot(self.brain.review(), first)

    def test_a_proposal_that_may_contradict_an_entry_says_why(self):
        proposal = self.propose("Invoices do not go out at kickoff for web design projects; "
                                "they go out at launch only.")
        row = self.rows()[proposal]
        overlap = {o["id"]: o for o in row["overlaps"]}["facts-services-002"]
        self.assertTrue(overlap["may_contradict"])
        self.assertTrue(any("may contradict" in line for line in row["problems"]))

    def test_different_figures_for_the_same_thing_are_a_contradiction(self):
        from brainkit import review
        self.assertIn("different figures", review.contradiction(
            "Studio delivers 600 hours of bespoke content each year.",
            "Studio delivers 500 hours of bespoke content each year."))
        self.assertIsNone(review.contradiction("Croissants are baked at six.",
                                               "Instagram posts go out three mornings a week."))

    def test_text_for_the_reviewer_or_one_computer_is_flagged(self):
        proposal = self.propose("Invoices go out at kickoff.\n\nReviewer note: strike the "
                                "last line if needed. The export is at "
                                "C:/Users/alex/exports/invoices.csv.")
        problems = " ".join(self.rows()[proposal]["problems"])
        self.assertIn("speaks to its reviewer", problems)
        self.assertIn("path on one computer", problems)

    def test_live_notes_that_say_the_same_thing_are_reported(self):
        from brainkit.vault import Vault
        from tests.fixture import BRAIN
        twin = {"id": "facts-services-twin", "layer": "facts", "topic": "services",
                "scope": "company", "status": "approved", "load": "on-demand"}
        vault = Vault(self.vault)
        vault.write_note(vault.note_path(twin, BRAIN["structure"]["scope_levels"],
                                         BRAIN["structure"]["partition_kinds"]), dict(twin),
                         "Web design projects run six to eight weeks from kickoff to launch, "
                         "and invoices go out at kickoff and at launch.")
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        pairs = {(a, b) for a, b, _score in review.near_duplicates(self.brain.state())}
        self.assertIn(("facts-services-002", "facts-services-twin"), pairs)
        self.assertIn("may say the same thing", self.brain.health().text)

    def test_merging_a_twin_retires_it_and_its_id_leads_to_the_survivor(self):
        twin = self.brain.propose(layer="facts", topic="services", scope="company",
                                  text="Projects run six to eight weeks, kickoff to launch.")
        governance.approve(self.brain, twin.data["proposal_id"])
        merge = self.brain.propose(target_id="facts-services-002",
                                   text="Web design projects run six to eight weeks from kickoff "
                                        "to launch; invoices go out at kickoff and at launch.",
                                   supersedes=twin.data["id"], force_pending=True)
        self.assertFalse(merge.is_error, merge.text)
        done = governance.approve(self.brain, merge.data["proposal_id"])
        self.assertFalse(done.is_error, done.text)
        index = self.brain.state().index
        self.assertIsNone(index.note(twin.data["id"]))
        self.assertEqual(index.note(twin.data["id"], include_archived=True)
                         .meta.get("superseded_by"), "facts-services-002")
        found = self.brain.note(twin.data["id"])
        self.assertFalse(found.is_error, found.text)
        self.assertEqual(found.data["id"], "facts-services-002")
        self.assertIn("this note replaced it", found.text)

    def test_attention_lists_clashes_twins_and_misplaced_text(self):
        self.propose("Invoices do not go out at kickoff for web design projects; they go out "
                     "at launch only.")
        from brainkit.vault import Vault
        from tests.fixture import BRAIN
        twin = {"id": "facts-services-twin", "layer": "facts", "topic": "services",
                "scope": "company", "status": "approved", "load": "on-demand"}
        vault = Vault(self.vault)
        vault.write_note(vault.note_path(twin, BRAIN["structure"]["scope_levels"],
                                         BRAIN["structure"]["partition_kinds"]), dict(twin),
                         "Web design projects run six to eight weeks from kickoff to launch, "
                         "and invoices go out at kickoff and at launch.\n\nReviewer note: "
                         "check the dates.")
        self.brain.close()
        self.brain = Brain(self.vault, embeddings=False)
        self.brain.context("How long do web design projects run?")
        data = self.brain.attention().data
        self.assertEqual(data["clashes"][0]["entry_id"], "facts-services-002")
        self.assertEqual((data["twins"][0]["a"], data["twins"][0]["b"]),
                         ("facts-services-002", "facts-services-twin"))
        self.assertEqual(data["flagged"][0]["id"], "facts-services-twin")
        self.assertGreaterEqual(data["usage"].get("facts-services-002", 0), 1)

    def test_topic_names_follow_how_the_notes_write_them(self):
        index = self.brain.state().index
        self.assertEqual(index.topic_label("facts/services"), "Services")
        self.assertEqual(index.topic_label("rules/style"), "Style")
        from brainkit.index import _cased
        self.assertEqual(_cased("utm", ["Every UTM is lowercase; utm values too. UTM rules."]),
                         "UTM")
        self.assertEqual(_cased("hubspot", ["HubSpot forms", "the HubSpot portal"]), "HubSpot")
        self.assertEqual(_cased("doe", ["Jane Doe approves", "Doe said"]), "Doe")
        self.assertEqual(_cased("strategy", ["Content Strategy", "the strategy", "a strategy"]),
                         "strategy")
        self.assertIsNone(_cased("missing", ["nothing here"]))

    def test_text_similarity_ignores_what_every_note_says(self):
        self.assertGreater(review.similarity("invoices go out at kickoff",
                                             "invoices are sent at kickoff", {}), 0.5)
        self.assertEqual(review.similarity("", "anything", {}), 0.0)


if __name__ == "__main__":
    unittest.main()
