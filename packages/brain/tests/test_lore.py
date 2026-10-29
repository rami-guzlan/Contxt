"""Lore: a lesson goes in full the first time it is relevant in a conversation, then by name
only, and a proposed lesson waits for the owner like any other (v4 spec, section 6)."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import mcp_server
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

STORY = ("## Story\n\nThe slide said 214 while the newer export said 388.\n\n## Pattern\n\n"
         "Quoting a number without the version it came from.\n\n## Words\n\n"
         "registrations, how many, total\n")


class LoreTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        se.add_notes(self.vault, [
            {"id": "lore_two_exports", "area": "work", "topic": "lore", "kind": "lesson",
             "load": "manual", "title": "Two exports, one slide", "body": STORY},
            {"id": "webinar", "area": "work", "topic": "general", "kind": "fact",
             "title": "Webinar", "body": "The webinar has registrations open."}])
        self.brain = se.open_brain(self.vault)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_a_lesson_goes_in_full_the_first_time_then_by_name_only(self):
        first = self.brain.context("How many registrations do we have?")
        self.assertIn("## Lesson: Two exports, one slide", first.text)
        self.assertIn("Watch for: Quoting a number without the version", first.text)
        self.assertEqual(first.data["lessons_full"], ["lore_two_exports"])
        again = self.brain.context("And the registrations total now?",
                                   session_id=first.data["session_id"])
        self.assertNotIn("The slide said 214", again.text)
        self.assertIn("## Lessons already given this conversation", again.text)
        self.assertIn("Two exports, one slide (`lore_two_exports#story`)", again.text)
        self.assertEqual(again.data["lessons_named"], ["lore_two_exports"])
        receipt = self.brain.receipt(first.data["packet_id"]).data
        self.assertIn("lesson in full", [s.get("form") for s in receipt["sent"]])

    def test_a_request_without_its_words_does_not_bring_the_lesson_up(self):
        found = self.brain.context("What time does the webinar start?")
        self.assertNotIn("## Lesson:", found.text)

    def test_a_lesson_is_never_routed_as_an_ordinary_note(self):
        found = self.brain.context("Tell me about the slide and the export")
        self.assertNotIn("lore_two_exports", found.data.get("note_ids") or [])

    def test_lore_list_and_lore_get_give_titles_levels_and_the_story(self):
        listed = self.brain.lore()
        self.assertEqual([r["title"] for r in listed.data["lessons"]],
                         ["Two exports, one slide"])
        self.assertEqual(listed.data["lessons"][0]["level_label"], "kept, not verified")
        self.assertIn("`lore_two_exports#story`", listed.text)
        one = self.brain.lesson("lore_two_exports")
        self.assertEqual(one.data["words"], ["registrations", "how many", "total"])
        self.assertIn("Story: The slide said 214", one.text)

    def test_a_proposed_lesson_waits_in_catch_up_like_any_other(self):
        made = self.brain.propose_lesson(
            title="The CC nobody asked for", story="An AI added a CC twice; both undone.",
            pattern="Adding watchers when the rule asks for a sign-off at the end.",
            words=["cc", "loop in"], evidence="Undone twice.")
        self.assertFalse(made.is_error, made.text)
        waiting = [p for p in self.brain.inbox().data["proposals"]
                   if p["target"].get("kind") == "lesson"]
        self.assertEqual(len(waiting), 1)
        self.assertEqual(waiting[0]["title"], "The CC nobody asked for")
        self.assertIn("## Pattern", waiting[0]["body"])

    def test_a_lesson_without_its_story_or_words_is_refused(self):
        refused = self.brain.propose_lesson(title="Empty", story="", pattern="x", words=[])
        self.assertTrue(refused.is_error)
        self.assertIn("a lesson needs its story", refused.text)

    def test_the_lore_tools_are_on_the_brain_mcp_server(self):
        server = mcp_server.Server(self.brain)
        brain = next(t for t in server.tools if t["name"] == "brain")
        self.assertTrue({"lore", "lesson"} <= set(brain["inputSchema"]["properties"]["action"]
                                                   ["enum"]))
        self.assertEqual(mcp_server.GROUPS["lore"], ["list", "get", "propose"])
        found = server.call("lore_get", {"id": "lore_two_exports"})
        self.assertFalse(found.is_error, found.text)


if __name__ == "__main__":
    unittest.main()
