"""A large Brain carries only its best candidates past scoring: the same packets, faster."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import router
from brainkit.api import Brain
from tests import fixture

REQUESTS = (
    "How long do web design projects run from kickoff to launch?",
    "Write a LinkedIn post about our new service",
    "What is our pricing for retainers?",
    "Draft a proposal for a bakery website redesign",
)


class RankLimitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build()
        cls.brain = Brain(cls.vault, embeddings=False)

    @classmethod
    def tearDownClass(cls):
        cls.brain.close()
        fixture.remove(cls.vault)

    def packet(self, request):
        data = self.brain.context(request, record=False).data
        return data["note_ids"], data.get("related_ids") or data.get("pointers")

    def test_the_best_candidates_alone_give_the_same_packets(self):
        whole = {r: self.packet(r) for r in REQUESTS}
        kept = router.RANK_LIMIT
        router.RANK_LIMIT = 3
        try:
            for request in REQUESTS:
                self.assertEqual(self.packet(request), whole[request], request)
            st = self.brain.state()
            chain, partitions = self.brain.caller(None, None, None, st=st)
            route = st.router.route(REQUESTS[1], chain, partitions)
            self.assertTrue(any(line.startswith("ranked the best 3 of ")
                                for line in route.notes_log), route.notes_log)
        finally:
            router.RANK_LIMIT = kept


if __name__ == "__main__":
    unittest.main()
