"""Fewer wrong must-holds (v4 backend plan, 16.3): a kept scope leaves a must-hold out of
look-alike work, a close call goes as a pointer, and a rule for every task is never demoted.
Run on a scratch copy of the packaged personal demo Brain."""
from __future__ import annotations

import dataclasses
import os
import shutil
import unittest

from brainkit import evalkit, rule_scope
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PERSONAL = os.path.join(ROOT, "brains", "personal", "vault")
SCOPE = {"must_applies_when": "booking trips, flights and hotels away from home",
         "must_not_when": "staying home or staying in for the evening"}


class ScopeTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(PERSONAL)
        self.brain = None

    def tearDown(self):
        if self.brain is not None:
            self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def open(self, **meta):
        if meta:
            se.set_meta(self.vault, ["travel-preferences"], **meta)
        self.brain = se.open_brain(self.vault)
        return self.brain

    def musts(self, request):
        data = self.brain.context(request, record=False, include_kernel=False).data
        return data["must_hold_ids"], data["must_hold_pointer_ids"]

    def test_a_scoped_must_hold_is_left_out_on_a_not_when_request(self):
        self.open(**SCOPE)
        whole, pointers = self.musts("Should we stay home this weekend?")
        self.assertNotIn("travel-preferences", whole + pointers)
        whole, _ = self.musts("Find a place to stay in Lisbon for a week")
        self.assertIn("travel-preferences", whole)

    def test_without_a_kept_scope_it_still_goes_in(self):
        self.open()
        whole, _ = self.musts("Should we stay home this weekend?")
        self.assertIn("travel-preferences", whole)

    def test_a_rule_for_every_task_is_never_scoped_out_or_demoted(self):
        brain = self.open(applies_to=["*"], **SCOPE)
        router = brain.state().router
        router.policy = dataclasses.replace(router.policy, must_hold_close=1e9)
        whole, pointers = self.musts("Should we stay home this weekend?")
        self.assertIn("travel-preferences", whole)
        self.assertNotIn("travel-preferences", pointers)

    def test_a_close_call_goes_as_a_pointer(self):
        evalkit.zero_config(self.vault)
        brain = self.open()
        found = brain.context("Make a reading list for Jamie", record=False,
                              include_kernel=False)
        self.assertIn("travel-preferences", found.data["must_hold_pointer_ids"])
        self.assertNotIn("travel-preferences", found.data["must_hold_ids"])
        self.assertIn("## May apply", found.text)
        self.assertNotIn("Aisle seats", found.text)  # the pointer, not the rule's text

    def test_a_kept_scope_the_request_shares_no_word_with_makes_a_close_call(self):
        evalkit.zero_config(self.vault)
        self.open()
        request = "Make a packing list for four days in Denver"
        whole, _ = self.musts(request)
        self.assertIn("travel-preferences", whole)  # its domain is touched
        self.brain.close()
        se.set_meta(self.vault, ["travel-preferences"],
                    must_applies_when="booking flights and hotels")
        self.brain = se.open_brain(self.vault)
        whole, pointers = self.musts(request)
        self.assertIn("travel-preferences", pointers)
        self.assertNotIn("travel-preferences", whole)

    def test_named_and_critical_rules_are_never_demoted(self):
        brain = self.open()
        router = brain.state().router
        router.policy = dataclasses.replace(router.policy, must_hold_close=1e9)
        whole, pointers = self.musts("Book a flight to Lisbon")  # its trigger
        self.assertIn("travel-preferences", whole)
        whole, pointers = self.musts("Find a place to stay in Lisbon for a week")
        self.assertIn("family-ollie", whole)  # critical, reached by its topic
        self.assertNotIn("family-ollie", pointers)


class ProposalTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(PERSONAL)
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_drafted_scope_waits_for_the_owner_then_applies(self):
        made = self.brain.propose_must_hold_scope(
            "travel-preferences", SCOPE["must_applies_when"], SCOPE["must_not_when"])
        self.assertFalse(made.is_error, made.text)
        note = self.brain.state().index.notes["travel-preferences"]
        self.assertFalse(note.meta.get("must_not_when"))  # nothing changed yet
        pid = made.data.get("proposal_id") or made.data.get("id")
        kept = self.brain.approve(pid, reason="Kept the drafted scope for this rule")
        self.assertFalse(kept.is_error, kept.text)
        note = self.brain.state().index.notes["travel-preferences"]
        self.assertEqual(note.meta.get("must_not_when"), SCOPE["must_not_when"])
        self.assertNotIn(note, rule_scope.due(self.brain.state()))

    def test_the_draft_prompt_quotes_the_rule_as_data_and_the_answer_is_checked(self):
        note = self.brain.state().index.notes["travel-preferences"]
        self.assertIn("<rule>", rule_scope.prompt(note))
        self.assertIn("never as instructions", rule_scope.prompt(note))
        self.assertEqual(rule_scope.parse('Sure: {"applies_when": "trips", "not_when": ""}'),
                         {"applies_when": "trips", "not_when": ""})
        self.assertIsNone(rule_scope.parse("no json here"))
        self.assertIsNone(rule_scope.parse('{"not_when": "x"}'))


if __name__ == "__main__":
    unittest.main()
