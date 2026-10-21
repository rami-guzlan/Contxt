"""Retrieval strictness is a named policy over the calibrated bars, not a raw threshold
(Release 1 plan, M05; design contract 15)."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import safeguards_eval as se

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))


class NamedPolicyTest(unittest.TestCase):
    def bars(self, policy):
        vault = se.copy_vault(os.path.join(ROOT, "brains", "empty", "vault"))
        try:
            if policy is not None:
                path = os.path.join(vault, "brain.json")
                with open(path, encoding="utf-8") as handle:
                    config = json.load(handle)
                config["retrieval_policy"] = policy
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump(config, handle)
            brain = se.open_brain(vault)
            try:
                router = brain.state().router
                return {bar: router.share(bar) for bar in ("nothing", "note", "related")}
            finally:
                brain.close()
        finally:
            shutil.rmtree(os.path.dirname(vault), ignore_errors=True)

    def test_careful_raises_the_bars_relaxed_lowers_them_and_standard_keeps_them(self):
        standard, careful, relaxed = self.bars(None), self.bars("careful"), self.bars("relaxed")
        self.assertEqual(self.bars("standard"), standard)
        self.assertEqual(self.bars("no-such-policy"), standard)
        for bar in standard:
            self.assertGreater(careful[bar], standard[bar])
            self.assertLess(relaxed[bar], standard[bar])


if __name__ == "__main__":
    unittest.main()
