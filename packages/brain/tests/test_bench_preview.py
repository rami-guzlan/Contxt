"""The Test Bench preview (Release 1 plan, 15.2 and 15.3): the packet by its own sections,
each item with why it was chosen and its tokens; and include or exclude that take parts out
without filling the gap with something else."""
from __future__ import annotations

import unittest

from brainkit.api import Brain
from tests import fixture

REQUEST = "Draft the case study for the website redesign"


class BenchPreviewTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_the_preview_lists_the_packets_sections_with_reasons_and_tokens(self):
        found = self.brain.preview(REQUEST).data
        names = [s["name"] for s in found["packet_sections"]]
        self.assertTrue(names)
        self.assertEqual(len(names), len(set(names)))
        for section in found["packet_sections"]:
            self.assertEqual(section["tokens"], sum(i["tokens"] for i in section["items"]))
            for item in section["items"]:
                self.assertTrue(item["id"] and item["why"], item)
        shown_map = sum(s["tokens"] for s in found["packet_sections"] if s["name"] == "map")
        self.assertEqual(found["packet_tokens"], found["token_count"] + shown_map)
        self.assertIn("brain_version", found)

    def notes(self, found):
        section = next(s for s in found["packet_sections"] if s["name"] == "notes")
        return [i["id"] for i in section["items"]]

    def test_an_excluded_note_is_not_replaced_by_another(self):
        full = self.brain.preview(REQUEST).data
        notes = self.notes(full)
        self.assertTrue(notes)
        trimmed = self.brain.preview(REQUEST, exclude={"ids": [notes[0]]}).data
        self.assertNotIn(notes[0], trimmed["note_ids"])
        self.assertTrue(set(trimmed["note_ids"]) <= set(full["note_ids"]))
        self.assertTrue(set(trimmed["related_ids"]) <= set(full["related_ids"]))

    def test_an_excluded_section_is_left_out_whole(self):
        full = self.brain.preview(REQUEST).data
        kept = [s["name"] for s in full["packet_sections"]]
        gone = self.brain.preview(REQUEST, exclude={"sections": [kept[0]]}).data
        self.assertNotIn(kept[0], [s["name"] for s in gone["packet_sections"]])

    def test_include_keeps_exactly_what_was_checked(self):
        full = self.brain.preview(REQUEST).data
        note = self.notes(full)[0]
        only = self.brain.preview(REQUEST, include={"sections": ["notes"], "ids": [note]}).data
        self.assertEqual(only["note_ids"], [note])
        self.assertEqual([s["name"] for s in only["packet_sections"]], ["notes"])


if __name__ == "__main__":
    unittest.main()
