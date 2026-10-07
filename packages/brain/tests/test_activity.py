"""What each AI asked and what it got: the app recorded from the MCP handshake, each request
with its pieces and why, what the conversation opened after it, and what it saved."""
import io
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import activity
from brainkit.api import Brain
from brainkit.mcp_server import Server
from tests import fixture


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        self.server = Server(self.brain, out=io.StringIO())

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def call(self, name, **arguments):
        self.server.out = io.StringIO()
        self.server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": name, "arguments": arguments}})
        return json.loads(self.server.out.getvalue())["result"]

    def test_a_request_says_which_app_asked_what_it_got_and_what_it_saved(self):
        self.server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                            "params": {"clientInfo": {"name": "claude-code",
                                                      "version": "2.1.0"}}})
        reply = self.call("get_task_context", request="Write a headline for the web page")
        session = reply["content"][0]["text"].split("session_id: ")[1].split(" ")[0]
        self.call("get_note", id="facts-services-002", session_id=session)
        self.call("propose_note", layer="facts", topic="services", scope="company",
                  text="Web projects include two rounds of changes.", session_id=session)
        data = self.brain.requests().data
        (request,) = data["requests"]
        self.assertEqual(request["app"], "Claude Code")
        self.assertEqual(request["request"], "Write a headline for the web page")
        self.assertTrue(request["kernel"])
        got = {p["id"]: p for p in request["got"]}
        self.assertIn("rules-style-002", got)
        self.assertEqual(got["rules-style-002"]["title"],
                         self.brain.state().index.note("rules-style-002").title)
        self.assertTrue(all(p["why"] or p["kind"] != "note" for p in request["got"]))
        self.assertEqual([p["id"] for p in request["opened"]], ["facts-services-002"])
        (saved,) = request["saved"]
        self.assertEqual(saved["status"], "waiting")
        self.assertGreater(request["tokens"], 0)
        self.assertGreater(request["share"], 0)
        self.assertEqual(data["apps"], ["Claude Code"])
        self.assertEqual(self.brain.requests(client="Cursor").data["requests"], [])

    def test_app_names(self):
        self.assertEqual(activity.client_label("claude-code 2.1.0"), "Claude Code")
        self.assertEqual(activity.client_label("claude-ai 0.1"), "Claude Desktop")
        self.assertEqual(activity.client_label("cursor-vscode 1.0"), "Cursor")
        self.assertEqual(activity.client_label("codex-mcp-client 0.4"), "Codex")
        self.assertEqual(activity.client_label("my-tool 3"), "my-tool")
        self.assertEqual(activity.client_label(""), "An AI app")

    def test_paging_and_an_empty_ledger(self):
        self.assertEqual(self.brain.requests().data["requests"], [])
        for text in ("How long do web projects take?", "Headline rules?"):
            self.brain.context(text)
        newest, older = self.brain.requests().data["requests"]
        self.assertEqual(newest["request"], "Headline rules?")
        page = self.brain.requests(before=newest["id"]).data["requests"]
        self.assertEqual([r["id"] for r in page], [older["id"]])
        self.assertEqual(self.brain.requests(before=older["id"]).data["requests"], [])


if __name__ == "__main__":
    unittest.main()
