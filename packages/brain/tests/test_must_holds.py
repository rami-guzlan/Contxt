"""Must-holds: constraints that go into every brief whenever their domain comes up.

Run on a scratch copy of the packaged personal demo Brain, where the peanut allergy, the
budget, travel and sleep rules are must-holds and the allergy is critical.
"""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import kernel as kernel_mod
from brainkit import mcp_server
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PERSONAL = os.path.join(ROOT, "brains", "personal", "vault")


class MustHoldTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(PERSONAL)
        self.brain = se.open_brain(self.vault)
        self.owner = self.brain.state().config.owner

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def context(self, request, **kwargs):
        kwargs.setdefault("record", False)
        kwargs.setdefault("include_kernel", False)
        return self.brain.context(request, **kwargs)

    # ------------------------------------------------------------------ routing
    def test_a_request_in_the_domain_gets_the_must_hold_without_naming_it(self):
        result = self.context("Plan Tuesday dinner for the four of us")
        self.assertIn("family-ollie", result.data["must_hold_ids"])
        text = result.text
        self.assertIn("## Must hold", text)
        self.assertIn("allergic to peanuts", text)
        # it comes right after the task, before anything else the brief carries
        self.assertLess(text.index("## Must hold"), text.index("## Scope"))

    def test_a_decoy_from_another_domain_does_not(self):
        result = self.context("Fix the dripping bathroom faucet")
        self.assertNotIn("family-ollie", result.data["must_hold_ids"])

    def test_the_trace_says_why_each_must_hold_is_in(self):
        result = self.brain.context("What should we cook this weekend?", record=False,
                                    include_kernel=False, explain=True)
        musts = {m["id"]: m["why"] for m in result.data["trace"]["must_holds"]}
        self.assertIn("cook", musts["family-ollie"])

    def test_must_holds_sit_outside_the_note_budget(self):
        se.set_meta(self.vault, ["family-ollie"], must_text=" ".join(["peanuts"] * 35))
        brain_json = os.path.join(self.vault, "brain.json")
        import json
        with open(brain_json, encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("budgets", {})["note_tokens"] = {"micro": 1, "standard": 1, "deep": 1,
                                                         "standard_knowledge": 1}
        with open(brain_json, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        result = self.context("Plan Tuesday dinner for the four of us")
        self.assertIn("family-ollie", result.data["must_hold_ids"])

    def test_every_packet_of_a_conversation_carries_them_again(self):
        first = self.brain.context("Plan Tuesday dinner")
        session = first.data["session_id"]
        second = self.brain.context("And a dessert for after?", session_id=session)
        self.assertIn("family-ollie", second.data["must_hold_ids"])
        self.assertNotIn("family-ollie", second.data.get("held_ids") or [])

    def test_a_stale_must_hold_still_goes_in_flagged(self):
        se.set_meta(self.vault, ["family-ollie"], review_by="2020-01-01")
        result = self.context("Plan Tuesday dinner")
        self.assertIn("family-ollie", result.data["must_hold_ids"])
        self.assertIn("Stale (review was due 2020-01-01)", result.text)

    def test_a_model_without_tools_gets_every_must_hold_in_full(self):
        result = self.brain.context("Plan a dinner party with a long walk after on a "
                                    "school night", record=False, include_kernel=False,
                                    tools=False)
        self.assertIn("## Must hold", result.text)
        self.assertNotIn("get_note", result.text.split("## Must hold")[1].split("##")[0])

    def test_past_the_cap_must_holds_are_listed_by_title(self):
        notes = [{"id": f"rule-{i}", "area": "food", "topic": "diet", "kind": "rule",
                  "load": "domain", "applies_to": "food", "triggers": ["dinner"],
                  "title": f"Rule {i}", "body": f"Dinner rule number {i}."} for i in range(9)]
        se.add_notes(self.vault, notes)
        result = self.context("Plan Tuesday dinner")
        self.assertEqual(len(result.data["must_hold_ids"]), 8)
        self.assertTrue(result.data["must_hold_listed"])
        self.assertIn("open each with get_note", result.text)
        # the critical one is never the one pushed out
        self.assertEqual(result.data["must_hold_ids"][0], "family-ollie")

    def test_a_progress_update_does_not_carry_must_holds(self):
        st = self.brain.state()
        focus = next(iter(st.index.focuses.values()))
        result = self.context(f"Update {focus.title}: we finished the dinner plan")
        if result.data["mode"] == "focus-update":
            self.assertEqual(result.data["must_hold_ids"], [])

    # ------------------------------------------------------------------ the startup index
    def test_the_kernel_lists_the_domains_with_must_holds(self):
        st = self.brain.state()
        chain = self.brain.caller(None)[0]
        text, _fingerprint = kernel_mod.render(st.config, st.index, st.scopes, chain)
        self.assertIn("## Must-hold domains", text)
        index = text.split("## Must-hold domains")[1].split("\n## ")[0]
        # critical: its line in full; the rest by title and id
        self.assertIn("allergic to peanuts", index)
        self.assertIn("(`money-budget`)", index)
        self.assertIn("The monthly budget", index)
        self.assertIn("- food (", index)
        self.assertIn("topics.md", index)

    def test_without_tools_the_kernel_carries_only_the_critical_lines(self):
        st = self.brain.state()
        chain = self.brain.caller(None)[0]
        text, _fp = kernel_mod.render(st.config, st.index, st.scopes, chain, tools=False)
        self.assertNotIn("## Must-hold domains", text)
        self.assertIn("## Must hold", text)
        self.assertIn("family-ollie", text)
        self.assertNotIn("money-budget", text)

    def test_marking_a_must_hold_changes_the_kernel_fingerprint(self):
        st = self.brain.state()
        chain = self.brain.caller(None)[0]
        _text, before = kernel_mod.render(st.config, st.index, st.scopes, chain)
        result = self.brain.propose(target_id="food-diet", text=st.index.notes["food-diet"].body,
                                    load="domain", applies_to="food", triggers="vegetarian",
                                    principal=self.owner)
        self.assertFalse(result.is_error, result.text)
        if result.data.get("status") == "pending":
            approved = self.brain.approve(result.data["proposal_id"], actor=self.owner)
            self.assertFalse(approved.is_error, approved.text)
        st = self.brain.state()
        text, after = kernel_mod.render(st.config, st.index, st.scopes, chain)
        self.assertNotEqual(before, after)
        self.assertIn("food-diet", text.split("## Must-hold domains")[1])

    # ------------------------------------------------------------------ governance
    def refused(self, **kwargs):
        st = self.brain.state()
        kwargs.setdefault("target_id", "food-diet")
        kwargs.setdefault("text", st.index.notes["food-diet"].body)
        result = self.brain.propose(principal=self.owner, **kwargs)
        return result.is_error, result.text

    def test_must_hold_fields_need_load_domain(self):
        error, text = self.refused(triggers="dinner")
        self.assertTrue(error)
        self.assertIn("load: domain", text)

    def test_applies_to_must_name_an_area_topic_or_project(self):
        error, text = self.refused(load="domain", applies_to="kitchen-sink")
        self.assertTrue(error)
        self.assertIn("kitchen-sink", text)

    def test_triggers_are_words_or_short_phrases(self):
        error, text = self.refused(load="domain", triggers="a very long trigger phrase that "
                                   "goes on and on")
        self.assertTrue(error)
        self.assertIn("trigger", text)

    def test_at_most_three_must_holds_are_critical(self):
        se.set_meta(self.vault, ["money-budget", "travel-preferences"], critical="true")
        error, text = self.refused(load="domain", critical=True)
        self.assertTrue(error)
        self.assertIn("at most 3", text)

    def test_the_connector_offers_the_must_hold_fields(self):
        tool = next(t for t in mcp_server.AGENT_TOOLS if t["name"] == "propose_note")
        props = tool["inputSchema"]["properties"]
        self.assertIn("domain", props["load"]["enum"])
        for name in ("applies_to", "triggers", "must_text", "critical"):
            self.assertIn(name, props)


if __name__ == "__main__":
    unittest.main()
