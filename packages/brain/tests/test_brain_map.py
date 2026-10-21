"""The Brain map rides at the top of a conversation's first packet, then only as what changed,
stays within its token cap, and the full map is one call away (Release 1 plan, section 10)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import brainmap, focus, util
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class BrainMapTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "invoice-days", "area": "work", "topic": "money", "kind": "fact",
             "title": "Invoice days", "summary": "When invoices go out.",
             "body": "Invoices go out on the 1st and the 15th."}])
        self.brain = se.open_brain(self.vault)
        made = focus.create_focus(self.brain, "Harbor Street bakery website",
                                  "Launch the ordering site.", aliases=["the bakery site"])
        assert not made.is_error, made.text

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def ask(self, request, session=None, **extra):
        return self.brain.context(request, session_id=session, **extra)

    def test_the_first_packet_carries_the_map_and_the_next_one_does_not_repeat_it(self):
        first = self.ask("When do invoices go out?")
        self.assertIn("Brain map: a partial list", first.text)
        self.assertIn("Harbor Street bakery website (also the bakery site)", first.text)
        self.assertEqual(first.data["map_included"], "full")
        again = self.ask("What else is due this week?", first.data["session_id"])
        self.assertNotIn("Brain map", again.text)
        self.assertEqual(again.data["map_included"], "held")

    def test_a_change_sends_only_what_changed(self):
        first = self.ask("When do invoices go out?")
        made = focus.create_focus(self.brain, "Office move to Pine Avenue",
                                  "Move the team by January 15.")
        self.assertFalse(made.is_error, made.text)
        again = self.ask("What is going on?", first.data["session_id"])
        self.assertEqual(again.data["map_included"], "changes")
        self.assertIn("Brain map changed: + project Office move to Pine Avenue", again.text)
        self.assertNotIn("Brain map: a partial list", again.text)

    def test_a_brief_without_the_startup_context_has_no_map(self):
        found = self.ask("When do invoices go out?", include_kernel=False, record=False)
        self.assertNotIn("Brain map", found.text)

    def test_the_short_map_stays_within_its_cap_however_much_the_brain_holds(self):
        st = self.brain.state()
        chain = st.scopes.chain("person:me")
        found = brainmap.build(st, self.brain, chain, [])
        found["projects"] = [{"id": f"p{i}", "name": f"Project number {i} with a long name",
                              "aka": ["another name"], "status": "active"}
                             for i in range(40)]
        found["projects"][27]["name"] = "Lighthouse restoration"
        text = brainmap.short(found, "What is the lighthouse restoration budget?")
        self.assertLessEqual(util.tokens(text), brainmap.MAP_TOKENS)
        self.assertIn("Lighthouse restoration", text)

    def test_the_full_map_is_paged_and_can_be_narrowed_to_an_area(self):
        found = self.brain.brain_map(area="work")
        self.assertFalse(found.is_error, found.text)
        self.assertTrue(any(line.startswith("area Work") for line in found.data["lines"]))
        self.assertFalse(any(line.startswith("project") for line in found.data["lines"]))
        everything = self.brain.brain_map()
        self.assertIn("project Harbor Street bakery website [active] also the bakery site",
                      everything.data["lines"])


if __name__ == "__main__":
    unittest.main()
