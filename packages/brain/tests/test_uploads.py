"""Automatic brain updates: capture nudges, proposal hygiene, skill and file uploads, sync.

The person should not have to add context by hand. The agent proposes as work happens (notes,
skills, documents, assets) and folders are swept for new material. What waits for review
waits in a staging area, outside the vault and its git history, until the owner decides:
skills always, and files when the capture policy says so (these tests set it; filing at once,
the default, is covered in test_files.py).
"""
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import governance, util  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import test_layout  # noqa: E402

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5E"
    "rkJggg==")


class Base(unittest.TestCase):
    """A fresh bakery brain (area layout) per test, acting as its owner, Ana."""

    brain_json = None
    files_wait = True  # these tests exercise review; filing at once is test_files.py's

    def setUp(self):
        self.vault = test_layout.build()
        if self.brain_json:
            self.update_brain_json(self.brain_json)
        if self.files_wait:
            self.update_governance({"capture": {
                "file": {"app": "wait", "chat": "wait", "folder": "wait"}}})
        self.brain = Brain(self.vault, embeddings=False)
        self.tmp = tempfile.mkdtemp(prefix="brain-uploads-")

    def update_governance(self, changes):
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data.setdefault("governance", {}).update(changes)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def update_brain_json(self, changes):
        path = os.path.join(self.vault, "brain.json")
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data.update(changes)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(os.path.dirname(self.vault), ignore_errors=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, *parts):
        return os.path.join(self.vault, *parts)

    def staging(self, proposal_id):
        return os.path.join(self.vault, ".brain", "staging", proposal_id)

    def write_tmp(self, name, data):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(path, mode, **({} if isinstance(data, bytes) else {"encoding": "utf-8"})) as h:
            h.write(data)
        return path

    def decisions(self):
        path = self.path("journal", "decisions.jsonl")
        return util.read_jsonl(path) if os.path.exists(path) else []


class ProposalHygieneTests(Base):
    brain_json = {"governance": {"approver": "person:ana", "auto_apply_own_scope": True,
                                 "max_proposals_per_session": 3}}

    def test_identical_pending_proposal_is_returned_not_duplicated(self):
        first = self.brain.propose(area="company", topic="menu", scope="company",
                                   text="Croissants are baked fresh at 6am daily.")
        again = self.brain.propose(area="company", topic="menu", scope="company",
                                   text="Croissants are baked  fresh at 6am daily.")
        self.assertEqual(first.data["status"], "pending")
        self.assertEqual(again.data["status"], "duplicate")
        self.assertEqual(again.data["proposal_id"], first.data["proposal_id"])
        self.assertEqual(len(self.brain.inbox().data["proposals"]), 1)

    def test_a_changed_number_is_not_a_duplicate(self):
        live = self.brain.propose(area="company", topic="menu", scope="person:ana",
                                  text="The half-day baking class costs $4,500.")
        self.assertEqual(live.data["status"], "applied", live.text)
        changed = self.brain.propose(area="company", topic="menu", scope="company",
                                     text="The half-day baking class costs $3,500.")
        self.assertEqual(changed.data["status"], "pending", changed.text)
        same = self.brain.propose(area="company", topic="menu", scope="company",
                                  text="The half-day baking class costs $4,500.")
        self.assertEqual(same.data["status"], "duplicate", same.text)

    def test_session_cap_stops_a_flood_of_proposals(self):
        session = "sess-0123456789ab"
        for n in range(3):
            res = self.brain.propose(area="company", topic="menu", scope="company",
                                     text=f"Menu fact number {n} for the cap test.",
                                     session_id=session)
            self.assertEqual(res.data["status"], "pending", res.text)
        capped = self.brain.propose(area="company", topic="menu", scope="company",
                                    text="One proposal too many for this session.",
                                    session_id=session)
        self.assertTrue(capped.is_error)
        self.assertEqual(capped.data["status"], "limit")
        other = self.brain.propose(area="company", topic="menu", scope="company",
                                   text="A different session is not capped.",
                                   session_id="sess-ba9876543210")
        self.assertEqual(other.data["status"], "pending")

    def test_auto_applied_change_records_its_session(self):
        res = self.brain.propose(area="company", topic="story", scope="person:ana",
                                 text="Ana prefers weekly summaries on Fridays.",
                                 session_id="sess-0123456789ab")
        self.assertEqual(res.data["status"], "applied", res.text)
        self.assertEqual(self.decisions()[-1]["session"], "sess-0123456789ab")


class SkillUploadTests(Base):
    def propose(self, **overrides):
        kwargs = dict(
            name="holiday-orders", category="kitchen",
            description="Take and schedule holiday cake and bread orders.",
            when_to_use="a customer wants a holiday order, or the holiday order sheet",
            triggers=["take a holiday order"], loads=["company/menu"],
            body="# /holiday-orders\n\n1. Confirm the date.\n2. Take a deposit.\n",
            files=[{"path": "assets/order-form.md", "content": "# Holiday order form\n"},
                   {"path": "assets/logo.png",
                    "content_base64": base64.b64encode(PNG).decode()}])
        kwargs.update(overrides)
        return self.brain.propose_skill(**kwargs)

    def test_skill_proposal_is_staged_not_live(self):
        res = self.propose()
        self.assertEqual(res.data["status"], "pending", res.text)
        pid = res.data["proposal_id"]
        self.assertFalse(os.path.exists(self.path("skills", "kitchen", "holiday-orders")))
        self.assertNotIn("holiday-orders", self.brain.state().index.skills)
        self.assertTrue(os.path.isfile(os.path.join(self.staging(pid), "files", "assets",
                                                    "logo.png")))
        row = self.brain.inbox().data["proposals"][0]
        self.assertEqual(row["kind"], "skill.create")
        self.assertEqual(sorted(f["path"] for f in row["files"]),
                         ["assets/logo.png", "assets/order-form.md"])

    def test_approving_installs_the_skill_with_its_files(self):
        pid = self.propose().data["proposal_id"]
        approved = governance.approve(self.brain, pid)
        self.assertFalse(approved.is_error, approved.text)
        folder = self.path("skills", "kitchen", "holiday-orders")
        with open(os.path.join(folder, "assets", "logo.png"), "rb") as handle:
            self.assertEqual(handle.read(), PNG)
        self.assertFalse(os.path.exists(self.staging(pid)))
        skill = self.brain.state().index.skills["holiday-orders"]
        self.assertEqual(skill.triggers, ["take a holiday order"])
        self.assertEqual(skill.load_topics, ["company/menu"])
        self.assertIn("Take a deposit", self.brain.skill("holiday-orders").text)
        self.assertEqual(self.decisions()[-1]["action"], "approved")

    def test_rejecting_leaves_nothing_behind(self):
        pid = self.propose().data["proposal_id"]
        rejected = governance.reject(self.brain, pid, "not needed")
        self.assertFalse(rejected.is_error, rejected.text)
        self.assertFalse(os.path.exists(self.staging(pid)))
        self.assertFalse(os.path.exists(self.path("skills", "kitchen", "holiday-orders")))
        self.assertEqual(self.brain.inbox().data["proposals"], [])

    def test_updating_a_skill_keeps_untouched_files(self):
        governance.approve(self.brain, self.propose().data["proposal_id"])
        update = self.brain.propose_skill(
            target="holiday-orders", body="# /holiday-orders\n\n1. Confirm the date twice.\n",
            files=[{"path": "assets/price-list.md", "content": "Yule log: 40 dollars\n"}])
        self.assertEqual(update.data["status"], "pending", update.text)
        self.assertEqual(self.brain.inbox().data["proposals"][0]["kind"], "skill.update")
        governance.approve(self.brain, update.data["proposal_id"])
        folder = self.path("skills", "kitchen", "holiday-orders")
        self.assertTrue(os.path.isfile(os.path.join(folder, "assets", "logo.png")))
        self.assertTrue(os.path.isfile(os.path.join(folder, "assets", "price-list.md")))
        skill = self.brain.state().index.skills["holiday-orders"]
        self.assertIn("twice", skill.body)
        self.assertEqual(skill.triggers, ["take a holiday order"])

    def test_an_existing_name_needs_an_explicit_target(self):
        governance.approve(self.brain, self.propose().data["proposal_id"])
        again = self.propose()
        self.assertTrue(again.is_error)
        self.assertIn("target", again.text)

    def test_unsafe_files_are_refused_before_anything_is_staged(self):
        for bad in ({"path": "../escape.md", "content": "x"},
                    {"path": "C:/Windows/evil.md", "content": "x"},
                    {"path": "assets/.env", "content": "SECRET=1"},
                    {"path": "keys/id_rsa", "content": "x"},
                    {"path": "assets/server.pem", "content": "x"},
                    {"path": "tool.exe", "content_base64": base64.b64encode(b"MZ").decode()},
                    {"path": "big.md", "content": "x" * (11 * 1024 * 1024)}):
            with self.subTest(path=bad["path"]):
                res = self.propose(files=[bad])
                self.assertTrue(res.is_error, res.text)
        self.assertFalse(os.path.exists(os.path.join(self.vault, ".brain", "staging")) and
                         os.listdir(os.path.join(self.vault, ".brain", "staging")))

    def test_files_can_come_from_local_paths(self):
        source = self.write_tmp("checklist.md", "# Closing checklist\n")
        res = self.propose(files=[{"path": "assets/checklist.md", "source_path": source}])
        self.assertEqual(res.data["status"], "pending", res.text)
        missing = self.propose(name="other-skill",
                               files=[{"path": "a.md", "source_path": source + ".nope"}])
        self.assertTrue(missing.is_error)


class FileUploadTests(Base):
    def test_document_waits_for_review_then_becomes_a_reference_and_pointer(self):
        source = self.write_tmp("Winter Menu.md",
                                "# Winter menu\n\nMulled wine buns cost 4 dollars. Chestnut "
                                "loaves are baked on Saturdays only.\n")
        res = self.brain.add_file(source_path=source, title="Winter menu",
                                  description="Seasonal menu with prices",
                                  topic="company/menu")
        self.assertEqual(res.data["status"], "pending", res.text)
        self.assertEqual(res.data["purpose"], "reference")
        self.assertFalse(os.path.exists(self.path("references")) and
                         os.listdir(self.path("references")))
        approved = governance.approve(self.brain, res.data["proposal_id"])
        self.assertFalse(approved.is_error, approved.text)
        reference = self.brain.reference("references/winter-menu.md")
        self.assertIn("Chestnut loaves", reference.text)
        pointer = self.brain.state().index.note(approved.data["pointer"])
        self.assertIn("references/winter-menu.md", pointer.body)
        self.assertEqual(pointer.route_key, "company/menu")
        self.assertIn("winter-menu", self.brain.search("winter menu prices").text)

    def file_menu(self, price):
        res = self.brain.add_file(content=f"# Winter menu\n\nMulled wine buns cost {price} "
                                          "dollars.\n", filename="winter-menu.md",
                                  title="Winter menu", topic="company/menu")
        approved = governance.approve(self.brain, res.data["proposal_id"])
        self.assertFalse(approved.is_error, approved.text)
        return approved.data["pointer"]

    def test_a_same_size_write_is_visible_even_when_the_file_timestamp_does_not_move(self):
        self.file_menu(4)
        path = self.path("references", "winter-menu.md")
        self.assertIn("4 dollars", self.brain.reference("references/winter-menu.md").text)
        stamp = os.stat(path)
        before = self.brain.vault.fingerprint()
        text = util.read_text(path).replace("4 dollars", "5 dollars")
        self.brain.vault.touch(path)
        util.atomic_write(path, text)
        os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        self.assertEqual(self.brain.vault.fingerprint(), before)
        self.assertIn("5 dollars", self.brain.reference("references/winter-menu.md").text)
        # Subsequent reads must keep the rebuilt state, not only repair the first response.
        self.assertIn("5 dollars", self.brain.reference("references/winter-menu.md").text)

    def test_a_new_version_replaces_the_reference_and_keeps_its_pointer(self):
        from brainkit import checkpoints
        pointer = self.file_menu(4)
        notes = len(self.brain.state().index.notes)
        update = self.brain.add_file(content="# Winter menu\n\nMulled wine buns cost 5 "
                                             "dollars.\n", filename="winter-menu.md",
                                     title="Winter menu", replaces="references/winter-menu.md")
        self.assertEqual(update.data["status"], "pending", update.text)
        self.assertEqual(update.data["keep_pointer"], pointer)
        self.assertIn("4 dollars", self.brain.reference("references/winter-menu.md").text)
        done = self.brain.decide([{"id": update.data["proposal_id"], "action": "approve"}],
                                 label="New winter menu")
        self.assertFalse(done.is_error, done.text)
        text = self.brain.reference("references/winter-menu.md").text
        self.assertIn("5 dollars", text)
        self.assertNotIn("4 dollars", text)
        self.assertTrue(text.startswith("# Winter menu\n\n> Source:"), text[:80])
        self.assertEqual(len(self.brain.state().index.notes), notes)
        self.assertIsNotNone(self.brain.state().index.note(pointer))
        undone = checkpoints.undo(self.brain, done.data["checkpoint"]["id"])
        self.assertFalse(undone.is_error, undone.text)
        self.assertIn("4 dollars", self.brain.reference("references/winter-menu.md").text)

    def test_a_new_version_is_refused_when_the_file_changed_since(self):
        self.file_menu(4)
        update = self.brain.add_file(content="Mulled wine buns cost 5 dollars.",
                                     filename="winter-menu.md",
                                     replaces="references/winter-menu.md")
        with open(self.path("references", "winter-menu.md"), "a", encoding="utf-8") as handle:
            handle.write("Edited by hand meanwhile.\n")
        refused = governance.approve(self.brain, update.data["proposal_id"])
        self.assertTrue(refused.is_error)
        self.assertEqual(refused.data["status"], "conflict")

    def test_a_new_version_of_a_file_nothing_points_at_adds_no_note(self):
        self.file_menu(4)
        os.makedirs(self.path("references"), exist_ok=True)
        with open(self.path("references", "hours.md"), "w", encoding="utf-8") as handle:
            handle.write("# Hours\n\nOpen 7am to 3pm.\n")
        notes = len(self.brain.state().index.notes)
        update = self.brain.add_file(content="# Hours\n\nOpen 7am to 4pm.\n",
                                     filename="hours.md", replaces="references/hours.md")
        self.assertIsNone(update.data["keep_pointer"])
        done = governance.approve(self.brain, update.data["proposal_id"])
        self.assertFalse(done.is_error, done.text)
        self.assertIn("4pm", self.brain.reference("references/hours.md").text)
        self.assertEqual(len(self.brain.state().index.notes), notes)

    def test_only_a_filed_reference_can_be_replaced(self):
        missing = self.brain.add_file(content="Hours text", filename="hours.md",
                                      replaces="references/hours.md")
        self.assertEqual(missing.data["status"], "refused", missing.text)
        outside = self.brain.add_file(content="Hours text", filename="hours.md",
                                      replaces="../brain.json")
        self.assertEqual(outside.data["status"], "refused", outside.text)

    def test_asset_is_filed_as_bytes_with_a_pointer(self):
        res = self.brain.add_file(content_base64=base64.b64encode(PNG).decode(),
                                  filename="logo.png", title="Crumb logo",
                                  description="Primary logo, use on light backgrounds",
                                  topic="company/story")
        self.assertEqual(res.data["purpose"], "asset")
        approved = governance.approve(self.brain, res.data["proposal_id"])
        self.assertFalse(approved.is_error, approved.text)
        target = approved.data["path"]
        self.assertTrue(target.startswith("assets/"))
        with open(self.path(*target.split("/")), "rb") as handle:
            self.assertEqual(handle.read(), PNG)
        pointer = self.brain.state().index.note(approved.data["pointer"])
        self.assertIn(target, pointer.body)

    def test_the_same_file_twice_is_a_duplicate(self):
        first = self.brain.add_file(content="Opening hours: 7am to 3pm, closed Mondays.",
                                    filename="hours.md", title="Opening hours")
        again = self.brain.add_file(content="Opening hours: 7am to 3pm, closed Mondays.",
                                    filename="hours-copy.md", title="Hours again")
        self.assertEqual(again.data["status"], "duplicate")
        self.assertEqual(again.data["proposal_id"], first.data["proposal_id"])

    def test_sensitive_and_unsupported_files_are_refused(self):
        secret = self.brain.add_file(content="STRICTLY CONFIDENTIAL salary bands",
                                     filename="pay.md", title="Pay")
        self.assertTrue(secret.is_error)
        binary = self.brain.add_file(content_base64=base64.b64encode(b"MZ").decode(),
                                     filename="setup.exe", title="Installer")
        self.assertTrue(binary.is_error)
        key = self.brain.add_file(source_path=self.write_tmp(".env", "TOKEN=abc"))
        self.assertTrue(key.is_error)

    def test_files_wait_even_in_your_own_scope_when_the_policy_says_so(self):
        res = self.brain.add_file(content="Ana's personal recipe notes for sourdough.",
                                  filename="notes.md", title="Recipe notes",
                                  scope="person:ana")
        self.assertEqual(res.data["status"], "pending")


class CaptureInPacketTests(Base):
    def test_packet_carries_a_capture_nudge(self):
        res = self.brain.context("From now on, always add the allergen list to menu posts. "
                                 "Write a post about our sourdough loaves.",
                                 principal="person:ana", record=False)
        self.assertIn("## Capture", res.text)
        self.assertIn("allergen list", res.text)
        self.assertEqual(res.data["capture"][0]["kind"], "rule")

    def test_ordinary_request_has_no_capture_section(self):
        res = self.brain.context("What do the sourdough loaves cost?",
                                 principal="person:ana", record=False)
        self.assertNotIn("## Capture", res.text)
        self.assertEqual(res.data["capture"], [])


class HookTests(unittest.TestCase):
    def run_hook(self, stdin):
        return subprocess.run([sys.executable, "-m", "brainkit.hooks.capture_prompt"],
                              input=stdin, capture_output=True, text=True, encoding="utf-8",
                              timeout=30)

    def test_durable_message_gets_context_for_the_agent(self):
        done = self.run_hook(json.dumps({"hook_event_name": "UserPromptSubmit",
                                         "prompt": "I prefer bullet summaries from now on."}))
        self.assertEqual(done.returncode, 0, done.stderr)
        payload = json.loads(done.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(payload["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("propose_note", context)
        self.assertIn("bullet summaries", context)

    def test_an_ordinary_request_gets_only_the_reminder_to_ask_the_brain(self):
        done = self.run_hook(json.dumps({"prompt": "Write a post about sourdough."}))
        context = json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("get_task_context", context)
        self.assertNotIn("propose_note", context)
        quiet = self.run_hook(json.dumps({"prompt": "thanks!"}))
        self.assertEqual((quiet.returncode, quiet.stdout.strip()), (0, ""))

    def test_garbage_never_breaks_the_session(self):
        done = self.run_hook("this is not json")
        self.assertEqual((done.returncode, done.stdout.strip()), (0, ""))


class SyncTests(Base):
    def setUp(self):
        super().setUp()
        self.drop = os.path.join(self.tmp, "drop")
        self.skills = os.path.join(self.tmp, "skills")
        os.makedirs(self.drop)
        os.makedirs(self.skills)
        self.update_brain_json({"sync": {"drop": [self.drop], "skills": [self.skills]}})

    def add_skill_folder(self, name, body):
        folder = os.path.join(self.skills, name)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(f"---\nname: {name}\ndescription: {name} procedure\n---\n{body}\n")
        return folder

    def test_dropped_files_are_proposed_once(self):
        self.write_tmp("drop/allergens.md", "# Allergens\n\nAll loaves may contain sesame.\n")
        self.write_tmp("drop/logo.png", PNG)
        first = self.brain.sync()
        self.assertEqual(first.data["proposed"], 2, first.text)
        again = self.brain.sync()
        self.assertEqual(again.data["proposed"], 0, again.text)
        kinds = sorted(p["kind"] for p in self.brain.inbox().data["proposals"])
        self.assertEqual(kinds, ["file.add", "file.add"])

    def test_unsafe_drops_are_skipped_once_and_reported(self):
        self.write_tmp("drop/.env", "TOKEN=abc")
        self.write_tmp("drop/setup.exe", b"MZ")
        first = self.brain.sync()
        self.assertEqual(first.data["proposed"], 0)
        self.assertEqual(first.data["skipped"], 2, first.text)
        self.assertEqual(self.brain.sync().data["skipped"], 0)

    def test_skill_folders_are_proposed_and_changes_become_updates(self):
        self.add_skill_folder("closing-up", "# /closing-up\n\n1. Lock the back door.\n")
        first = self.brain.sync()
        self.assertEqual(first.data["proposed"], 1, first.text)
        row = self.brain.inbox().data["proposals"][0]
        self.assertEqual(row["kind"], "skill.create")
        governance.approve(self.brain, row["id"])
        self.assertIn("closing-up", self.brain.state().index.skills)
        self.assertEqual(self.brain.sync().data["proposed"], 0)
        self.add_skill_folder("closing-up", "# /closing-up\n\n1. Lock both doors.\n")
        changed = self.brain.sync()
        self.assertEqual(changed.data["proposed"], 1, changed.text)
        self.assertEqual(self.brain.inbox().data["proposals"][0]["kind"], "skill.update")


if __name__ == "__main__":
    unittest.main()
