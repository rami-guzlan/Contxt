"""Two rules a Contxt home relies on: a Brain that declares its areas has exactly those, and
the Brain commits only into a git repository of its own, never into one it sits inside."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from brainkit import config, gitops  # noqa: E402

PERSONAL = {
    "schema": 1,
    "name": "A personal Brain",
    "owner": "person:pat",
    "structure": {
        "areas": {
            "me": {"label": "Me", "order": 1},
            "family": {"label": "Family", "order": 2},
            "projects": {"label": "Projects", "order": 3},
            "topics": {"label": "Topics", "order": 4},
        },
    },
    "scopes": {"company": {"label": "Household"}, "person:pat": {"parent": "company"}},
}


def git(folder, *args):
    subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True,
                   stdin=subprocess.DEVNULL)


class AreasTests(unittest.TestCase):
    def setUp(self):
        self.vault = tempfile.mkdtemp(prefix="brain-areas-")

    def tearDown(self):
        shutil.rmtree(self.vault, ignore_errors=True)

    def write(self, data):
        with open(os.path.join(self.vault, "brain.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def test_declared_areas_replace_the_default_set(self):
        self.write(PERSONAL)
        self.assertEqual(sorted(config.load(self.vault).areas),
                         ["family", "me", "projects", "topics"])

    def test_a_brain_that_declares_none_gets_the_default_set(self):
        self.write({"schema": 1, "name": "Defaults"})
        areas = config.load(self.vault).areas
        self.assertIn("marketing", areas)
        self.assertIn("topics", areas)


class OwnRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.outer = tempfile.mkdtemp(prefix="brain-outer-")
        git(self.outer, "init", "-q", "-b", "main")
        git(self.outer, "-c", "user.name=Test", "-c", "user.email=t@example.com",
            "commit", "-q", "--allow-empty", "-m", "the application")
        self.brain = os.path.join(self.outer, "brain")
        os.makedirs(os.path.join(self.brain, "vault"))
        with open(os.path.join(self.brain, "vault", "note.md"), "w", encoding="utf-8") as h:
            h.write("A private note.\n")

    def tearDown(self):
        shutil.rmtree(self.outer, ignore_errors=True)

    def head(self, folder):
        return subprocess.run(["git", "log", "--format=%s"], cwd=folder, capture_output=True,
                              text=True).stdout.splitlines()

    def test_a_brain_inside_another_repository_commits_nothing_there(self):
        self.assertFalse(gitops.owns_repo(self.brain))
        result = gitops.commit(self.brain, ["vault/note.md"], "Brain: a private note")
        self.assertFalse(result["committed"])
        self.assertIn("not its own", result["reason"])
        self.assertEqual(self.head(self.outer), ["the application"])

    def test_a_brain_inside_another_repository_reads_no_history_from_it(self):
        self.assertIsNotNone(gitops.locate(os.path.join(self.brain, "vault")))
        self.assertIsNone(gitops.locate_own(os.path.join(self.brain, "vault"), self.brain))
        git(self.brain, "init", "-q", "-b", "main")
        found = gitops.locate_own(os.path.join(self.brain, "vault"), self.brain)
        self.assertEqual(found[1], "vault/")

    def test_a_brain_with_its_own_repository_commits_there(self):
        git(self.brain, "init", "-q", "-b", "main")
        self.assertTrue(gitops.owns_repo(self.brain))
        result = gitops.commit(self.brain, ["vault/note.md"], "Brain: a private note")
        self.assertTrue(result["committed"], result)
        self.assertEqual(self.head(self.brain), ["Brain: a private note"])
        self.assertEqual(self.head(self.outer), ["the application"])


if __name__ == "__main__":
    unittest.main()
