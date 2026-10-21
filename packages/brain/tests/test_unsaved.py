"""A change that is live but whose git commit failed says so in its reply, is recorded in the
journal, shows in gnomon_health, and is saved by the next change."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import gitops
from brainkit.api import Brain
from tests import fixture

FAILED = {"committed": False, "failed": True, "reason": "error: unable to index file: "
          "Filename too long"}


class UnsavedTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(git=True)
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["git"] = {"auto_commit": True}
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.brain = Brain(self.vault, embeddings=False)
        self.brain.write_kernel()
        gitops.commit(self.brain.repo_root, [path, os.path.join(self.brain.repo_root,
                                                                 "CLAUDE.md"),
                                             os.path.join(self.brain.repo_root, "AGENTS.md")],
                      "settings")

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def journal(self):
        with open(os.path.join(self.vault, "journal", "decisions.jsonl"), encoding="utf-8") as h:
            return [json.loads(line) for line in h if line.strip()]

    def test_a_failed_commit_is_reported_in_the_reply(self):
        with mock.patch.object(gitops, "commit", return_value=dict(FAILED)):
            made = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                      text="Give me the answer first, reasoning after.")
        self.assertEqual(made.data["status"], "applied", made.text)
        self.assertIn("saving it to the brain's git history failed", made.text)
        self.assertIn("Filename too long", made.text)
        self.assertEqual((made.data["saved"], made.data["commit_error"][:6]), (False, "error:"))
        record = self.journal()[-1]
        self.assertEqual(record["action"], "unsaved")
        self.assertIn("Filename too long", record["reason"])

    def test_health_warns_about_uncommitted_vault_changes_until_the_next_change(self):
        with mock.patch.object(gitops, "commit", return_value=dict(FAILED)):
            self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                               text="Give me the answer first, reasoning after.")
        self.assertTrue(self.brain.unsaved())
        warnings = self.brain.health().data["warnings"]
        self.assertTrue(any("not saved to git" in w for w in warnings), warnings)
        again = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                   text="Use short sentences.")
        self.assertNotIn("git history failed", again.text)
        self.assertEqual(self.brain.unsaved(), [])
        self.assertFalse(any("not saved to git" in w
                             for w in self.brain.health().data["warnings"]))

    def test_nothing_to_save_is_not_a_failure(self):
        with mock.patch.object(gitops, "commit",
                               return_value={"committed": False, "reason": "nothing to commit"}):
            made = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                      text="Give me the answer first, reasoning after.")
        self.assertNotIn("git history failed", made.text)
        self.assertNotIn("saved", made.data)

    def test_git_runs_with_long_paths_on_windows(self):
        if os.name == "nt":
            self.assertEqual(gitops.GIT[:3], ("git", "-c", "core.longpaths=true"))
        else:
            self.assertEqual(gitops.GIT, ("git",))


if __name__ == "__main__":
    unittest.main()
