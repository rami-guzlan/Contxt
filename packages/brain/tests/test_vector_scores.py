"""Cosine ranking stays exact while normalization work scales with the snapshot."""
import math
import random
import unittest
from types import SimpleNamespace
from unittest import mock

from brainkit.index import Index, cosine


def index_with(vectors):
    snapshot = SimpleNamespace(notes={}, skills={}, references={}, focus_updates={})
    config = SimpleNamespace(routing=SimpleNamespace(phrases=[]), topics={})
    index = Index(snapshot, config)
    index._vectors = vectors
    return index


def reference(vectors, query):
    out, asks = {}, {}
    for key, vector in vectors.items():
        value = cosine(query, vector)
        if key.startswith("ask:"):
            note = "note:" + key[4:].rsplit(":", 1)[0]
            asks[note] = max(asks.get(note, -1.0), value)
        else:
            out[key] = value
    for key, value in asks.items():
        if key in out and value > out[key]:
            out[key] = value
    return out


class VectorScoreTest(unittest.TestCase):
    def test_scores_and_question_folding_match_pairwise_cosine_exactly(self):
        rng = random.Random(834)
        vectors = {f"note:{i}": [rng.uniform(-2, 2) for _ in range(384)]
                   for i in range(12)}
        vectors.update({"ask:0:0": [-3.0] * 384, "ask:0:1": [4.0] * 384,
                        "ask:missing:0": [1.0] * 384, "topic:short": [1.0, 2.0],
                        "section:zero": [0.0] * 384, "domain:empty": []})
        index = index_with(vectors)
        queries = [[], [0.0] * 384, [1.0, 2.0], [-1.0] * 384]
        queries += [[rng.uniform(-4, 4) for _ in range(384)] for _ in range(8)]
        for query in queries:
            with self.subTest(dimensions=len(query)):
                self.assertEqual(index.similarity_vector(query), reference(vectors, query))

    def test_scoring_many_requests_does_not_repeat_stored_vector_normalization(self):
        vectors = {f"note:{i}": [float(i + 1), 2.0, -3.0] for i in range(16)}
        queries = [[1.0, float(i), 4.0] for i in range(8)]
        index = index_with(vectors)
        with mock.patch("brainkit.index.math.sumprod", wraps=math.sumprod) as dot:
            for query in queries:
                index.similarity_vector(query)
        normalizations = sum(a is b for (a, b), _ in dot.call_args_list)
        self.assertLessEqual(normalizations, len(vectors) + len(queries))

    def test_a_new_snapshot_uses_its_own_vector_lengths(self):
        query = [1.0, 0.0]
        first = index_with({"note:same": [3.0, 4.0]})
        second = index_with({"note:same": [8.0, -2.0]})
        self.assertEqual(first.similarity_vector(query)["note:same"], cosine(query, [3.0, 4.0]))
        self.assertEqual(second.similarity_vector(query)["note:same"], cosine(query, [8.0, -2.0]))
        self.assertNotEqual(first.similarity_vector(query), second.similarity_vector(query))
