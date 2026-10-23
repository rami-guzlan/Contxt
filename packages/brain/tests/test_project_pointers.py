"""A project summary must not hide the separately approved facts behind it."""
import unittest

from brainkit import safeguards_eval
from brainkit.api import Brain
from tests import fixture


class ProjectFactPointers(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.project = self.brain.focus_create(
            "Harbor workshop", "Prepare the workshop venue.", principal="person:alex"
        ).data["id"]
        safeguards_eval.add_notes(self.vault, [
            {"id": "workshop-budget", "title": "Harbor workshop approved budget",
             "summary": "The Harbor workshop budget is 4800 dollars.",
             "area": "projects", "topic": self.project, "scope": "person:alex",
             "kind": "decision", "body": "The approved budget is 4800 dollars. The proposed increase was rejected."},
            {"id": "workshop-venue", "title": "Harbor workshop venue",
             "summary": "The Harbor workshop venue is Green Hall.",
             "area": "facts", "topic": "services", "scope": "person:alex",
             "body": "The Harbor workshop takes place in Green Hall."},
            {"id": "sam-workshop-budget", "title": "Harbor workshop budget",
             "area": "projects", "topic": self.project, "scope": "person:sam",
             "body": "Sam's private budget is 9900 dollars."},
            {"id": "workshop-goal", "title": "Harbor workshop budget target",
             "area": "projects", "topic": self.project, "scope": "person:alex",
             "load": "manual", "body": "The owner's private budget target is 2200 dollars."},
        ])

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def context(self, request, **kwargs):
        return self.brain.context(request, principal="person:alex", **kwargs)

    def test_approved_project_facts_are_reachable_and_can_be_opened(self):
        for request in ("What budget is approved for the Harbor workshop?",
                        "What is the current approved budget for the Harbor workshop?"):
            with self.subTest(request=request):
                result = self.context(request, record=False)
                self.assertIn("workshop-budget", result.data["related_ids"])
                self.assertIn("workshop-budget", result.text)
                opened = self.brain.note("workshop-budget", principal="person:alex")
                self.assertIn("4800", opened.text)
                self.assertIn("rejected", opened.text)

    def test_project_facts_are_reachable_when_filed_outside_the_project_folder(self):
        result = self.context("What is the venue for the Harbor workshop?", record=False)
        self.assertIn("workshop-venue", result.data["related_ids"] + result.data["note_ids"])

    def test_pointers_do_not_expose_other_principals_or_manual_notes(self):
        result = self.context("What budget is approved for the Harbor workshop?", record=False)
        visible = set(result.data["note_ids"] + result.data["related_ids"])
        self.assertFalse({"sam-workshop-budget", "workshop-goal"} & visible)
        self.assertNotIn("9900", result.text)
        self.assertNotIn("2200", result.text)

    def test_a_general_project_overview_does_not_expand_into_its_facts(self):
        result = self.context("Where are we with the Harbor workshop?", record=False)
        self.assertEqual(result.data["note_ids"], [self.project])
        self.assertEqual(result.data["related_ids"], [])

    def test_opened_project_fact_is_held_without_repeating_its_body(self):
        opened = self.brain.note("workshop-budget", principal="person:alex", session_id="facts")
        again = self.context("workshop-budget", session_id="facts")
        self.assertIn("4800", opened.text)
        self.assertIn("workshop-budget", again.data["held_ids"])
        self.assertNotIn("The approved budget is 4800", again.text)

    def test_a_related_project_pointer_does_not_promote_its_body(self):
        result = self.context("What budget is approved for the Harbor workshop?", record=False)
        self.assertEqual(result.data["note_ids"], [self.project])
        self.assertNotIn("The proposed increase was rejected.", result.text)


    def test_membership_cache_never_shares_private_candidates_between_callers(self):
        safeguards_eval.set_meta(self.vault, [self.project], scope="company")
        first = self.context("What budget is approved for the Harbor workshop?", record=False)
        self.assertIn("workshop-budget", first.data["related_ids"])
        other = self.brain.context("What budget is approved for the Harbor workshop?",
                                   principal="person:sam", record=False)
        visible = set(other.data["related_ids"] + other.data["note_ids"])
        self.assertNotIn("workshop-budget", visible)
        self.assertNotIn("workshop-venue", visible)
        self.assertNotIn("4800", other.text)

    def test_new_project_facts_invalidate_membership_cache(self):
        self.context("What budget is approved for the Harbor workshop?", record=False)
        safeguards_eval.add_notes(self.vault, [{
            "id": "workshop-travel-budget", "title": "Harbor workshop travel budget",
            "summary": "The approved Harbor workshop travel budget is 950 dollars.",
            "area": "facts", "topic": "travel", "scope": "person:alex", "kind": "decision",
            "body": "The Harbor workshop travel budget is 950 dollars."}])
        result = self.context("What is the approved travel budget for the Harbor workshop?",
                              record=False)
        self.assertIn("workshop-travel-budget", result.data["related_ids"])
        self.assertIn("workshop-travel-budget", result.text)

    def test_every_reported_pointer_is_visible_to_the_model(self):
        for request in ("What budget is approved for the Harbor workshop?",
                        "What is the venue for the Harbor workshop?",
                        "Where are we with the Harbor workshop?"):
            with self.subTest(request=request):
                result = self.context(request, record=False)
                for note_id in result.data["related_ids"]:
                    self.assertIn(note_id, result.text)

    def test_model_without_tools_is_not_told_to_open_project_pointers(self):
        result = self.context("What budget is approved for the Harbor workshop?",
                              tools=False, record=False)
        self.assertNotIn("Open one with notes_get", result.text)
