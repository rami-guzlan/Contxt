"""The knowledge agent's tools (brain-logic plan 17.4 to 17.6): checked by code, looks that
return data, suggestions that write nothing, the change digest, the impact check against a
reference computation, the memory of suggestions and the lessons it offers, typed checks with
their code fallback."""
from __future__ import annotations

import os
import shutil
import unittest

from brainkit import agent_tools, kev
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


def vault_hash(root: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    for folder, _dirs, names in sorted(os.walk(os.path.join(root, "knowledge"))):
        for name in sorted(names):
            with open(os.path.join(folder, name), "rb") as handle:
                digest.update(handle.read())
    return digest.hexdigest()


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)
        self.note = next(n for n in self.brain.state().index.notes.values()
                         if n.kind == "fact" and n.live)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def test_code_checks_every_call(self):
        _, problems = agent_tools.call(self.brain, "delete_note", {"id": self.note.id})
        self.assertIn("no tool 'delete_note'", problems[0])
        _, problems = agent_tools.call(self.brain, "get_note", {"id": "invented-note"})
        self.assertIn("no note 'invented-note'", problems)
        _, problems = agent_tools.call(self.brain, "get_note", {"id": self.note.id, "x": 1})
        self.assertIn("no argument 'x'", problems)
        _, problems = agent_tools.call(self.brain, "suggest_note", {"change": "rewrite",
                                                                    "why": "x"})
        self.assertTrue(any("change is one of" in p for p in problems))
        found, problems = agent_tools.call(self.brain, "get_note", {"id": self.note.id})
        self.assertEqual(problems, [])
        self.assertIn(self.note.title, found)

    def test_suggestion_tools_write_nothing(self):
        before = vault_hash(self.vault)
        for name, args in (
                ("suggest_note", {"change": "retire", "ids": [self.note.id], "why": "over"}),
                ("challenge", {"id": self.note.id, "why": "may be old"}),
                ("open_task", {"title": "Check it", "why": "stale"}),
                ("suggest_state", {"sheet": "accounts", "row": "x", "column": "y",
                                   "value": "z", "why": "w"})):
            found, problems = agent_tools.call(self.brain, name, args)
            self.assertEqual(problems, [], name)
            self.assertIn("suggestion", found)
        self.assertEqual(vault_hash(self.vault), before)  # no direct writes: 100%

    def test_the_impact_line_matches_a_reference_count(self):
        for n in range(3):
            self.brain.context(f"{self.note.title} ({n})")
        found = agent_tools.impact(self.brain, self.note.id)
        reference = sum(
            1 for row in self.brain.ledger.requests(limit=500)
            if self.note.id in ((row.get("data") or {}).get("note_ids") or []))
        self.assertEqual(found["briefs"], reference)
        self.assertIn(f"{reference} brief", found["line"])

    def test_the_change_digest_says_what_changed(self):
        owner = self.brain.state().config.owner
        made = self.brain.propose(area="marketing", topic="booth", text="The booth is blue.",
                                  note_kind="fact", principal=owner, force_pending=True)
        self.brain.approve(made.data["proposal_id"], actor=owner)
        digest = agent_tools.changes_since(self.brain)
        self.assertIn("marketing", digest["line"])

    def test_the_memory_finds_past_suggestions_and_offers_a_lesson(self):
        for n in range(3):
            self.brain.ledger.add_episode(action="tidy-repeats", area="clients",
                                          topic=f"Acme pricing note {n}",
                                          text="Merge the two Acme notes", decision="declined",
                                          reason="client notes stay apart")
        found = agent_tools.past_suggestions(self.brain, "Acme pricing")
        self.assertEqual(len(found), 3)
        lessons = agent_tools.lessons(self.brain)
        self.assertEqual(lessons[0]["decision"], "declined")
        self.assertIn("client notes stay apart", lessons[0]["text"])

    def test_typed_checks_fall_back_to_code(self):
        notes = [n for n in self.brain.state().index.notes.values() if n.live][:2]
        for kind in ("stale", "duplicate", "contradicts", "worth", "tier"):
            found = kev.check(self.brain, kind, notes[0], notes[1])
            self.assertEqual(found["by"], "code", kind)
            self.assertIn("Typed check (code)", kev.line(found))


if __name__ == "__main__":
    unittest.main()
