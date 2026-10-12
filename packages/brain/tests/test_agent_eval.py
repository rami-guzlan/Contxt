"""The knowledge agent's labeled set runs through the code-run loop and scores its bars
(brain-logic plan 17.9); the stand-in oracle checks the harness itself."""
from __future__ import annotations

import os
import unittest

from brainkit import agent_eval

HERE = os.path.dirname(os.path.abspath(__file__))
BRAINS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "brains")


class AgentSetTest(unittest.TestCase):
    def test_every_action_has_labeled_cases(self):
        cases = agent_eval.load(BRAINS)
        actions = {c["action"] for c in cases}
        self.assertEqual(actions, set(agent_eval.VERDICTS))
        for case in cases:
            for allowed in case["expect"].values():
                self.assertTrue(set(allowed) <= set(agent_eval.VERDICTS[case["action"]]),
                                case["id"])

    def test_the_oracle_clears_every_bar(self):
        cases = [c for c in agent_eval.load(BRAINS) if c["id"] in ("repeats-1", "drift-1",
                                                                     "verify-1")]
        rows = [agent_eval.run_case(BRAINS, case, "oracle") for case in cases]
        found = agent_eval.score(rows)
        self.assertEqual((found["agreement"], found["valid"]), (1.0, 1.0))
        self.assertTrue(found["no_writes"] and found["impacts_match"])
        self.assertEqual(found["hand_ups"], 0)


if __name__ == "__main__":
    unittest.main()
