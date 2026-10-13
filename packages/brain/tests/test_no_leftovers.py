"""Nothing of a person's Brain stays behind in the temp folder.

Evals, replays and benches rebuild briefs from the person's own Brain into throwaway ledgers
and scratch copies: the requests, the briefs and the notes they carried. Each is removed when
the run ends, so a Brain's content never lingers on the system drive.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import bench, evaluate, replay  # noqa: E402
from brainkit import safeguards_eval as se  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import test_layout  # noqa: E402

REPO = os.path.dirname(os.path.dirname(ROOT))
BRAINS = os.path.join(REPO, "brains")
EVALS = os.path.join(ROOT, "tests", "evals")
CAKE = "How much notice does a celebration cake need?"


class LeftoverTests(unittest.TestCase):
    def setUp(self):
        self.vault = test_layout.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.temp = tempfile.mkdtemp(prefix="leftover-check-")
        self.patch = mock.patch.object(tempfile, "tempdir", self.temp)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)
        shutil.rmtree(self.temp, ignore_errors=True)

    def left(self) -> list[str]:
        return sorted(os.listdir(self.temp))

    def spec(self, cases) -> str:
        path = os.path.join(os.path.dirname(self.vault), "spec.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(cases, handle)
        return path

    def test_a_replay_leaves_nothing_behind(self):
        packet = self.brain.context(CAKE, principal="person:ana").data["packet_id"]
        proposed = self.brain.propose(area="company", topic="menu", title="Cake notice in June",
                                      text="In June, celebration cakes need ten days of notice "
                                           "because of weddings.", principal="person:ana",
                                      evidence="Ana said so", note_kind="fact")
        found = replay.replay(self.brain, packet, proposal=proposed.data["proposal_id"])
        self.assertEqual(found["replayed"], 1)
        self.assertEqual(self.left(), [])

    def test_an_eval_on_the_brain_leaves_nothing_behind(self):
        path = self.spec({"cases": [{"id": "cake", "request": CAKE, "user": "person:ana",
                                     "must": []}]})
        evaluate.run(self.brain, path)
        self.assertEqual(self.left(), [])

    def test_a_bench_leaves_nothing_behind(self):
        bench.run(self.brain, self.spec({"cases": []}))
        self.assertEqual(self.left(), [])

    def test_the_demo_evals_leave_nothing_behind(self):
        with open(os.path.join(EVALS, "retrieval.json"), encoding="utf-8") as handle:
            spec = json.load(handle)
        spec["cases"] = spec["cases"][:1]
        se.run_retrieval(BRAINS, spec)
        self.assertEqual(self.left(), [])


if __name__ == "__main__":
    unittest.main()
