"""The Brain map rides at the top of a conversation's first packet, then only as what changed,
stays within its token cap, and the full map is one call away (Release 1 plan, section 10)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import brainmap, focus, util
from brainkit import frontmatter as fm
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
        self.assertIn("## Brain map · partial", first.text)
        self.assertIn("absent here doesn't mean absent from the Brain", first.text)
        self.assertIn("Harbor Street bakery website (aka “the bakery site”)", first.text)
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
        self.assertNotIn("## Brain map · partial", again.text)

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

    def seal(self, name):
        st = self.brain.state()
        project = next(f for f in st.index.focuses.values() if f.title == name)
        path = os.path.join(self.vault, project.note.path)
        meta, body, _errors = fm.parse(util.read_text(path))
        meta["sealed"] = True
        util.atomic_write(path, fm.dump(meta, body))

    def test_a_sealed_project_is_left_out_with_no_name_and_no_count(self):
        made = focus.create_focus(self.brain, "Quiet client rebrand", "Rebrand, sealed.")
        self.assertFalse(made.is_error, made.text)
        self.seal("Quiet client rebrand")
        first = self.ask("What projects are active?")
        self.assertNotIn("Quiet client rebrand", first.text)
        self.assertNotIn("+1 more", first.text)
        self.assertNotIn("sealed", first.text.lower())
        whole = self.brain.brain_map(tier="projects")
        self.assertNotIn("Quiet client rebrand", whole.text)
        view = self.brain.map_view()
        self.assertEqual(view.data["sealed"], 1)  # the owner's own view says one is there
        self.assertNotIn("Quiet client rebrand", view.data["text"])

    def test_a_tier_cut_to_fit_ends_with_more_and_gnomon_map_returns_it_whole(self):
        st = self.brain.state()
        found = brainmap.build(st, self.brain, st.scopes.chain("person:me"), [])
        found["projects"] = [{"id": f"p{i}", "name": f"Project {i}", "aka": [],
                              "status": "active", "address": f"p{i}"} for i in range(9)]
        shown = brainmap.render(found)
        self.assertIn("; +3 more", shown["text"])
        self.assertEqual(shown["cut"]["projects"], 3)
        whole = brainmap.full(found, tier="projects")
        self.assertEqual(len(whole["lines"]), 9)
        self.assertIn("Project 8 [active] (open: p8)", whole["lines"])

    def test_the_map_counts_entries_by_level_and_lists_lore_titles(self):
        se.add_notes(self.vault, [
            {"id": "always-sign-off", "area": "work", "topic": "money", "kind": "rule",
             "title": "Sign-off", "load": "domain", "applies_to": ["work"],
             "triggers": ["invoice"], "must_text": "The owner signs off every invoice",
             "body": "The owner signs off every invoice."},
            {"id": "checked-fact", "area": "work", "topic": "money", "kind": "fact",
             "title": "Bank", "verified": "2026-10-01", "body": "We bank locally."},
            {"id": "lore_two_exports", "area": "work", "topic": "lore", "kind": "lesson",
             "load": "manual", "title": "Two exports, one slide",
             "body": "## Story\n\nTwo numbers.\n\n## Pattern\n\nNo version.\n\n"
                     "## Words\n\nregistrations, total\n"}])
        found = self.ask("When do invoices go out?")
        self.assertIn("Lore: Two exports, one slide", found.text)
        self.assertIn("By level: canon 1 · confirmed 1 · kept", found.text)
        self.assertIn("exhaust 0", found.text)
        self.assertIn("Must-hold domains: The owner signs off every invoice", found.text)
        self.assertEqual(self.brain.brain_map(tier="lore").data["lines"],
                         ["Two exports, one slide (open: lore_two_exports#story)"])


if __name__ == "__main__":
    unittest.main()
