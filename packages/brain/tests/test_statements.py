"""One statement model (brain-logic plan 6) and the goals plan's G0: one vocabulary for what a
statement is, read from what every note already records; who said it, when to check it again
and its tier; brief text kept by preset; goal notes; and a project's objective."""
from __future__ import annotations

import json
import os
import shutil
import unittest

from brainkit import governance, health, mcp_server, statements
from brainkit import safeguards_eval as se
from brainkit.api import Brain

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
BRAINS = os.path.join(ROOT, "brains")


class Config:
    """Just enough of a Brain's settings for the vocabulary's readers."""

    def __init__(self, data):
        self.data = data
        self.governance = data.get("governance") or {}


class _Meta:
    """Just enough of a note for the vocabulary's readers."""

    def __init__(self, kind="fact", load="on-demand", **meta):
        self.kind, self.load, self.meta = kind, load, dict(meta)

    @property
    def verified(self):
        return str(self.meta.get("verified") or self.meta.get("added") or "")


class VocabularyTest(unittest.TestCase):
    def test_every_list_comes_from_the_one_vocabulary(self):
        self.assertIs(governance.NOTE_KINDS, statements.NOTE_KINDS)
        self.assertIs(governance.CAPTURE_TYPES, statements.CAPTURE_TYPES)
        tool = next(t for t in mcp_server.AGENT_TOOLS if t["name"] == "notes_propose")
        self.assertEqual(tool["inputSchema"]["properties"]["kind"]["enum"],
                         list(statements.NOTE_KINDS))
        for word in statements.PROPOSAL_KINDS + statements.NOTE_KINDS:
            self.assertIn(statements.kind(word), statements.KINDS, word)

    def test_older_words_read_as_the_kinds_they_name(self):
        self.assertEqual(statements.kind("state"), "value")
        self.assertEqual(statements.kind("focus"), "project")
        self.assertEqual(statements.kind("preference"), "rule")
        self.assertEqual(statements.subtype("preference"), "preference")
        self.assertEqual(statements.filed("value"), "state")
        self.assertEqual(statements.filed("preference"), "rule")
        self.assertEqual(statements.kind("something else"), "fact")

    def test_every_demo_note_reads_as_a_statement_without_loss(self):
        for name in sorted(os.listdir(BRAINS)):
            vault = os.path.join(BRAINS, name, "vault")
            if not os.path.isfile(os.path.join(vault, "brain.json")):
                continue
            copy = se.copy_vault(vault)
            brain = Brain(copy, embeddings=False)
            try:
                st = brain.state()
                for note in st.index.notes.values():
                    found = statements.describe(note, st.config)
                    self.assertIn(found["kind"], statements.KINDS, note.id)
                    self.assertIn(found["tier"], statements.TIERS, note.id)
                    self.assertEqual(note.statement_kind, found["kind"])
                checked = health.report(brain)
                self.assertFalse(checked.is_error, f"{name}: {checked.text}")
            finally:
                brain.close()
                shutil.rmtree(os.path.dirname(copy), ignore_errors=True)

    def test_capture_types_follow_the_vocabulary(self):
        def capture(**target):
            return governance.capture_type("note.create", target)

        self.assertEqual(capture(kind="rule", subtype="preference"), "preference")
        self.assertEqual(capture(kind="rule", subtype="convention"), "convention")
        self.assertEqual(capture(kind="rule"), "rule")
        self.assertEqual(capture(kind="procedure"), "rule")
        self.assertEqual(capture(kind="identity"), "convention")
        self.assertEqual(capture(kind="goal"), "convention")
        self.assertEqual(capture(kind="state"), "progress")
        self.assertEqual(capture(kind="fact", type="decision"), "decision")
        self.assertEqual(capture(kind="decision"), "decision")
        self.assertEqual(capture(kind="fact"), "fact")
        self.assertEqual(governance.capture_type("note.update", {"kind": "fact"}), "change")


class StatementFieldsTest(unittest.TestCase):
    def test_who_said_it_comes_from_the_note_or_its_origin(self):
        self.assertEqual(statements.said_by({"said_by": "person"}, "conversation"), "person")
        self.assertEqual(statements.said_by({}, "conversation"), "owner-ai")
        self.assertEqual(statements.said_by({}, "meeting"), "person")
        self.assertEqual(statements.said_by({}, "file"), "document")
        self.assertEqual(statements.said_by({}, "run"), "agent")
        self.assertEqual(statements.said_by({}, "you"), "owner")
        self.assertEqual(statements.said_by({}, "unknown"), "")

    def test_the_tier_comes_from_the_kind_and_the_load(self):
        self.assertEqual(statements.tier("rule"), "alignment")
        self.assertEqual(statements.tier("goal"), "alignment")
        self.assertEqual(statements.tier("fact", "domain"), "alignment")  # a must-hold
        self.assertEqual(statements.tier("state"), "state")
        self.assertEqual(statements.tier("fact"), "knowledge")
        self.assertEqual(statements.tier("focus"), "knowledge")

    def test_review_by_comes_from_a_shelf_life_by_kind_unless_set(self):
        config = Config({})
        fact = _Meta("fact", verified="2026-01-01")
        self.assertEqual(statements.review_by(fact, config), "2026-06-30")  # 180 days
        project = _Meta("focus", added="2026-01-01")
        self.assertEqual(statements.review_by(project, config), "2026-01-31")  # 30 days
        own = _Meta("fact", verified="2026-01-01", review_by="2026-02-01")
        self.assertEqual(statements.review_by(own, config), "2026-02-01")
        custom = Config({"statements": {"shelf_life": {"fact": 10}}})
        self.assertEqual(statements.review_by(fact, custom), "2026-01-11")
        self.assertEqual(statements.review_by(_Meta("fact"), config), "")

    def test_brief_text_is_kept_by_preset_unless_set(self):
        self.assertEqual(governance.retention_days(Config({})), 90)  # careful
        regulated = Config({"governance": {"preset": "regulated"}})
        self.assertEqual(governance.retention_days(regulated), 730)
        own = Config({"governance": {"preset": "regulated"},
                      "sessions": {"retention_days": 30}})
        self.assertEqual(governance.retention_days(own), 30)


class GoalsAndObjectivesTest(unittest.TestCase):
    def setUp(self):
        self.vault = se.copy_vault(os.path.join(BRAINS, "knowledge-company", "vault"))
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)

    def owner(self):
        return self.brain.state().config.owner

    def test_a_goal_note_loads_only_when_asked_for_and_its_fields_are_checked(self):
        made = self.brain.propose(
            area="marketing", topic="goals", text="Grow webinar attendance to 150 a session.",
            title="Webinar attendance", note_kind="goal", principal=self.owner(),
            extra={"level": "yours", "due": "2026-12-15", "goal_status": "active"})
        self.assertFalse(made.is_error, made.text)
        approved = self.brain.approve(made.data["proposal_id"], actor=self.owner())
        self.assertFalse(approved.is_error, approved.text)
        note = self.brain.state().index.note(made.data["id"])
        self.assertEqual((note.kind, note.load), ("goal", "manual"))
        self.assertEqual(note.meta["goal_status"], "active")
        self.assertEqual(note.tier, "alignment")
        wrong = self.brain.propose(
            area="marketing", topic="goals", text="Something else.", note_kind="goal",
            principal=self.owner(), extra={"level": "someday", "due": "soon"})
        self.assertTrue(wrong.is_error)
        self.assertIn("level is one of purpose, yours, agent", wrong.text)
        self.assertIn("due is a date", wrong.text)

    def test_a_project_objective_opens_its_briefs_and_changes_with_a_reason(self):
        made = self.brain.focus_create(
            "Spring Fair", "Our stand at the spring trade fair.",
            objective="Forty qualified conversations at the fair, each logged for sales.")
        self.assertFalse(made.is_error, made.text)
        project = made.data["id"]
        brief = self.brain.context("Plan the spring fair stand", record=False)
        self.assertIn("Objective of the project Spring Fair: Forty qualified conversations",
                      brief.text)
        refused = self.brain.update(project, {"objective": "Sixty conversations."})
        self.assertTrue(refused.is_error)
        self.assertIn("needs a reason", refused.text)
        changed = self.brain.update(project, {"objective": "Sixty conversations."},
                                    reason="The stand doubled in size.")
        self.assertFalse(changed.is_error, changed.text)
        self.assertEqual(self.brain.state().index.note(project).meta["objective"],
                         "Sixty conversations.")
        long_one = " ".join(["word"] * 61)
        too_long = self.brain.focus_create("Long One", "x", objective=long_one)
        self.assertTrue(too_long.is_error)
        self.assertIn("about 60 words", too_long.text)
        not_a_project = self.brain.update("company-numbers", {"objective": "x"}, reason="r")
        self.assertTrue(not_a_project.is_error)

    def test_the_workspace_files_a_preference_as_a_rule_of_that_subtype(self):
        from brainkit import statements as vocabulary
        self.assertEqual(vocabulary.filed("preference"), "rule")
        made = self.brain.propose(
            area="marketing", topic="voice", text="I prefer short subject lines.",
            note_kind=vocabulary.filed("preference"), principal=self.owner(),
            extra={"subtype": "preference"}, force_pending=True)
        self.assertFalse(made.is_error, made.text)
        waiting = json.dumps(made.data)
        self.assertIn("pending", waiting)


if __name__ == "__main__":
    unittest.main()
