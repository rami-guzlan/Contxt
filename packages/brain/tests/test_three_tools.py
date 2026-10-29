"""The Brain's MCP surface in three tools (section 17.4 of the v4 plan): `context` first,
`brain(action)` for every read and `propose(kind)` for every suggestion, about 1k tokens with
the instructions. The details come back from brain(action: "help"); every earlier name still
answers; the kernel is paid once; and the prompt hook captures with no model call."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from brainkit import mcp_server, util
from brainkit.api import Brain
from brainkit.hooks import capture_prompt
from tests import fixture

SESSION = "3f2b9c1e-7d4a-4b8e-9c0f-1a2b3c4d5e6f"


class ThreeToolsTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.server = mcp_server.Server(self.brain)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_three_tools_and_the_instructions_cost_about_a_thousand_tokens(self):
        self.assertEqual([t["name"] for t in self.server.tools], ["context", "brain", "propose"])
        cost = (util.tokens(json.dumps(self.server.tools))
                + util.tokens(mcp_server.public_text(mcp_server.INSTRUCTIONS)))
        self.assertLessEqual(cost, 1000)

    def test_a_read_answers_as_its_old_tool_did(self):
        new = self.server.call("brain", {"action": "search", "query": "website redesign"})
        old = self.server.call("notes_search", {"query": "website redesign"})
        self.assertFalse(new.is_error, new.text)
        self.assertEqual(new.text, old.text)

    def test_every_earlier_name_still_answers(self):
        names = ([t["name"] for t in mcp_server.AGENT_TOOLS] + list(mcp_server.ALIASES)
                 + list(mcp_server.GROUPS))
        for name in names:
            found = self.server.call(name, {})
            self.assertNotIn("is not available", found.text, name)
            self.assertNotIn("No kind", found.text, name)

    def test_a_note_proposal_takes_its_note_kind_under_its_own_name(self):
        made = self.server.call("propose", {
            "kind": "note", "note_kind": "rule", "area": "rules", "topic": "style",
            "text": "Headlines are in sentence case.", "evidence": '"sentence case, always"'})
        self.assertFalse(made.is_error, made.text)
        waiting = [p for p in self.brain.inbox().data["proposals"]
                   if "sentence case" in json.dumps(p)]
        self.assertTrue(waiting, made.text)

    def test_help_documents_every_action_and_kind(self):
        index = self.server.call("brain", {"action": "help"})
        for name in [*mcp_server.BRAIN_ACTIONS, *mcp_server.PROPOSE_KINDS]:
            self.assertIn(f"- {name}(", index.text)
        search = self.server.call("brain", {"action": "help", "about": "search"})
        self.assertIn("`query`", search.text)
        note = self.server.call("brain", {"action": "help", "about": "note"})
        self.assertIn("`note_kind`", note.text)
        self.assertNotIn("notes_propose", note.text + index.text)
        reading = self.server.call("brain", {"action": "help", "about": "reading"})
        self.assertIn("cumulative snapshots", reading.text)

    def test_an_unknown_action_or_kind_names_the_ones_there_are(self):
        action = self.server.call("brain", {"action": "delete"})
        self.assertTrue(action.is_error)
        self.assertIn("search", action.text)
        kind = self.server.call("propose", {"kind": "email"})
        self.assertTrue(kind.is_error)
        self.assertIn("note", kind.text)

    def test_text_sent_out_names_the_three_tools(self):
        said = mcp_server.public_text(
            'Open it with notes_get(id="x"), search with notes(action: "search"), call '
            "gnomon_get_context, then todos_update.")
        self.assertEqual(said, 'Open it with brain(action: "get", id="x"), search with '
                               'brain(action: "search"), call context, then '
                               'propose(kind: "todo").')

    def start(self, client: str, folder: str):
        out = io.StringIO()
        server = mcp_server.Server(self.brain, out=out)
        with mock.patch.object(os, "getcwd", return_value=folder):
            server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"clientInfo": {"name": client, "version": "1"}}})
        return server

    def test_a_client_that_loaded_the_startup_file_is_not_sent_the_kernel_again(self):
        written = self.brain.write_kernel().data
        folder = os.path.dirname(self.vault)
        self.assertEqual(mcp_server.startup_fingerprint(folder), written["fingerprint"])
        loaded = self.start("claude-code", folder).call("context", {"request": "Write a post"})
        self.assertFalse(loaded.data["kernel_included"])
        self.assertNotIn("# Startup context (kernel", loaded.text)
        other = self.start("claude-ai", folder).call("context", {"request": "Write a post"})
        self.assertTrue(other.data["kernel_included"])
        elsewhere = self.start("claude-code", tempfile.gettempdir()).call(
            "context", {"request": "Write a post"})
        self.assertTrue(elsewhere.data["kernel_included"])


class PacketBudgetTest(unittest.TestCase):
    """The owner's per-turn budgets (17.4) on a starter Brain: a first packet within 1.5k
    tokens, a new ask within 600 and an edit within 150."""

    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def test_first_packet_new_ask_and_edit_stay_within_their_budgets(self):
        first = self.brain.context("Draft a post announcing the website redesign")
        self.assertLessEqual(util.tokens(first.text), 1500)
        session = first.data["session_id"]
        ask = self.brain.context("Now write an email to a client about it", session_id=session)
        self.assertLessEqual(util.tokens(ask.text), 600)
        edit = self.brain.context("make it shorter", session_id=session)
        self.assertLessEqual(util.tokens(edit.text), 150)
        self.assertNotIn("Also relevant", edit.text)


class HookCaptureTest(unittest.TestCase):
    """The prompt hook files what a message states as lasting, with no model call."""

    def setUp(self):
        self.vault = fixture.build()
        env = {"BRAIN_VAULT": self.vault, "BRAIN_EMBEDDINGS": "0", "BRAIN_PRINCIPAL": "",
               "BRAIN_HOOK_PUSH": "0"}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()
        os.environ.pop("BRAIN_HOOK_ASK", None)
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        self.env.stop()
        fixture.remove(self.vault)

    def prompt(self, text) -> str:
        out = io.StringIO()
        payload = {"prompt": text, "session_id": SESSION}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), \
                contextlib.redirect_stdout(out):
            capture_prompt.main()
        found = out.getvalue()
        return json.loads(found)["hookSpecificOutput"]["additionalContext"] if found else ""

    def waiting(self, words) -> list:
        return [p for p in Brain(self.vault, embeddings=False).inbox().data["proposals"]
                if words in json.dumps(p)]

    def test_a_durable_message_is_filed_for_review_with_no_model_call(self):
        said = self.prompt("From now on, always send invoices on the first Monday.")
        self.assertIn("Filed for the owner's review", said)
        self.assertNotIn("propose(", said)
        self.assertEqual(len(self.waiting("first Monday")), 1)
        self.prompt("From now on, always send invoices on the first Monday.")
        self.assertEqual(len(self.waiting("first Monday")), 1)  # the same words, once

    def test_an_ordinary_request_gets_no_reminder_and_files_nothing(self):
        self.assertEqual(self.prompt("Draft a post announcing our new client program"), "")
        self.assertEqual(self.waiting("client program"), [])
        with mock.patch.dict(os.environ, {"BRAIN_HOOK_ASK": "1"}):
            self.assertIn("call context with it first", self.prompt("Write a post about it"))


if __name__ == "__main__":
    unittest.main()
