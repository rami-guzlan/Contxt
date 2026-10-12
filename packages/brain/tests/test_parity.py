"""Without a verified model service the engine is off, and retrieval runs exactly as it did
before the local engine was built: every eval request's brief is the same, byte for byte, as
the copy kept in evals/parity_briefs.json (scripts/parity_briefs.py writes and compares it).
"""
import importlib.util
import os
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(ROOT))
SCRIPT = os.path.join(REPO, "scripts", "parity_briefs.py")


def load_script():
    spec = importlib.util.spec_from_file_location("parity_briefs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.path.isfile(SCRIPT), "needs the repository's scripts folder")
class ParityTest(unittest.TestCase):
    def test_briefs_are_the_same_as_before_the_engine(self):
        parity = load_script()
        with open(parity.KEPT, encoding="utf-8") as handle:
            kept = __import__("json").load(handle)["briefs"]
        # No model service: the engine stays off whatever this machine runs.
        with mock.patch.dict(os.environ, {"BRAIN_MODEL_SERVICE": "off"}):
            now = parity.briefs()
        problems = parity.compare(now, kept)
        self.assertEqual(problems, [], "\n\n".join(problems[:5]))
        self.assertGreater(len(now), 150)


if __name__ == "__main__":
    unittest.main()
