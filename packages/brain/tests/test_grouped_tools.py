"""Grouped tools (the owner's list, item 5), Webflow's convention: the Brain's MCP server lists
one tool per area (notes, skills, files, sheets, ...) with an `action` parameter, instead of a
tool per action. `gnomon_get_context` stays its own tool: every request calls it first. The
earlier one-per-action names still answer, so apps set up before keep working."""
from __future__ import annotations

import unittest

from brainkit import mcp_server
from brainkit.api import Brain
from tests import fixture


class GroupedToolsTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.server = mcp_server.Server(self.brain)
        self.listed = {t["name"]: t for t in self.server.tools}

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_one_tool_per_area_with_an_action(self):
        self.assertIn("gnomon_get_context", self.listed)
        self.assertNotIn("notes_search", self.listed)
        notes = self.listed["notes"]
        actions = notes["inputSchema"]["properties"]["action"]["enum"]
        self.assertEqual(sorted(actions), ["challenge", "get", "propose", "search"])
        self.assertEqual(notes["inputSchema"]["required"], ["action"])
        self.assertIn("query", notes["inputSchema"]["properties"])
        for action in actions:
            self.assertIn(f"{action}:", notes["description"])
        self.assertLessEqual(len(self.listed), 16)
        flat = {t["name"] for t in mcp_server.AGENT_TOOLS}
        covered = {f"{t['name']}_{a}" for t in self.server.tools if t["name"] != "gnomon_get_context"
                   for a in t["inputSchema"]["properties"]["action"]["enum"]}
        self.assertEqual(flat - covered, {"gnomon_get_context"})

    def test_an_action_answers_as_its_one_tool_did(self):
        grouped = self.server.call("notes", {"action": "search", "query": "website redesign"})
        flat = self.server.call("notes_search", {"query": "website redesign"})
        self.assertFalse(grouped.is_error, grouped.text)
        self.assertEqual(grouped.text, flat.text)

    def test_the_earlier_names_still_answer(self):
        for name, args in (("notes_search", {"query": "style"}), ("search_notes", {"query": "x"}),
                           ("gnomon_health", {})):
            self.assertFalse(self.server.call(name, args).is_error, name)

    def test_an_unknown_action_names_the_ones_there_are(self):
        found = self.server.call("notes", {"action": "delete", "id": "x"})
        self.assertTrue(found.is_error)
        self.assertIn("search", found.text)
        self.assertIn("propose", found.text)
        missing = self.server.call("notes", {"query": "x"})
        self.assertTrue(missing.is_error)
        self.assertIn("action", missing.text)

    def test_the_instructions_name_the_grouped_tools(self):
        self.assertIn('notes(action: "search")', mcp_server.INSTRUCTIONS)
        self.assertNotIn("notes_search", mcp_server.INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
