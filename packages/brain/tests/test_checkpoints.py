"""Undo points: a batch of decisions is taken back as a unit, and only what it changed."""
import base64
import json
import os
import stat
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import checkpoints, governance, util
from brainkit.api import Brain
from tests import fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(files_wait=True)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    # ---------------------------------------------------------------- helpers

    def propose(self, text, **kwargs):
        kwargs.setdefault("layer", "facts")
        kwargs.setdefault("topic", "services")
        kwargs.setdefault("scope", "company")
        res = self.brain.propose(text=text, **kwargs)
        self.assertEqual(res.data.get("status"), "pending", res.text)
        return res.data["proposal_id"], res.data["id"]

    def journal(self):
        return util.read_jsonl(os.path.join(self.vault, "journal", "decisions.jsonl"))

    def note(self, note_id):
        return self.brain.state().index.note(note_id, include_archived=True)

    def pending(self):
        return set(self.brain.state().snapshot.proposals)

    # ---------------------------------------------------------------- batches

    def test_a_batch_of_decisions_is_one_undo_point(self):
        first, first_id = self.propose("Brand sprints run two weeks with one review.")
        second, _ = self.propose("Motion work is quoted per finished second.")
        res = governance.decide(self.brain, [{"id": first, "action": "approve"},
                                             {"id": second, "action": "reject",
                                              "reason": "not true"}],
                                label="Two decisions", source={"task_id": "task_1"})
        self.assertFalse(res.is_error, res.text)
        point = res.data["checkpoint"]
        self.assertEqual(point["label"], "Two decisions")
        self.assertEqual(point["source"], {"task_id": "task_1"})
        self.assertEqual([d["action"] for d in point["decisions"]], ["approved", "rejected"])
        self.assertEqual(point["decisions"][0]["note"], first_id)
        paths = {f["path"] for f in point["files"]}
        self.assertIn(f"inbox/{first}.md", paths)
        self.assertIn(f"inbox/{second}.md", paths)
        self.assertTrue(any(p.startswith("knowledge/") for p in paths))
        self.assertFalse(any(p.startswith("journal/") for p in paths))  # never rewound
        listed = checkpoints.list_checkpoints(self.brain)
        self.assertEqual(listed[0]["id"], point["id"])
        self.assertTrue(listed[0]["undoable"])

    def test_nothing_changed_makes_no_undo_point(self):
        res = governance.decide(self.brain, [{"id": "no-such-proposal", "action": "approve"}])
        self.assertTrue(res.is_error)
        self.assertIsNone(res.data["checkpoint"])
        self.assertEqual(checkpoints.list_checkpoints(self.brain), [])

    def test_only_the_approver_decides_or_undoes(self):
        proposal, _ = self.propose("Retainers include two rounds of revisions.")
        refused = governance.decide(self.brain, [{"id": proposal, "action": "approve"}],
                                    actor="person:sam")
        self.assertTrue(refused.is_error)
        self.assertIn(proposal, self.pending())
        done = governance.decide(self.brain, [{"id": proposal, "action": "approve"}])
        undo = checkpoints.undo(self.brain, done.data["checkpoint"]["id"], actor="person:sam")
        self.assertTrue(undo.is_error)
        self.assertEqual(undo.data["status"], "forbidden")

    # ---------------------------------------------------------------- undo

    def test_undo_takes_the_notes_out_and_puts_the_proposals_back(self):
        proposal, note_id = self.propose(
            "Web design projects run eight to ten weeks from kickoff to launch.",
            supersedes="facts-services-002")
        done = governance.decide(self.brain, [{"id": proposal, "action": "approve"}])
        self.assertFalse(done.is_error, done.text)
        self.assertTrue(self.note(note_id).live)
        self.assertFalse(self.note("facts-services-002").live)  # replaced, archived

        undone = checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertFalse(undone.is_error, undone.text)
        self.assertIsNone(self.note(note_id))
        restored = self.note("facts-services-002")
        self.assertTrue(restored.live)
        self.assertNotIn("superseded_by", restored.meta)
        self.assertIn(proposal, self.pending())  # back in review
        actions = [r.get("action") for r in self.journal()]
        self.assertIn("approved", actions)  # the journal keeps what happened
        self.assertEqual(actions[-1], "reverted")
        listed = {c["id"]: c for c in checkpoints.list_checkpoints(self.brain)}
        original = listed[done.data["checkpoint"]["id"]]
        self.assertEqual(original["undone_by"], undone.data["checkpoint"]["id"])
        self.assertFalse(original["undoable"])

    def test_undo_refuses_when_something_changed_since(self):
        proposal, note_id = self.propose("Logo files ship as SVG and PNG at three sizes.")
        done = governance.decide(self.brain, [{"id": proposal, "action": "approve"}])
        governance.mark(self.brain, note_id, "stale", reason="sizes changed")
        point = done.data["checkpoint"]["id"]
        (listed,) = checkpoints.list_checkpoints(self.brain)
        self.assertFalse(listed["undoable"])
        self.assertTrue(any(b["what"] for b in listed["blocked"]))
        refused = checkpoints.undo(self.brain, point)
        self.assertTrue(refused.is_error)
        self.assertEqual(refused.data["status"], "conflict")
        self.assertTrue(self.note(note_id).live)  # nothing was touched
        self.assertTrue(self.note(note_id).meta.get("stale"))

    def test_an_undo_can_itself_be_undone(self):
        proposal, note_id = self.propose("Every brand sheet includes a dark-mode palette.")
        done = governance.decide(self.brain, [{"id": proposal, "action": "approve"}])
        undone = checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertIsNone(self.note(note_id))
        redone = checkpoints.undo(self.brain, undone.data["checkpoint"]["id"])
        self.assertFalse(redone.is_error, redone.text)
        self.assertTrue(self.note(note_id).live)
        self.assertNotIn(proposal, self.pending())
        again = checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertTrue(again.is_error)  # already undone once; its redo stands now

    def test_a_rejected_upload_comes_back_whole(self):
        added = self.brain.add_file(filename="palette.png",
                                    content_base64=base64.b64encode(PNG).decode("ascii"),
                                    title="Studio palette", description="The brand colors")
        proposal = added.data["proposal_id"]
        staging = os.path.join(self.vault, ".brain", "staging", proposal)
        self.assertTrue(os.path.isdir(staging))
        done = governance.decide(self.brain, [{"id": proposal, "action": "reject"}])
        self.assertFalse(os.path.isdir(staging))
        checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertIn(proposal, self.pending())
        approved = governance.approve(self.brain, proposal)  # staged bytes are back
        self.assertFalse(approved.is_error, approved.text)
        with open(os.path.join(self.vault, *approved.data["path"].split("/")), "rb") as handle:
            self.assertEqual(handle.read(), PNG)

    def test_an_approved_upload_leaves_on_undo(self):
        added = self.brain.add_file(filename="palette.png",
                                    content_base64=base64.b64encode(PNG).decode("ascii"),
                                    title="Studio palette")
        proposal = added.data["proposal_id"]
        done = governance.decide(self.brain, [{"id": proposal, "action": "approve"}])
        filed = done.data["results"][0]["data"]["path"]
        self.assertTrue(os.path.isfile(os.path.join(self.vault, *filed.split("/"))))
        checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertFalse(os.path.exists(os.path.join(self.vault, *filed.split("/"))))
        self.assertIn(proposal, self.pending())

    def test_the_owner_archives_notes_in_the_same_batch(self):
        proposal, _ = self.propose("Studio day rate covers eight hours of senior design.")
        res = governance.decide(self.brain, [
            {"id": proposal, "action": "approve"},
            {"id": "facts-services-001", "action": "archive", "reason": "covered elsewhere"},
        ])
        self.assertFalse(res.is_error, res.text)
        self.assertFalse(self.note("facts-services-001").live)
        record = self.journal()[-1]
        self.assertEqual((record["action"], record["note"], record["reason"]),
                         ("archived", "facts-services-001", "covered elsewhere"))
        self.assertEqual([d["action"] for d in res.data["checkpoint"]["decisions"]],
                         ["approved", "archived"])
        checkpoints.undo(self.brain, res.data["checkpoint"]["id"])
        self.assertTrue(self.note("facts-services-001").live)

    def test_the_owner_edits_a_note_in_place_and_can_undo_it(self):
        before = self.note("facts-services-002")
        res = governance.decide(self.brain, [{
            "id": "facts-services-002", "action": "edit",
            "body": "Web design projects invoice at kickoff and at launch.",
            "edits": {"summary": "When web projects are invoiced"},
            "reason": "Length now lives in its own entry",
        }])
        self.assertFalse(res.is_error, res.text)
        edited = self.note("facts-services-002")
        self.assertEqual(edited.body, "Web design projects invoice at kickoff and at launch.")
        self.assertEqual(edited.meta["summary"], "When web projects are invoiced")
        self.assertEqual(edited.path, before.path)  # same entry, same place
        record = self.journal()[-1]
        self.assertEqual((record["action"], record["note"]), ("edited", "facts-services-002"))
        self.assertEqual(record["previous"], before.body)  # the journal keeps what it said
        self.assertEqual(res.data["checkpoint"]["decisions"][0]["action"], "edited")
        checkpoints.undo(self.brain, res.data["checkpoint"]["id"])
        self.assertEqual(self.note("facts-services-002").body, before.body)

    def test_an_edit_needs_a_live_note_and_some_text(self):
        for item in ({"id": "facts-services-000", "action": "edit", "body": "Text."},
                     {"id": "facts-services-002", "action": "edit", "body": "  "}):
            res = governance.decide(self.brain, [item])
            self.assertTrue(res.is_error, item)
        self.assertEqual(checkpoints.list_checkpoints(self.brain), [])

    def test_a_proposal_is_approved_with_the_owners_own_words(self):
        proposal, note_id = self.propose("Retainers include two rounds of revisions.")
        res = governance.decide(self.brain, [{
            "id": proposal, "action": "approve",
            "body": "Retainers include two rounds of revisions per month.",
        }])
        self.assertFalse(res.is_error, res.text)
        self.assertEqual(self.note(note_id).body,
                         "Retainers include two rounds of revisions per month.")

    def test_archiving_needs_a_live_note(self):
        res = governance.decide(self.brain, [{"id": "facts-services-000", "action": "archive"}])
        self.assertTrue(res.is_error)
        self.assertFalse(res.data["results"][0]["ok"])

    # ---------------------------------------------------------------- storage

    def test_undo_points_are_kept_outside_git_and_pruned(self):
        with mock.patch.object(checkpoints, "KEEP", 2):
            made = []
            for text in ("Kickoffs happen on Mondays.", "Launches never happen on Fridays.",
                         "Case studies wait for client sign-off."):
                proposal, _ = self.propose(text)
                made.append(governance.decide(
                    self.brain, [{"id": proposal, "action": "approve"}]).data["checkpoint"]["id"])
            kept = [c["id"] for c in checkpoints.list_checkpoints(self.brain)]
        self.assertEqual(kept, made[:0:-1])  # the newest two, newest first
        folder = os.path.join(self.vault, ".brain", "checkpoints")
        self.assertFalse(os.path.exists(os.path.join(folder, made[0] + ".json")))
        blobs = set(os.listdir(os.path.join(folder, "blobs")))
        wanted = {f["before"] for c in kept
                  for f in util.read_json(os.path.join(folder, c + ".json"))["files"]
                  if f["before"]}
        self.assertEqual(blobs, wanted)  # nothing kept that no undo point needs


class GitUndoTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build(git=True, files_wait=True)
        brain_json = os.path.join(self.vault, "brain.json")
        with open(brain_json, encoding="utf-8") as handle:
            config = json.load(handle)
        config["git"] = {"auto_commit": True}
        with open(brain_json, "w", encoding="utf-8") as handle:
            json.dump(config, handle)
        with open(os.path.join(os.path.dirname(self.vault), ".gitignore"), "w") as handle:
            handle.write("vault/.brain/\n")
        env = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
               "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        self.env.stop()
        fixture.remove(self.vault)

    def commits(self):
        out = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=os.path.dirname(self.vault),
                             capture_output=True, text=True, check=True)
        return int(out.stdout.strip())

    def test_a_batch_of_decisions_is_one_commit(self):
        ids = []
        for text in ("Kickoffs happen on Mondays.", "Launches never happen on Fridays.",
                     "Case studies wait for client sign-off."):
            res = self.brain.propose(layer="facts", topic="services", scope="company", text=text)
            ids.append(res.data["proposal_id"])
        before = self.commits()
        done = governance.decide(self.brain, [{"id": i, "action": "approve"} for i in ids],
                                 label="Three facts")
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(self.commits(), before + 1)
        self.assertTrue(done.data["commit"]["committed"])
        message = subprocess.run(["git", "log", "-1", "--format=%B"],
                                 cwd=os.path.dirname(self.vault), capture_output=True,
                                 text=True, check=True).stdout
        self.assertTrue(message.startswith("Three facts"))
        self.assertEqual(message.count("Approved note.create"), 3)
        live = self.brain.state().index.notes
        self.assertTrue(all(self.brain.state().snapshot.proposals.get(i) is None for i in ids))
        self.assertEqual(sum(1 for n in live.values() if n.meta.get("approved_by")), 3)

    def test_one_decision_is_committed_under_its_own_words(self):
        res = self.brain.propose(layer="facts", topic="services", scope="company",
                                 text="Kickoffs happen on Mondays.")
        governance.decide(self.brain, [{"id": res.data["proposal_id"], "action": "approve"}])
        subject = subprocess.run(["git", "log", "-1", "--format=%s", "--", "vault/knowledge"],
                                 cwd=os.path.dirname(self.vault), capture_output=True,
                                 text=True, check=True).stdout
        self.assertIn(res.data["id"], subject)  # git log names the note, as before batches

    def test_an_undo_is_committed_like_any_decision(self):
        res = self.brain.add_file(filename="palette.png",
                                  content_base64=base64.b64encode(PNG).decode("ascii"),
                                  title="Studio palette")
        done = governance.decide(self.brain, [{"id": res.data["proposal_id"],
                                               "action": "reject"}])
        undone = checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertFalse(undone.is_error, undone.text)
        commit = undone.data["commit"]
        self.assertTrue(commit and commit.get("committed"), commit)
        # the runtime folder (staging) is restored but never committed
        self.assertFalse(any(p.startswith("vault/.brain") for p in commit["paths"]))


@unittest.skipIf(os.name == "nt", "POSIX permissions")
class PermissionTests(unittest.TestCase):
    def test_written_files_are_readable_by_the_group(self):
        folder = fixture.build()
        try:
            path = os.path.join(folder, "note.md")
            util.atomic_write(path, "text\n")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode) & 0o044, 0o044)
            os.chmod(path, 0o640)
            util.atomic_write(path, "changed\n")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o640)  # kept as it was
        finally:
            fixture.remove(folder)


if __name__ == "__main__":
    unittest.main()
