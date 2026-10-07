"""The context supply chain: an entry's versions and the events that made them, putting one
back, its details, where it went, and where requests found nothing."""
import datetime as dt
import json
import os
import sqlite3
import sys
from contextlib import closing
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import checkpoints, governance, inventory, util
from brainkit.api import Brain
from brainkit.model import Note
from brainkit.sessions import Ledger
from tests import fixture

ENV = {"GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "t@example.com",
       "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "t@example.com"}
NOTE = "facts-services-002"


def configure(vault, **changes):
    path = os.path.join(vault, "brain.json")
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    for key, value in changes.items():
        config[key] = value
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)


class Base(unittest.TestCase):
    git = False

    def setUp(self):
        self.vault = fixture.build(git=self.git)
        if self.git:
            configure(self.vault, git={"auto_commit": True})
            with open(os.path.join(os.path.dirname(self.vault), ".gitignore"), "w") as handle:
                handle.write("vault/.brain/\n")
        self.env = mock.patch.dict(os.environ, ENV)
        self.env.start()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        self.env.stop()
        fixture.remove(self.vault)

    def decide(self, *items):
        res = governance.decide(self.brain, list(items))
        self.assertFalse(res.is_error, res.text)
        return res

    def note(self, note_id=NOTE):
        return self.brain.state().index.note(note_id, include_archived=True)

    def journal(self):
        return util.read_jsonl(os.path.join(self.vault, "journal", "decisions.jsonl"))


class VersionTests(Base):
    git = True

    def test_every_change_is_a_version_that_says_who_made_it_and_why(self):
        self.decide({"id": NOTE, "action": "edit", "reason": "Shorter",
                     "body": "Web projects run six to eight weeks."})
        self.decide({"id": NOTE, "action": "update", "fields": {"owner": "person:sam"}})
        rows = self.brain.versions(NOTE).data["versions"]
        self.assertEqual(len(rows), 3)
        newest, edited, first = rows
        self.assertTrue(newest["current"] and newest["committed"])
        self.assertFalse(newest["text_changed"])  # only a detail changed
        self.assertEqual([c["action"] for c in newest["changes"]], ["updated"])
        self.assertTrue(edited["text_changed"])
        self.assertEqual(edited["changes"][0]["reason"], "Shorter")
        self.assertNotIn("previous", edited["changes"][0])  # full texts stay out of listings
        self.assertEqual(first["message"], "fixture")
        self.assertNotIn("body", first)
        with_text = self.brain.versions(NOTE, with_text=True).data["versions"]
        self.assertTrue(with_text[-1]["body"].startswith("Web design projects run six"))

    def test_an_earlier_version_comes_back_and_the_restore_can_be_undone(self):
        original = self.note().body
        self.decide({"id": NOTE, "action": "edit", "body": "Projects take a while."})
        first = self.brain.versions(NOTE).data["versions"][-1]
        done = self.decide({"id": NOTE, "action": "restore", "ref": first["ref"],
                            "reason": "the edit lost the invoicing"})
        self.assertEqual(self.note().body, original)
        record = self.journal()[-1]
        self.assertEqual((record["action"], record["from"]), ("restored", first["commit"]))
        self.assertEqual(record["previous"], "Projects take a while.")
        self.assertEqual(record["hash"], util.sha256(original))
        self.assertEqual(done.data["checkpoint"]["label"], "Restored 1")
        self.assertTrue(self.note().meta.get("revised"))
        checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertEqual(self.note().body, "Projects take a while.")
        again = governance.restore(self.brain, NOTE, "current")
        self.assertEqual(again.data["status"], "unchanged")

    def test_a_restore_needs_a_live_entry_and_one_of_its_versions(self):
        self.assertTrue(governance.restore(self.brain, NOTE, "0000000").is_error)
        archived = governance.restore(self.brain, "facts-services-000", "current")
        self.assertTrue(archived.is_error)
        self.assertIn("bring it back first", archived.text)
        self.assertTrue(self.brain.versions("no-such-note").is_error)

    def test_a_skill_keeps_every_version_and_review_shows_what_a_change_replaces(self):
        update = self.brain.propose_skill(
            target="brand-sheet", description="A one-page brand sheet PDF.",
            body="# /brand-sheet\n\n1. Gather the palette.\n2. Export a one-page PDF.\n")
        self.assertEqual(update.data["status"], "pending", update.text)
        row = next(r for r in self.brain.review().data["proposals"]
                   if r["kind"] == "skill.update")
        self.assertEqual(row["skill"]["name"], "brand-sheet")
        self.assertEqual(row["skill"]["description"], "A one-page brand sheet PDF.")
        before = row["skill_before"]
        self.assertIn("Write the voice lines", before["body"])
        self.assertTrue(before["description"].startswith("Produce a one-page brand sheet"))
        self.assertFalse(row["base_changed"])
        approved = governance.approve(self.brain, update.data["proposal_id"])
        self.assertFalse(approved.is_error, approved.text)
        rows = self.brain.skill_versions("brand-sheet", with_text=True).data["versions"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["current"] and rows[0]["text_changed"])
        self.assertIn("Gather the palette.", rows[0]["body"])
        self.assertEqual(rows[0]["meta"]["description"], "A one-page brand sheet PDF.")
        self.assertIn("Write the voice lines", rows[1]["body"])
        self.assertEqual(rows[1]["message"], "fixture")
        self.assertNotIn("body", self.brain.skill_versions("brand-sheet").data["versions"][0])
        self.assertTrue(self.brain.skill_versions("no-such-skill").is_error)

    def test_a_skill_change_proposed_before_another_was_approved_says_so(self):
        first = self.brain.propose_skill(target="brand-sheet", body="# /brand-sheet\n\n1. One.\n")
        governance.approve(self.brain, first.data["proposal_id"])
        stale = self.brain.propose_skill(target="brand-sheet", body="# /brand-sheet\n\n1. Two.\n")
        path = os.path.join(self.vault, "skills", "design", "brand-sheet", "SKILL.md")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("1. One.", "1. One, edited by hand."))
        row = next(r for r in self.brain.review().data["proposals"]
                   if r["id"] == stale.data["proposal_id"])
        self.assertTrue(row["base_changed"])
        self.assertIn("The skill changed since this was proposed", " ".join(row["problems"]))

    def test_a_hand_edit_not_committed_yet_is_the_newest_version(self):
        path = os.path.join(self.vault, *self.note().path.split("/"))
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text.replace("six to eight", "seven"))
        rows = self.brain.versions(NOTE).data["versions"]
        self.assertEqual((rows[0]["ref"], rows[0]["committed"]), ("current", False))
        self.assertEqual(rows[0]["message"], "Not committed yet")
        self.assertTrue(rows[1]["committed"])


class JournalVersionTests(Base):
    """Without git, an edit's journal record keeps what it replaced."""

    def test_versions_come_from_the_journal_without_git(self):
        original = self.note().body
        self.decide({"id": NOTE, "action": "edit", "body": "Projects take a while."})
        rows = self.brain.versions(NOTE, with_text=True).data["versions"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ref"], "current")
        self.assertTrue(rows[1]["ref"].startswith("journal:"))
        self.assertEqual(rows[1]["body"], original)
        self.decide({"id": NOTE, "action": "restore", "ref": rows[1]["ref"]})
        self.assertEqual(self.note().body, original)


class DetailTests(Base):
    def test_owner_cadence_and_sensitivity_are_set_and_cleared(self):
        self.decide({"id": NOTE, "action": "update", "reason": "Sam runs projects",
                     "fields": {"owner": "person:sam", "review_days": "30",
                                "classification": "confidential"}})
        meta = self.note().meta
        self.assertEqual((meta["owner"], meta["review_days"], meta["classification"]),
                         ("person:sam", "30", "confidential"))
        record = self.journal()[-1]
        self.assertEqual(record["action"], "updated")
        self.assertEqual(record["was"]["owner"], "")
        self.decide({"id": NOTE, "action": "update", "fields": {"review_days": ""}})
        self.assertNotIn("review_days", self.note().meta)
        same = governance.update(self.brain, NOTE, {"owner": "person:sam"})
        self.assertEqual(same.data["status"], "unchanged")

    def test_details_that_make_no_sense_are_refused(self):
        res = governance.update(self.brain, NOTE, {
            "review_days": "soon", "owner": "person:nobody", "classification": "secret",
            "area": "nowhere", "status": "archived"})
        self.assertTrue(res.is_error)
        self.assertEqual(len(res.data["problems"]), 5)
        self.assertNotIn("owner", self.note().meta)

    def test_moving_an_entry_moves_its_file(self):
        before = self.note().path
        self.decide({"id": NOTE, "action": "update", "fields": {"topic": "pricing"}})
        moved = self.note()
        self.assertEqual(moved.route_key, "facts/pricing")
        self.assertNotEqual(moved.path, before)
        self.assertFalse(os.path.exists(os.path.join(self.vault, *before.split("/"))))
        self.assertEqual(self.journal()[-1]["moved_from"], before)

    def test_a_cadence_in_policy_makes_entries_due(self):
        governance.verify(self.brain, NOTE)
        configure(self.vault, governance={"approver": "person:alex",
                                          "review_days": {"facts": 10, "services": 30}})
        st = self.brain.state()
        note = self.note()
        self.assertEqual(st.config.review_days_for(note), 10)
        today = util.today_date()  # notes carry the owner's local date
        self.assertIsNone(note.stale_reason(today, 10))
        self.assertIn("not verified since", note.stale_reason(today + dt.timedelta(days=11), 10))
        row = self.brain.entry(NOTE).data
        self.assertEqual(row["review_days"], 10)
        self.assertEqual(row["review_due"], (today + dt.timedelta(days=10)).isoformat())
        governance.update(self.brain, NOTE, {"review_days": "90"})
        self.assertEqual(self.brain.state().config.review_days_for(self.note()), 90)

    def test_checks_made_in_bulk_are_one_undo_point(self):
        done = self.decide({"id": NOTE, "action": "verify", "confidence": "confirmed"},
                           {"id": "facts-services-001", "action": "mark", "state": "stale",
                            "reason": "the offer changed"})
        self.assertEqual(done.data["checkpoint"]["label"], "Verified 1, marked 1")
        self.assertEqual(self.note().meta["confidence"], "confirmed")
        self.assertTrue(self.note("facts-services-001").meta["stale"])
        refused = governance.decide(self.brain, [{"id": NOTE, "action": "mark",
                                                  "state": "stale"}])
        self.assertTrue(refused.is_error)  # a mark needs a reason
        checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertNotIn("stale", self.note("facts-services-001").meta)

    def test_an_archived_entry_comes_back(self):
        self.decide({"id": "facts-services-000", "action": "unarchive", "reason": "still true"})
        self.assertTrue(self.note("facts-services-000").live)
        self.assertEqual(self.journal()[-1]["action"], "unarchived")
        self.assertTrue(governance.unarchive(self.brain, "facts-services-001").is_error)

    def test_a_merged_entry_comes_back_beside_what_replaced_it(self):
        res = self.brain.propose(layer="facts", topic="services", scope="company",
                                 text="Northwind does brand, web and motion work.",
                                 supersedes="facts-services-001")
        self.decide({"id": res.data["proposal_id"], "action": "approve"})
        self.assertEqual(self.note("facts-services-001").meta["superseded_by"], res.data["id"])
        back = governance.unarchive(self.brain, "facts-services-001")
        self.assertEqual(back.data["replaced_by"], res.data["id"])
        self.assertNotIn("superseded_by", self.note("facts-services-001").meta)


class UseTests(Base):
    def usage(self, note_id=NOTE):
        return self.brain.ledger.usage_table("note").get(("note", note_id)) or {}

    def test_handouts_are_counted_by_day_and_kept_when_the_detail_goes(self):
        first = self.brain.context(NOTE).data["session_id"]
        self.brain.note(NOTE, session_id=first)  # opened again: the same conversation
        self.brain.context(NOTE)  # another conversation
        self.brain.record_use("run_1", [{"id": NOTE}, {"id": "no-such-note"}])
        counts = self.usage()
        self.assertEqual((counts["total"], counts["d7"], counts["d30"]), (3, 3, 3))
        self.assertEqual((counts["in_packets"], counts["opened"], counts["in_work"]), (2, 1, 1))
        self.assertEqual(counts["last"], util.now().date().isoformat())
        use = self.brain.use(NOTE).data
        self.assertEqual({r["via"] for r in use["recent"]}, {"packet", "opened", "work"})
        self.assertIn("work:run_1", {r["session_id"] for r in use["recent"]})
        self.assertEqual(use["daily"][-1]["conversations"], 3)
        # The detail ages out; the counts stay.
        path = self.brain.ledger.path
        self.brain.close()
        old = (util.now() - dt.timedelta(days=200)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute("UPDATE deliveries SET at = ?", (old,))
            conn.execute("UPDATE packets SET at = ?", (old,))
            conn.execute("UPDATE sessions SET seen = ?", (old,))
        self.brain = Brain(self.vault, embeddings=False)
        self.brain.ledger.touch("sess-later")
        self.assertEqual(self.brain.use(NOTE).data["recent"], [])
        self.assertEqual(self.usage()["total"], 3)

    def test_each_handout_says_why_routing_picked_it(self):
        sid = self.brain.context("How long do web design projects run from kickoff to "
                                 "launch?").data["session_id"]
        recent = self.brain.use(NOTE).data["recent"]
        self.assertEqual(recent[0]["session_id"], sid)
        self.assertIn("score", recent[0]["reason"])
        self.assertIn("words:", recent[0]["reason"])
        self.assertIn("kickoff", recent[0]["request"])

    def test_an_older_ledger_is_counted_once(self):
        path = os.path.join(self.vault, ".brain", "old.sqlite")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.executescript(
                "CREATE TABLE deliveries (session_id TEXT, packet_id TEXT, kind TEXT, "
                "item TEXT, hash TEXT, tokens INTEGER, at TEXT);")
            day = util.now_iso()
            conn.executemany("INSERT INTO deliveries VALUES (?, ?, 'note', ?, 'h', 10, ?)", [
                ("s1", "p1", NOTE, day), ("s1", "followup", NOTE, day), ("s2", "p2", NOTE, day),
                ("work:r1", "work", NOTE, day)])
        for _ in range(2):  # a second process opening it adds nothing
            ledger = Ledger(path)
            row = ledger.usage_table("note")[("note", NOTE)]
            ledger.close()
        self.assertEqual((row["total"], row["in_packets"], row["opened"], row["in_work"]),
                         (3, 2, 1, 1))


class GapTests(Base):
    def test_a_request_that_found_nothing_is_a_gap_until_dismissed(self):
        self.brain.context("What is the capital of Portugal?")
        gaps = self.brain.gaps().data["gaps"]
        self.assertEqual([g["kind"] for g in gaps], ["nothing"])
        self.assertIn("Portugal", gaps[0]["request"])
        self.brain.dismiss_gap(gaps[0]["key"])
        self.assertEqual(self.brain.gaps().data["gaps"], [])

    def test_an_entry_the_ai_had_to_find_itself_is_a_gap(self):
        sid = self.brain.context("What is the capital of Portugal?").data["session_id"]
        self.brain.note("rules-design-001", session_id=sid)
        searched = [g for g in self.brain.gaps().data["gaps"] if g["kind"] == "searched"]
        self.assertEqual(len(searched), 1)
        self.assertEqual(searched[0]["entry"], "rules-design-001")
        self.assertTrue(searched[0]["entry_title"])
        # Opening what the packet brought or listed is no gap.
        sid = self.brain.context(NOTE).data["session_id"]
        self.brain.note(NOTE, session_id=sid)
        self.assertEqual(len([g for g in self.brain.gaps().data["gaps"]
                              if g["kind"] == "searched"]), 1)


class InventoryTests(Base):
    def test_every_entry_skill_and_document_is_listed_with_its_details(self):
        rows = {r["id"]: r for r in self.brain.inventory().data["items"]}
        note = rows[NOTE]
        self.assertEqual((note["owner"], note["owner_set"]), ("person:alex", False))
        self.assertEqual((note["type"], note["live"], note["changes"]), ("note", True, 0))
        self.assertEqual(note["uses"], {"total": 0, "d7": 0, "d30": 0, "last": None})
        self.assertFalse(rows["facts-services-000"]["live"])
        self.assertEqual(rows["brand-sheet"]["type"], "skill")
        self.assertEqual(rows["references/style-guide.md"]["type"], "reference")
        self.decide({"id": NOTE, "action": "edit", "body": "Projects take a while."})
        self.assertEqual(self.brain.entry(NOTE).data["changes"], 1)

    def test_origin_is_read_from_what_a_note_already_says(self):
        def origin(created=None, **meta):
            note = Note(id="n", area="facts", topic="t", scope="company", status="approved",
                        load="on-demand", body="x", path="p", meta=meta)
            found = inventory.origin_of(note, created)
            return found["kind"], found["ref"]

        self.assertEqual(origin(source="workspace, proposed by Claude Code"), ("workspace", ""))
        self.assertEqual(origin(source="sync: drop/brief.md"), ("file", ""))
        self.assertEqual(origin(source="reference brief.pdf proposed by person:alex"),
                         ("file", ""))
        self.assertEqual(origin(source="worktree distill Pass 2 - Tools.md"), ("import", ""))
        self.assertEqual(origin(source="captured by person:alex with remember"), ("you", ""))
        self.assertEqual(origin({"session": "sess-1"}, source="proposed by person:alex"),
                         ("conversation", "sess-1"))
        self.assertEqual(origin(origin="meeting:mtg_1", source="anything"), ("meeting", "mtg_1"))
        self.assertEqual(origin(), ("unknown", ""))

    def test_a_note_proposed_in_a_conversation_names_it(self):
        res = self.brain.propose(layer="facts", topic="services", scope="person:alex",
                                 text="I review motion work on Thursdays.",
                                 session_id="sess-abc123")
        self.assertEqual(res.data["status"], "applied", res.text)
        row = self.brain.entry(res.data["id"]).data
        self.assertEqual(row["origin"]["kind"], "conversation")
        self.assertEqual(row["origin"]["ref"], "sess-abc123")
        given = self.brain.propose(layer="facts", topic="services", scope="person:alex",
                                   text="Motion reviews need the storyboard.",
                                   origin="meeting:mtg_7")
        self.assertEqual(self.note(given.data["id"]).meta["origin"], "meeting:mtg_7")


class PolicyTests(Base):
    def test_the_owner_sets_policy_and_can_undo_it(self):
        before = self.brain.policies().data
        self.assertEqual((before["review_days"], before["retention_days"]), ({}, 90))
        self.assertEqual(before["default_owner"], "person:alex")
        res = self.brain.set_policies({"review_days": {"facts": 120, "state": 30},
                                       "retention_days": 30, "default_owner": "person:sam"},
                                      reason="quarterly checks")
        self.assertFalse(res.is_error, res.text)
        policy = self.brain.policies().data
        self.assertEqual(policy["review_days"], {"facts": 120, "state": 30})
        self.assertEqual((policy["retention_days"], policy["default_owner"]), (30, "person:sam"))
        self.assertEqual(self.brain.state().config.review_days_for(self.note()), 120)
        self.assertEqual(self.brain.entry(NOTE).data["owner"], "person:sam")
        record = self.journal()[-1]
        self.assertEqual((record["action"], record["was"]["retention_days"]), ("policy", 90))
        self.assertEqual(self.brain.set_policies({"retention_days": 30}).data["status"],
                         "unchanged")
        checkpoints.undo(self.brain, res.data["checkpoint"]["id"])
        self.assertEqual(self.brain.policies().data["review_days"], {})

    def test_policy_that_makes_no_sense_is_refused(self):
        res = self.brain.set_policies({"review_days": {"nowhere": 5, "facts": "soon"},
                                       "retention_days": 0, "default_owner": "person:nobody",
                                       "approver": "person:sam"})
        self.assertTrue(res.is_error)
        self.assertEqual(len(res.data["problems"]), 4)
        self.assertEqual(self.brain.policies().data["retention_days"], 90)


class FlowTests(Base):
    def test_the_week_shows_what_came_in_what_was_decided_and_what_waits(self):
        made = [self.brain.propose(layer="facts", topic="services", scope="company", text=t)
                for t in ("Kickoffs happen on Mondays.", "Launches never happen on Fridays.")]
        self.decide({"id": made[0].data["proposal_id"], "action": "approve"})
        self.brain.context("What is the capital of Portugal?")
        flow = self.brain.flow().data
        self.assertEqual((flow["came_in"], flow["approved"], flow["waiting"]), (2, 1, 1))
        self.assertTrue(flow["oldest_waiting"])
        self.assertEqual(flow["delivery"]["empty"], 1)
        self.assertEqual(flow["usage_since"], util.now().date().isoformat())
        self.assertEqual(flow["stock"]["live"], len(self.brain.state().index.notes))
        self.assertGreater(flow["stock"]["standing_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
