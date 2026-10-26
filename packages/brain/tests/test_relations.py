"""Relationships between entries (v4 backend plan, 13.2): edges derived from fields the Brain
already stores (supersedes, belongs to, pinned in, cites, mentions) and an entry's own
`relates` list (explains, depends on, example of, instead of); kept in the Brain's SQLite file
and rebuilt with the index; read with `notes(action: "related")`, scope-filtered, a sealed
entry left out with no count; at most two steps out."""
from __future__ import annotations

import os
import unittest

from brainkit import mcp_server, relations
from brainkit.api import Brain
from tests import fixture

NEW = """---
id: facts-pricing-2026
layer: facts
topic: services
scope: company
status: approved
load: on-demand
summary: Web design pricing for 2026.
supersedes: facts-services-001
project: Website Redesign
relates:
  - "explains: rules-style-003"
  - "gets along with: rules-style-001"
---

Web design projects for 2026 start at a fixed fee, as discussed on the Studio Podcast.
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
---

Acme pays a negotiated rate for the Website Redesign work.
"""


class RelationsTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        folder = os.path.join(self.vault, "knowledge", "facts", "services")
        os.makedirs(folder, exist_ok=True)
        for name, text in (("facts-pricing-2026.md", NEW), ("facts-acme-rates.md", SEALED)):
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def edges(self, note_id, **kw):
        found = self.brain.related(note_id, **kw)
        self.assertFalse(found.is_error, found.text)
        return {(e["type"], e["id"], e["direction"]) for e in found.data["edges"]}

    def test_edges_come_from_fields_the_brain_already_stores(self):
        found = self.edges("facts-pricing-2026")
        self.assertIn(("supersedes", "facts-services-001", "out"), found)
        self.assertIn(("belongs to", "state-focus-website-redesign", "out"), found)
        self.assertIn(("mentions", "state-focus-studio-podcast", "out"), found)
        self.assertIn(("explains", "rules-style-003", "out"), found)
        style = self.edges("rules-style-003")
        self.assertIn(("cites", "references/style-guide.md", "out"), style)
        self.assertIn(("explains", "facts-pricing-2026", "in"), style)

    def test_only_the_four_explicit_types_are_kept(self):
        kinds = {t for t, _, _ in self.edges("facts-pricing-2026")}
        self.assertNotIn("gets along with", kinds)
        self.assertLessEqual(kinds, set(relations.TYPES))

    def test_a_sealed_entry_is_left_out_with_no_count(self):
        project = self.brain.related("state-focus-website-redesign")
        ids = {e["id"] for e in project.data["edges"]}
        self.assertIn("facts-pricing-2026", ids)
        self.assertNotIn("facts-acme-rates", ids)
        self.assertNotIn("acme", project.text.lower())
        hidden = self.brain.related("facts-acme-rates")
        self.assertTrue(hidden.is_error)

    def test_types_filter_and_two_steps_at_most(self):
        only = self.edges("facts-pricing-2026", types=["supersedes"])
        self.assertEqual({t for t, _, _ in only}, {"supersedes"})
        far = self.brain.related("rules-style-003", depth=5).data["edges"]
        self.assertEqual(max(e["depth"] for e in far), 2)
        self.assertTrue(any(e["depth"] == 2 and e["id"] == "state-focus-website-redesign"
                            for e in far))

    def test_the_index_is_rebuilt_when_the_vault_changes(self):
        self.assertNotIn("mentions", {t for t, _, _ in self.edges("rules-style-002")})
        path = next(os.path.join(r, n) for r, _, files in os.walk(self.vault) for n in files
                    if n.startswith("rules-style-002"))
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\nThe Studio Podcast uses these headlines too.\n")
        self.brain.vault.touch(path)
        self.assertIn(("mentions", "state-focus-studio-podcast", "out"),
                      self.edges("rules-style-002"))

    def test_agents_read_it_as_notes_related(self):
        server = mcp_server.Server(self.brain)
        found = server.call("notes", {"action": "related", "id": "facts-pricing-2026"})
        self.assertFalse(found.is_error, found.text)
        self.assertIn("supersedes: `facts-services-001`", found.text)
        self.assertIn('notes(action: "get"', found.text)


if __name__ == "__main__":
    unittest.main()
