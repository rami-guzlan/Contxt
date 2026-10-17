"""Lexical retrieval scales with matching postings without changing evidence."""
import random
import unittest
from collections import Counter

from brainkit.index import BM25


def reference(index, query, restrict=None):
    terms = index.query_terms(query) if isinstance(query, str) else list(query)
    out = {}
    keys = index.docs.keys() if restrict is None else [k for k in restrict if k in index.docs]
    for key in keys:
        score = 0.0
        counts = index.docs[key]
        length = index.lengths[key] or 1
        for term in terms:
            freq = counts.get(term)
            if freq:
                score += index.idf.get(term, 0.0) * freq * (index.k1 + 1) / (
                    freq + index.k1 * (1 - index.b + index.b * length / index.avg))
        if score > 0:
            out[key] = score
    return out


class LexicalPostingsTest(unittest.TestCase):
    def test_scores_keep_exact_arithmetic_and_caller_order(self):
        rng = random.Random(80317)
        words = ['sail', 'harbor', 'mast', 'wind', 'ocean', 'anchor', 'boat', 'rope']
        docs = {str(i): ' '.join(rng.choices(words, k=rng.randrange(0, 50))) for i in range(80)}
        docs['empty'] = ''
        for k1, b in ((1.2, .75), (.7, 0), (2.1, 1)):
            index = BM25(docs, k1=k1, b=b)
            queries = ['', 'unknown', 'the and', 'sails winds rope', ['rope', 'mast', 'rope']]
            queries += [' '.join(rng.choices(words, k=9)) for _ in range(12)]
            for query in queries:
                for restrict in (None, [], ['missing', 'empty', '8', '2', '8'], list(reversed(docs))):
                    with self.subTest(k1=k1, b=b, query=query, restrict=restrict is None):
                        self.assertEqual(list(index.scores(query, restrict).items()),
                                         list(reference(index, query, restrict).items()))

    def test_sparse_requests_do_not_probe_every_document_term(self):
        index = BM25({str(i): 'anchor rope' if i == 17 else 'harbor wind' for i in range(1000)})
        probes = []

        class Counted(Counter):
            def get(self, key, default=None):
                probes.append(key)
                return super().get(key, default)

        index.docs = {key: Counted(value) for key, value in index.docs.items()}
        self.assertEqual(set(index.scores('anchor rope')), {'17'})
        self.assertLessEqual(len(probes), 2)

    def test_bulk_coverage_matches_individual_coverage_including_unseen_terms(self):
        index = BM25({'a': 'anchor anchor rope', 'b': 'wind rope', 'c': '', 'd': 'harbor'},
                     unseen_idf=7.0)
        for query in ('anchor rope', 'anchor unknown', '', 'the and', 'ropes winds'):
            for restrict in (None, [], ['b', 'missing', 'a', 'b'], ['d', 'c']):
                with self.subTest(query=query, restrict=restrict):
                    keys = list(index.docs) if restrict is None else list(dict.fromkeys(restrict))
                    got = index.coverages(query, restrict)
                    self.assertEqual(got, {key: index.coverage(query, key) for key in keys})

    def test_a_new_snapshot_does_not_reuse_old_postings(self):
        first = BM25({'same': 'anchor rope'})
        second = BM25({'same': 'harbor wind'})
        self.assertTrue(first.scores('anchor'))
        self.assertEqual(second.scores('anchor'), {})
        self.assertEqual(second.coverages('anchor'), {'same': 0.0})

    def test_bulk_coverage_keeps_float_summation_on_long_varied_queries(self):
        rng = random.Random(2971)
        words = [chr(97+i//26)+chr(97+i%26)+"word" for i in range(80)]
        docs = {str(i): " ".join(rng.choices(words, k=rng.randrange(1, 150))) for i in range(100)}
        index = BM25(docs)
        for _ in range(30):
            query = " ".join(rng.sample(words, 40))
            self.assertEqual(index.coverages(query), {key: index.coverage(query, key) for key in docs})
