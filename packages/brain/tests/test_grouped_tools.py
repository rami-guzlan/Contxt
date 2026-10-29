"""Grouped tools (the owner's list, item 5): one tool per area (notes, skills, files, sheets,
...) with an `action` parameter. Since section 17.4 the server lists three tools (context,
brain, propose), but every grouped name and every earlier one-per-action name still answers,
so apps set up before keep working."""
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

    def test_every_grouped_action_still_answers_though_only_three_tools_are_listed(self):
        self.assertEqual([t["name"] for t in self.server.tools], ["context", "brain", "propose"])
        flat = {t["name"] for t in mcp_server.AGENT_TOOLS}
        covered = {f"{area}_{action}" for area, actions in mcp_server.GROUPS.items()
                   for action in actions}
        self.assertEqual(flat - covered, {"gnomon_get_context"})
        for area, actions in mcp_server.GROUPS.items():
            found = self.server.call(area, {"action": actions[0]})
            self.assertNotIn("is not available", found.text, area)

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

    def test_the_instructions_name_the_three_tools(self):
        said = mcp_server.public_text(mcp_server.INSTRUCTIONS)
        self.assertIn('brain(action: "search")', said)
        self.assertNotIn("notes_search", said)
        self.assertNotIn('notes(action: "search")', said)


if __name__ == "__main__":
    unittest.main()
