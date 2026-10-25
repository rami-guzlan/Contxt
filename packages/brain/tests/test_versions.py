"""Brain versions (Release 1 plan, 15.1): a version is a git tag `gnomon/v<N>` in the
Brain's own repository with its cause and counts; versions diff entry by entry; a restore
is a new commit and a new version, refused when an entry changed since the last version;
every packet names the version it was built from."""
from __future__ import annotations

import os
import subprocess
import unittest

from brainkit import versions
from brainkit.api import Brain
from tests import fixture


def _commit(base, message):
    subprocess.run(["git", "add", "-A"], cwd=base, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-q", "-m", message], cwd=base, check=True, capture_output=True)


class VersionTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(git=True)
        self.base = os.path.dirname(self.vault)
        self.brain = Brain(self.vault, embeddings=False)
        note = next(iter(self.brain.state().index.notes.values()))
        self.note_id, self.path = note.id, os.path.join(self.vault, note.path)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def rewrite(self, old, new):
        with open(self.path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn(old, text)
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(text.replace(old, new))

    def first_words(self):
        body = self.brain.state().index.note(self.note_id).body.strip()
        return body.split()[0]

    def test_a_version_is_a_tag_with_its_cause_and_counts(self):
        made = versions.tag(self.brain, cause="manual")
        self.assertFalse(made.is_error, made.text)
        self.assertEqual(made.data["version"]["name"], "v1")
        self.assertEqual(made.data["version"]["cause"], "manual")
        listed = versions.list_versions(self.brain)
        self.assertEqual([v["name"] for v in listed], ["v1"])
        tags = subprocess.run(["git", "tag", "--list", "gnomon/*"], cwd=self.base,
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(tags, ["gnomon/v1"])

    def test_the_label_says_how_many_writes_since_the_last_version(self):
        versions.tag(self.brain, cause="manual")
        self.assertEqual(versions.label(self.brain), "v1")
        self.rewrite(self.first_words(), "Changed")
        _commit(self.base, "a later write")
        self.assertEqual(versions.label(self.brain), "v1+1")

    def test_a_diff_lists_the_entries_changed_with_old_and_new_text(self):
        versions.tag(self.brain, cause="manual")
        word = self.first_words()
        self.rewrite(word, "Changed")
        made = versions.tag(self.brain, cause="distill")
        self.assertEqual(made.data["version"]["changed"], 1)
        found = versions.diff(self.brain, "v1", "v2")
        (entry,) = found["changed"]
        self.assertEqual(entry["id"], self.note_id)
        self.assertIn(word, entry["old"])
        self.assertIn("Changed", entry["new"])
        self.assertEqual(found["added"], [])
        self.assertEqual(found["removed"], [])

    def test_a_restore_is_a_new_version_and_refuses_after_a_later_change(self):
        versions.tag(self.brain, cause="manual")
        word = self.first_words()
        self.rewrite(word, "Changed")
        versions.tag(self.brain, cause="distill")
        self.rewrite("Changed", "Again")
        refused = versions.restore(self.brain, "v1", ids=[self.note_id])
        self.assertTrue(refused.is_error)
        self.assertIn(self.note_id, refused.data.get("changed_since", []))
        self.rewrite("Again", "Changed")
        done = versions.restore(self.brain, "v1", ids=[self.note_id])
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(done.data["version"]["cause"], "restore")
        self.assertEqual(done.data["version"]["name"], "v3")
        self.assertEqual(self.first_words(), word)

    def test_every_packet_names_the_brain_version(self):
        versions.tag(self.brain, cause="manual")
        data = self.brain.context("website redesign", record=False).data
        self.assertEqual(data.get("brain_version"), "v1")

    def test_a_receipt_names_the_brain_version_it_was_built_from(self):
        from brainkit import receipts
        versions.tag(self.brain, cause="manual")
        packet = self.brain.context("website redesign").data["packet_id"]
        self.assertEqual(receipts.build(self.brain, packet)["brain_version"], "v1")


if __name__ == "__main__":
    unittest.main()
