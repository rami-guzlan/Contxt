"""Proposals, the auto-apply policy, approvals, rejections, Focus writes and freshness."""
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import frontmatter as fm
from brainkit import governance, util
from brainkit.api import Brain
from tests import fixture


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def decisions(self):
        path = os.path.join(self.vault, "journal", "decisions.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_shared_knowledge_waits_for_approval(self):
        res = self.brain.propose(layer="facts", topic="services", scope="company",
                                 text="Motion design retainers are billed monthly.")
        self.assertEqual(res.data["status"], "pending", res.text)
        proposal_id = res.data["proposal_id"]
        self.assertTrue(os.path.exists(os.path.join(self.vault, "inbox", proposal_id + ".md")))
        self.assertNotIn(res.data["id"], self.brain.state().index.notes)
        approved = governance.approve(self.brain, proposal_id)
        self.assertFalse(approved.is_error, approved.text)
        note = self.brain.state().index.notes[res.data["id"]]
        self.assertEqual(note.meta["approved_by"], "person:alex")
        self.assertFalse(os.path.exists(os.path.join(self.vault, "inbox", proposal_id + ".md")))
        self.assertEqual(self.decisions()[-1]["action"], "approved")

    def test_own_scope_applies_immediately(self):
        res = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                 text="Give me the answer first, reasoning after.")
        self.assertEqual(res.data["status"], "applied", res.text)
        self.assertIn(res.data["id"], self.brain.state().index.notes)
        self.assertEqual(self.decisions()[-1]["action"], "auto-applied")

    def test_unscoped_proposal_goes_where_its_topic_lives(self):
        shared = self.brain.propose(layer="facts", topic="services",
                                    text="Motion retainers renew every quarter.")
        self.assertEqual(shared.data["status"], "pending", shared.text)
        personal = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                      text="Short answers first.")
        self.assertEqual(personal.data["status"], "applied")
        again = self.brain.propose(layer="rules", topic="preferences",
                                   text="Bullets over paragraphs.")
        self.assertEqual(again.data["status"], "applied", again.text)
        two = self.brain.propose(target_id="facts-services-001", text="Brand and web.")
        three = self.brain.propose(target_id="facts-services-001", text="Brand, web, motion.")
        self.assertNotEqual(two.data["proposal_id"], three.data["proposal_id"])

    def test_other_scope_and_force_pending_wait(self):
        res = self.brain.propose(layer="facts", topic="services", scope="person:sam",
                                 text="Sam covers motion work on Thursdays.")
        self.assertEqual(res.data["status"], "pending")
        forced = self.brain.propose(layer="rules", topic="preferences", scope="person:alex",
                                    text="Prefer bullet lists.", force_pending=True)
        self.assertEqual(forced.data["status"], "pending")

    def test_validation_duplicates_and_approver(self):
        bad = self.brain.propose(layer="nonsense", topic="x", text="y")
        self.assertTrue(bad.is_error)
        dup = self.brain.propose(layer="facts", topic="services", scope="company",
                                 text="Northwind offers brand identity, web design and motion "
                                      "design for small companies.")
        self.assertEqual(dup.data["status"], "duplicate")
        pending = self.brain.propose(layer="facts", topic="services", scope="company",
                                     text="Brand sprints take two weeks.")
        refused = governance.approve(self.brain, pending.data["proposal_id"], actor="person:sam")
        self.assertTrue(refused.is_error)
        self.assertEqual(refused.data["status"], "forbidden")

    def test_approve_with_edited_body_reject_and_log(self):
        a = self.brain.propose(layer="facts", topic="services", scope="company",
                               text="Brand sprints take two weeks.")
        b = self.brain.propose(layer="facts", topic="services", scope="company",
                               text="We also do print design.")
        done = governance.approve(self.brain, a.data["proposal_id"],
                                  body="Brand sprints take ten working days.")
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(self.brain.state().index.notes[a.data["id"]].body.strip(),
                         "Brand sprints take ten working days.")
        gone = governance.reject(self.brain, b.data["proposal_id"], "we do not do print")
        self.assertFalse(gone.is_error)
        last = self.decisions()[-1]
        self.assertEqual((last["action"], last["reason"]), ("rejected", "we do not do print"))
        self.assertEqual(last["body"], "We also do print design.")

    def test_update_conflict_archive_and_supersede(self):
        change = self.brain.propose(target_id="facts-services-002",
                                    text="Web design projects run eight weeks.")
        self.assertEqual(change.data["status"], "pending")
        note = self.brain.state().index.notes["facts-services-002"]
        path = os.path.join(self.vault, note.path)
        meta, body, _ = fm.parse(util.read_text(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(fm.dump(meta, "Edited by hand meanwhile.\n"))
        time.sleep(0.01)
        conflict = governance.approve(self.brain, change.data["proposal_id"])
        self.assertEqual(conflict.data["status"], "conflict")
        resolved = governance.approve(self.brain, change.data["proposal_id"],
                                      body="Web design projects run eight weeks.")
        self.assertFalse(resolved.is_error, resolved.text)
        newer = self.brain.propose(layer="facts", topic="services", scope="company",
                                   text="Northwind offers brand, web, motion and print design.",
                                   supersedes="facts-services-001")
        governance.approve(self.brain, newer.data["proposal_id"])
        self.assertNotIn("facts-services-001", self.brain.state().index.notes)
        self.assertIn("facts-services-001", self.brain.state().index.archived)

    def test_inbox_lists_pending(self):
        self.brain.propose(layer="facts", topic="services", scope="company",
                           text="Brand sprints take two weeks.")
        rows = self.brain.inbox().data["proposals"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["route_key"], "facts/services")


class FocusAndFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_focus_update_appends_and_changes_current_state(self):
        res = self.brain.focus_update("website redesign", "Case studies drafted",
                                      {"next": "Client review", "status": "active"})
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(res.data["seq"], 2)
        focus = self.brain.state().index.focuses["state-focus-website-redesign"]
        self.assertEqual(focus.current()["next"], "Client review")
        self.assertEqual(len(focus.updates), 2)
        packet = self.brain.context("Where are we with the website redesign?", record=False)
        self.assertIn("Client review", packet.text)

    def test_create_focus_in_own_scope_and_errors(self):
        created = self.brain.focus_create("Office Move", "Move the studio to the new space.")
        self.assertEqual(created.data["status"], "applied", created.text)
        self.assertIn("state-focus-office-move", self.brain.state().index.focuses)
        again = self.brain.focus_create("Office Move", "duplicate")
        self.assertTrue(again.is_error)
        missing = self.brain.focus_update("no such focus", "x")
        self.assertTrue(missing.is_error)

    def test_hand_edit_is_visible_on_the_next_request(self):
        note = self.brain.state().index.notes["facts-services-002"]
        path = os.path.join(self.vault, note.path)
        meta, _body, _ = fm.parse(util.read_text(path))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(fm.dump(meta, "Web design projects now run four weeks, invoices at "
                                       "kickoff.\n"))
        res = self.brain.context("How long do web design projects run?", record=False)
        self.assertIn("four weeks", res.text)


class GitCommitTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(git=True)
        with open(os.path.join(self.vault, "brain.json"), encoding="utf-8") as handle:
            data = json.load(handle)
        data["git"] = {"auto_commit": True}
        with open(os.path.join(self.vault, "brain.json"), "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        root = os.path.dirname(self.vault)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=t@example.com",
                        "commit", "-qam", "enable commits"], cwd=root, check=True,
                       capture_output=True)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_governed_writes_are_committed_with_only_their_files(self):
        root = os.path.dirname(self.vault)
        with open(os.path.join(root, "unrelated.txt"), "w") as handle:
            handle.write("work in progress")
        subprocess.run(["git", "add", "unrelated.txt"], cwd=root, check=True)
        res = self.brain.focus_update("website redesign", "Pages built")
        self.assertTrue(res.data["commit"]["committed"], res.data)
        log = subprocess.run(["git", "log", "-1", "--name-only", "--format=%s"], cwd=root,
                             capture_output=True, text=True).stdout
        self.assertIn("state-focus-website-redesign.jsonl", log)
        self.assertNotIn("unrelated.txt", log)

    def _git_sees_only(self, config=""):
        """Git reads only `config`: no system or user config, no identity from the environment,
        and no identity guessed from the machine (like a fresh container or CI runner)."""
        handle, path = tempfile.mkstemp(suffix=".gitconfig")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            out.write(config)
        self.addCleanup(os.remove, path)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_", "GIT_CONFIG"))
               and key != "EMAIL"}
        env.update(GIT_CONFIG_GLOBAL=path, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_COUNT="1",
                   GIT_CONFIG_KEY_0="user.useConfigOnly", GIT_CONFIG_VALUE_0="true")
        return mock.patch.dict(os.environ, env, clear=True)

    def _last_author(self):
        return subprocess.run(["git", "log", "-1", "--format=%an <%ae>"],
                              cwd=os.path.dirname(self.vault), capture_output=True,
                              text=True).stdout.strip()

    def test_governed_writes_are_committed_when_git_has_no_identity(self):
        with self._git_sees_only():
            res = self.brain.focus_update("website redesign", "Pages built")
        self.assertTrue(res.data["commit"]["committed"], res.data)
        self.assertEqual(self._last_author(), "AI Brain <brain@localhost>")

    def test_a_configured_git_identity_is_kept(self):
        with self._git_sees_only("[user]\n\tname = Pat Example\n\temail = pat@example.com\n"):
            res = self.brain.focus_update("website redesign", "Pages built")
        self.assertTrue(res.data["commit"]["committed"], res.data)
        self.assertEqual(self._last_author(), "Pat Example <pat@example.com>")


if __name__ == "__main__":
    unittest.main()
