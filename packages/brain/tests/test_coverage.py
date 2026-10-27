"""The packet says what it doesn't cover (v4 backend plan, 16.1): a request's distinctive words
that no item in the packet holds, where each likely is, and the call that fetches it; at most
three lines, and none when everything is covered."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from brainkit import coverage
from brainkit.api import Brain
from brainkit.index import BM25
from tests import fixture

DOCS = {
    "refunds": "Refund window. Refunds are given within 30 days of the order.",
    "kickoff": "## Kickoff checklist\nBefore the call: agenda, owners, refund terms.",
    "hours": "Opening hours are nine to five on weekdays.",
    "parking": "Parking is behind the building.",
    "wifi": "The guest wifi password changes monthly.",
    "team": "The team meets on Mondays.",
}


def _index():
    notes = {k: SimpleNamespace(id=k, body=v) for k, v in DOCS.items()}
    return SimpleNamespace(note_bm25=BM25(DOCS), notes=notes)


class BlockTest(unittest.TestCase):
    def test_an_uncovered_word_names_where_it_likely_is_and_the_fetch(self):
        text, found = coverage.block(_index(), "Refund window for the kickoff checklist",
                                     delivered={"refunds"}, admitted=set(DOCS))
        self.assertIn("refund", " ".join(found["covered"]))
        row = found["not_covered"][0]
        self.assertEqual(row["words"], ["kickoff"])  # "checklist" is only in a heading
        self.assertEqual(row["likely"], "kickoff#Kickoff checklist")
        self.assertEqual(row["fetch"], 'notes(action: "get", id: "kickoff")')
        self.assertIn('notes(action: "get", id: "kickoff")', text)

    def test_left_out_when_everything_is_covered(self):
        text, found = coverage.block(_index(), "What is the refund window?",
                                     delivered={"refunds"}, admitted=set(DOCS))
        self.assertEqual((text, found["not_covered"]), ("", []))

    def test_a_note_the_caller_may_not_see_is_never_named(self):
        _text, found = coverage.block(_index(), "Refund window for the kickoff checklist",
                                      delivered={"refunds"}, admitted=set(DOCS) - {"kickoff"})
        self.assertEqual(found["not_covered"], [])

    def test_a_question_about_when_gets_the_timeline(self):
        _text, found = coverage.block(_index(), "What changed in refunds since 2026-10-01?",
                                      delivered={"refunds"}, admitted=set(DOCS))
        self.assertEqual([r["fetch"] for r in found["not_covered"]],
                         ['activity(action: "timeline", since: "2026-10-01")'])

    def test_a_stray_word_is_not_a_gap(self):
        _text, found = coverage.block(_index(), "What is the refund window on weekdays?",
                                      delivered={"refunds"}, admitted=set(DOCS))
        self.assertEqual(found["not_covered"], [])  # "weekdays" labels no note

    def test_a_name_is_a_gap(self):
        _text, found = coverage.block(_index(), "Is the refund window the same for Mondays?",
                                      delivered={"refunds"}, admitted=set(DOCS))
        self.assertEqual([r["likely"] for r in found["not_covered"]], ["team"])

    def test_runners_up_point_where_a_missing_word_is_not_a_label(self):
        _text, found = coverage.block(_index(), "Refund window and the agenda owners",
                                      delivered={"refunds"}, admitted=set(DOCS),
                                      runners=["refunds", "kickoff", "hours"])
        self.assertEqual([r["likely"] for r in found["not_covered"]], ["kickoff", "hours"])
        self.assertEqual(found["not_covered"][0]["words"][:1], ["agenda"])

    def test_no_runners_up_when_every_word_is_covered(self):
        _text, found = coverage.block(_index(), "What is the refund window?",
                                      delivered={"refunds"}, admitted=set(DOCS),
                                      runners=["kickoff", "hours"])
        self.assertEqual(found["not_covered"], [])

    def test_at_most_three_lines(self):
        many = {f"word{i}": f"word{i} alpha" for i in range(30)} | {"base": "alpha"}
        index = SimpleNamespace(note_bm25=BM25(many),
                                notes={k: SimpleNamespace(id=k, body=v) for k, v in many.items()})
        request = "alpha " + " ".join(f"word{i}" for i in range(6))
        text, found = coverage.block(index, request, delivered={"base"}, admitted=set(many))
        self.assertLessEqual(len(found["not_covered"]), coverage.LINES)
        self.assertLessEqual(sum(line.startswith("- ") for line in text.splitlines()), 3)


class PacketTest(unittest.TestCase):
    def test_each_fetch_the_packet_names_works_and_holds_the_word(self):
        vault = fixture.build()
        brain = Brain(vault, embeddings=False)
        try:
            found = brain.context("How long do web projects take?", record=False)
            rows = found.data["coverage"]["not_covered"]
            self.assertTrue(rows)
            self.assertIn("## Not covered here", found.text)
            for row in rows:
                note_id = row["likely"].split("#", 1)[0]
                opened = brain.note(note_id)
                self.assertFalse(opened.is_error, opened.text)
                if row["words"] != ["close match"]:
                    self.assertTrue(any(w in opened.text.lower() for w in row["words"]))
        finally:
            brain.close()
            fixture.remove(vault)


if __name__ == "__main__":
    unittest.main()
