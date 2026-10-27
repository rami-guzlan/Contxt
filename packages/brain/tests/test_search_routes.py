"""A second way to search (v4 backend plan, 16.2): routes that miss differently from the
packet's matching, fused, each hit saying which routes found it."""
from __future__ import annotations

import unittest

from brainkit import safeguards_eval as se
from brainkit.api import Brain
from tests import fixture


class SearchRoutesTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = None

    def tearDown(self):
        if self.brain is not None:
            self.brain.close()
        fixture.remove(self.vault)

    def open(self):
        self.brain = Brain(self.vault, embeddings=False)
        return self.brain

    def found(self, query, **kwargs):
        return {h["id"]: h["found_by"] for h in self.brain.search(query, **kwargs).data["hits"]}

    def test_the_graph_route_finds_a_linked_note_the_words_miss(self):
        se.set_meta(self.vault, ["rules-design-001"], relates=["explains: facts-services-002"])
        self.open()
        words = {s.item.id for s in self.brain.state().router.score_notes(
            "How long do web projects take?", list(self.brain.state().index.notes.values()))
            if s.score > 0.05}
        self.assertNotIn("rules-design-001", words)
        found = self.found("How long do web projects take?")
        self.assertIn("related", found.get("rules-design-001", []))

    def test_a_rephrase_is_searched_beside_the_query(self):
        self.open()
        self.assertNotIn("facts-services-002", self.found("zzqx"))
        found = self.found("zzqx", rephrase="how long web projects take")
        self.assertIn("your rephrase", found.get("facts-services-002", []))

    def test_a_title_word_finds_its_note_and_says_so(self):
        self.open()
        note = self.brain.state().index.notes["state-focus-studio-podcast"]
        found = self.found(note.title)
        self.assertIn("title or heading", found.get(note.id, []))
        text = self.brain.search(note.title).text
        self.assertIn("notes_get", text)

    def test_only_what_the_caller_may_see(self):
        self.open()
        self.assertNotIn("facts-clients-acme-001", self.found("Acme"))  # sealed


if __name__ == "__main__":
    unittest.main()
