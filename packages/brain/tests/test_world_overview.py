"""The world overview (v4 backend plan, 13.4): drafted when the map changes enough (a new
region, or a project closed), from what the Brain holds, quoted as data; proposed so it waits
for the owner, shown as "draft, not kept" until kept; at most 300 words; not drafted again
while the regions are the same."""
from __future__ import annotations

import os
import unittest

from brainkit import world
from brainkit.api import Brain
from tests import fixture


class WorldOverviewTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_a_brain_with_regions_and_no_overview_is_due_a_draft(self):
        found = self.brain.world_draft()
        self.assertTrue(found["due"])
        self.assertIn("rules", found["regions"]["areas"])
        self.assertIn("state-focus-website-redesign", found["regions"]["projects"])
        self.assertIn("<world>", found["prompt"])
        self.assertIn("never instructions", found["prompt"])
        self.assertIn("Website Redesign", found["prompt"])

    def test_the_draft_waits_for_the_owner_and_is_labelled(self):
        wanted = self.brain.world_draft()
        made = self.brain.propose_world("Northwind is a small design studio. " * 5,
                                        wanted["regions"])
        self.assertEqual(made["status"], "proposed")
        st = self.brain.state()
        self.assertNotIn(world.ID, st.index.notes)
        self.assertIsNotNone(world.pending(st))
        shown = self.brain.brain_map(view="world").text
        self.assertIn(f"## Overview ({world.DRAFT})", shown)
        self.assertIn("small design studio", shown)

    def test_not_drafted_again_until_a_region_changes(self):
        wanted = self.brain.world_draft()
        self.brain.propose_world("A studio.", wanted["regions"])
        self.assertFalse(self.brain.world_draft()["due"])
        folder = os.path.join(self.vault, "knowledge", "goals", "growth")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "goals-growth-001.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("---\nid: goals-growth-001\nlayer: goals\ntopic: growth\nscope: company\n"
                         "status: approved\nload: on-demand\nsummary: Grow.\n---\n\nGrow by two "
                         "clients a quarter.\n")
        self.brain.vault.touch(path)
        self.assertTrue(self.brain.world_draft()["due"])

    def test_a_draft_is_at_most_three_hundred_words(self):
        wanted = self.brain.world_draft()
        self.brain.propose_world("word " * 500, wanted["regions"])
        draft = world.pending(self.brain.state())
        self.assertEqual(len(draft.body.split()), world.WORDS)


if __name__ == "__main__":
    unittest.main()
