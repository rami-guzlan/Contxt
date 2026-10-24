"""Every note, lesson and file part has an address; gnomon_open returns that part only,
within the pull budget, and says when something the map named is gone (v4 spec, section 6)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import addresses, governance, util
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

PLAN = """# Run of show

## Session 1

Doors at nine, talk at ten.

## Session 2

Panel after lunch.
"""


class SectionAddressTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "webinar-guests", "area": "work", "topic": "general", "kind": "fact",
             "title": "Webinar guests", "summary": "Who speaks.",
             "body": "Intro line.\n\n## Guest bios\n\nDana runs a bakery.\n\n## Logistics\n\n"
                     "Calls start at ten."},
            {"id": "old-plan", "area": "work", "topic": "general", "kind": "fact",
             "title": "Old plan", "body": "## Budget\n\nTwo hundred."},
            {"id": "lore_doghouse", "area": "work", "topic": "lore", "kind": "lesson",
             "load": "manual", "title": "Doghouse moonbase",
             "body": "## Story\n\nOne step after another.\n\n## Pattern\n\nScope creep.\n\n"
                     "## Words\n\none more thing, scope\n"},
            *[{"id": f"filler-{i}", "area": "work", "topic": "general", "kind": "fact",
               "title": f"Filler {i}", "body": f"Filler fact {i}."} for i in range(3)]])
        os.makedirs(os.path.join(self.vault, "references"), exist_ok=True)
        util.atomic_write(os.path.join(self.vault, "references", "run-of-show.md"), PLAN)
        self.brain = se.open_brain(self.vault)
        first = self.brain.context("What is on the webinar?")
        self.session, self.packet = first.data["session_id"], first.data["packet_id"]

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def open(self, address, **extra):
        return self.brain.open(address, session_id=self.session, **extra)

    def test_every_part_has_an_address_named_by_its_heading(self):
        self.assertEqual(addresses.of("webinar-guests", "Intro.\n\n## Guest bios\n\nA.\n"),
                         ["webinar-guests#opening", "webinar-guests#guest-bios"])
        self.assertEqual(addresses.of("plain", "No headings here."), ["plain#body"])
        found = self.brain.sections("webinar-guests")
        self.assertEqual([r["address"] for r in found.data["sections"]],
                         ["webinar-guests#opening", "webinar-guests#guest-bios",
                          "webinar-guests#logistics"])

    def test_opening_a_note_section_returns_that_section_only(self):
        found = self.open("webinar-guests#guest-bios")
        self.assertFalse(found.is_error, found.text)
        self.assertIn("Dana runs a bakery.", found.text)
        self.assertNotIn("Calls start at ten.", found.text)
        self.assertIn("{kept, not verified}", found.text)

    def test_a_file_section_and_a_lesson_story_open_by_address(self):
        part = self.open("run-of-show.md#session-1")
        self.assertIn("Doors at nine", part.text)
        self.assertNotIn("Panel after lunch", part.text)
        story = self.brain.open("lore_doghouse#story")
        self.assertIn("One step after another.", story.text)
        self.assertNotIn("Scope creep.", story.text)

    def test_past_the_pull_budget_only_the_name_comes_back_and_the_receipt_says_so(self):
        self.open("webinar-guests#guest-bios")
        self.open("run-of-show.md#session-1")
        over = self.open("webinar-guests#logistics")
        self.assertTrue(over.is_error)
        self.assertEqual(over.data["status"], "over_pull_budget")
        self.assertNotIn("Calls start at ten.", over.text)
        self.assertIn("Webinar guests", over.text)
        receipt = self.brain.receipt(self.packet)
        opened = [o["address"] for o in receipt.data["opened"]]
        self.assertEqual(opened, ["webinar-guests#guest-bios",
                                  "references/run-of-show.md#session-1"])
        self.assertTrue(all(o["tokens"] > 0 for o in receipt.data["opened"]))
        self.assertEqual([(r["address"], r["says"]) for r in receipt.data["refused"]],
                         [("webinar-guests#logistics", "named only, over the pull budget")])
        self.assertIn("Opened by the AI after the packet", receipt.text)

    def test_the_default_pull_budget_is_two_items_and_about_1500_tokens(self):
        found = self.brain.context("Anything else?", session_id=self.session)
        self.assertIn("open up to 2 more items (about 1,500 tokens)", found.text)
        self.assertEqual(governance.policies(self.brain)["pull_items"], 2)
        self.assertEqual(governance.policies(self.brain)["pull_tokens"], 1500)

    def test_the_owner_sets_the_pull_budget(self):
        done = governance.set_policies(self.brain, {"pull_items": 3, "pull_tokens": 3000})
        self.assertFalse(done.is_error, done.text)
        found = self.brain.context("Anything else?", session_id=self.session)
        self.assertIn("open up to 3 more items (about 3,000 tokens)", found.text)

    def test_something_gone_since_the_map_was_built_is_not_found_with_when(self):
        st = self.brain.state()
        note = st.index.note("old-plan")
        path = os.path.join(self.vault, note.path)
        from brainkit import frontmatter as fm
        meta, body, _errors = fm.parse(util.read_text(path))
        meta.update(status="archived", updated="2026-10-20")
        util.atomic_write(path, fm.dump(meta, body))
        gone = self.open("old-plan#budget")
        self.assertTrue(gone.is_error)
        self.assertEqual(gone.data["status"], "not_found")
        self.assertEqual(gone.data["gone_at"], "2026-10-20")
        self.assertIn("removed on 2026-10-20", gone.text)
        self.assertNotIn("Two hundred", gone.text)
        nothing = self.open("never-was#anything")
        self.assertEqual(nothing.data["status"], "not_found")
        self.assertIsNone(nothing.data["gone_at"])

    def test_after_a_not_found_the_next_packet_carries_a_fresh_map(self):
        again = self.brain.context("And the guests?", session_id=self.session)
        self.assertEqual(again.data["map_included"], "held")
        self.open("never-was#anything")
        fresh = self.brain.context("Who else?", session_id=self.session)
        self.assertEqual(fresh.data["map_included"], "full")
        self.assertIn("## Brain map · partial", fresh.text)


if __name__ == "__main__":
    unittest.main()
