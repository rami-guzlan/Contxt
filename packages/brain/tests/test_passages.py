"""A long note is matched passage by passage, so a fact deep in it can be found."""
from __future__ import annotations

import os
import shutil
import unittest
from types import SimpleNamespace

from brainkit import index
from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
FILLER = ("We talked through the week's errands, the weather and the garden at length. " * 4)


def _note(body):
    return SimpleNamespace(body=body)


class SplitTest(unittest.TestCase):
    def test_a_short_note_is_one_passage_its_own_vector_reads(self):
        self.assertEqual(index.note_passages(_note("A short note.")), [])

    def test_a_long_note_splits_on_paragraphs_and_keeps_every_word_in_order(self):
        body = "\n\n".join(f"Paragraph {i}. {FILLER}" for i in range(8))
        passages = index.note_passages(_note(body))
        self.assertGreater(len(passages), 1)
        self.assertTrue(all(len(p) <= index.PASSAGE_CHARS for p in passages))
        self.assertEqual(" ".join(" ".join(passages).split()), " ".join(body.split()))

    def test_one_very_long_paragraph_is_cut_on_sentences(self):
        passages = index.note_passages(_note(FILLER * 6))
        self.assertTrue(all(len(p) <= index.PASSAGE_CHARS for p in passages))
        self.assertTrue(all(p.endswith(".") for p in passages[:-1]))


@unittest.skipUnless(os.path.isdir(MODELS or "-"), "needs BRAIN_TEST_MODELS with bge-small")
class MeaningTest(unittest.TestCase):
    def test_a_fact_deep_in_a_long_note_is_found_by_its_passage(self):
        vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"), MODELS)
        try:
            body = "\n\n".join([FILLER] * 12 + [
                "user:\nMy whippet Juno pulls on the leash every morning walk."])
            se.add_notes(vault, [{"id": "long-chat", "title": "A long chat", "area": "me",
                                  "topic": "chats", "summary": "A chat about the week.",
                                  "body": body}])
            def score():
                brain = se.open_brain(vault, semantic=True)
                try:
                    return brain.state().index.similarity("What breed is my dog?")[
                        "note:long-chat"]
                finally:
                    brain.close()

            with_passages = score()
            saved, index.PASSAGE_FROM = index.PASSAGE_FROM, 10 ** 9
            try:
                without = score()
            finally:
                index.PASSAGE_FROM = saved
            self.assertGreater(with_passages, without + 0.05)
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
