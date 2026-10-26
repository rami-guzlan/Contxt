"""The world view and edges in packets (v4 backend plan, 13.2 and 13.4): an entry in a packet
shows up to two edges, each to something the same packet holds; `gnomon_map(view: "world")`
shows the kept overview, the regions, how entries relate and the lessons, only what the caller
may see."""
from __future__ import annotations

import os
import unittest

from brainkit import mcp_server
from brainkit.api import Brain
from tests import fixture

WHY = """---
id: rules-headline-why
layer: rules
topic: style
scope: company
status: approved
load: on-demand
summary: Why our headlines use sentence case.
relates:
  - "explains: rules-style-002"
  - "explains: facts-services-002"
---

Sentence case headlines read as plain speech, which is why the studio's headlines use them.
"""

SEALED = """---
id: facts-acme-rates
layer: facts
topic: clients
scope: client:acme
partition: client:acme
status: approved
load: on-demand
summary: Acme's negotiated rates.
supersedes: facts-clients-acme-001
---

Acme pays a negotiated rate.
"""


class WorldTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        folder = os.path.join(self.vault, "knowledge", "rules", "style")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "rules-headline-why.md"), "w", encoding="utf-8") as h:
            h.write(WHY)
        with open(os.path.join(folder, "facts-acme-rates.md"), "w", encoding="utf-8") as h:
            h.write(SEALED)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_an_entry_in_a_packet_shows_edges_only_to_what_the_packet_holds(self):
        text = self.brain.context("Why do our headlines use sentence case?").text
        self.assertIn("rules-headline-why", text)
        self.assertIn("rules-style-002", text)
        self.assertIn("Related: explains `rules-style-002`", text)
        if "facts-services-002" not in text:
            self.assertNotIn("explains `facts-services-002`", text)

    def test_the_world_view_shows_regions_relations_and_no_sealed_counts(self):
        found = self.brain.brain_map(view="world")
        self.assertFalse(found.is_error, found.text)
        self.assertIn("No world overview kept yet.", found.text)
        self.assertIn("## How entries relate", found.text)
        self.assertIn("explains", found.data["relations"])
        self.assertNotIn("supersedes", found.data["relations"])  # only the sealed entry's
        self.assertNotIn("acme", found.text.lower())

    def test_a_kept_overview_leads_the_world_view(self):
        folder = os.path.join(self.vault, "knowledge", "identity")
        path = os.path.join(folder, "world.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("---\nid: world\nlayer: identity\ntopic: identity\nscope: company\n"
                         "status: approved\nload: on-demand\nsummary: The studio's world.\n"
                         "---\n\nNorthwind is a small design studio working on websites.\n")
        self.brain.vault.touch(path)
        found = self.brain.brain_map(view="world")
        self.assertIn("## Overview", found.text)
        self.assertIn("small design studio", found.text)

    def test_agents_read_it_as_gnomon_map_world(self):
        server = mcp_server.Server(self.brain)
        found = server.call("gnomon", {"action": "map", "view": "world"})
        self.assertFalse(found.is_error, found.text)
        self.assertIn("World view", found.text)
        self.assertIn('notes(action: "related"', found.text)


if __name__ == "__main__":
    unittest.main()
