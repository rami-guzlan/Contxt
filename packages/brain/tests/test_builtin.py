"""Built-in skills: listed, copied into a new brain, and added to an older one as one undo
point without overwriting a skill of the same name."""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import builtin
from brainkit.api import Brain
from tests import fixture

NAMES = ["goals-interview", "knowledge-check", "pull-what-matters", "teach", "wrap-up"]


class BuiltinTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_every_built_in_skill_parses_and_names_no_one(self):
        found = builtin.available()
        self.assertEqual(sorted(s["name"] for s in found), NAMES)
        for skill in found:
            with open(os.path.join(skill["folder"], "SKILL.md"), encoding="utf-8") as handle:
                text = handle.read()
            self.assertTrue(skill["description"], skill["name"])
            self.assertNotIn(chr(0x2014), text)  # no em dashes
            self.assertNotIn(chr(0x2013), text)  # no en dashes
            for line in text.split("---", 2)[2].splitlines():
                # no spaced hyphen standing in for a dash (a list's own marker is fine)
                self.assertNotIn(" - ", re.sub(r"^\s*[-*]\s+", "", line), line)

    def test_an_older_brain_gets_the_missing_ones_as_one_undo_point(self):
        listed = self.brain.builtin_skills().data
        self.assertEqual(sorted(listed["missing"]), NAMES)
        added = self.brain.add_builtin_skills(actor="person:alex")
        self.assertFalse(added.is_error, added.text)
        self.assertEqual(sorted(added.data["added"]), NAMES)
        skills = self.brain.state().index.skills
        self.assertEqual(skills["knowledge-check"].category, "brain")
        self.assertFalse(self.brain.builtin_skills().data["missing"])
        again = self.brain.add_builtin_skills(actor="person:alex")
        self.assertEqual(again.data["added"], [])
        self.brain.undo(added.data["checkpoint"]["id"], actor="person:alex")
        self.assertNotIn("knowledge-check", self.brain.state().index.skills)

    def test_only_the_owner_adds_them(self):
        refused = self.brain.add_builtin_skills(actor="person:sam")
        self.assertTrue(refused.is_error)

    def test_a_new_vault_gets_copies_and_keeps_its_own(self):
        vault = tempfile.mkdtemp(prefix="builtin-")
        own = os.path.join(vault, "skills", "brain", "teach")
        os.makedirs(own)
        with open(os.path.join(own, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write("---\nname: teach\n---\n# Mine\n")
        copied = builtin.copy_into(vault)
        self.assertEqual(sorted(copied), [n for n in NAMES if n != "teach"])
        with open(os.path.join(own, "SKILL.md"), encoding="utf-8") as handle:
            self.assertIn("# Mine", handle.read())
        fixture.remove(vault)


if __name__ == "__main__":
    unittest.main()
