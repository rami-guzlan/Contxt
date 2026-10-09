"""The adapters, driven for real: the MCP server as a subprocess and the local HTTP API."""
import json
import os
import subprocess
import sys
import unittest
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import governance, http_server  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import fixture  # noqa: E402


class MCPServerTests(unittest.TestCase):
    """Spawn `brain mcp` exactly as .mcp.json does and speak JSON-RPC to it."""

    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build()
        env = dict(os.environ, BRAIN_VAULT=cls.vault, BRAIN_EMBEDDINGS="0",
                   PYTHONIOENCODING="utf-8")
        env.pop("BRAIN_PRINCIPAL", None)
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "brainkit", "mcp"], cwd=ROOT, env=env,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8")
        cls.next_id = 0

    @classmethod
    def tearDownClass(cls):
        cls.proc.stdin.close()
        cls.proc.wait(timeout=10)
        cls.proc.stdout.close()
        cls.proc.stderr.close()
        fixture.remove(cls.vault)

    def rpc(self, method, params=None):
        type(self).next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method,
                   "params": params or {}}
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        self.assertTrue(line, self.proc.stderr.read() if self.proc.poll() is not None else "")
        return json.loads(line)

    def call(self, name, arguments):
        reply = self.rpc("tools/call", {"name": name, "arguments": arguments})
        return reply["result"]

    def test_handshake_tools_and_a_full_task(self):
        init = self.rpc("initialize", {"protocolVersion": "2025-06-18"})
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("get_task_context", init["result"]["instructions"])
        names = {t["name"] for t in self.rpc("tools/list")["result"]["tools"]}
        self.assertEqual(names, {"get_task_context", "get_skill", "get_reference", "get_note",
                                 "search_notes", "propose_note", "propose_skill", "add_file",
                                 "record_focus_update", "create_focus", "record_output",
                                 "brain_health", "challenge_note", "list_agents",
                                 "get_agent"})
        first = self.call("get_task_context", {"request": "How long do web design projects run?"})
        self.assertFalse(first["isError"], first)
        text = first["content"][0]["text"]
        self.assertIn("facts-services-002", text)
        self.assertIn("# Startup context", text)
        session = text.split("session_id: ", 1)[1].split()[0]
        second = self.call("get_task_context", {"request": "How long do web design projects run?",
                                                "session_id": session})
        self.assertIn("Already in this conversation", second["content"][0]["text"])
        self.assertNotIn("# Startup context", second["content"][0]["text"])
        skill = self.call("get_skill", {"name": "brand-sheet", "session_id": session})
        self.assertIn("Export a one-page PDF", skill["content"][0]["text"])
        ref = self.call("get_reference", {"path": "references/style-guide.md"})
        self.assertIn("Studio style guide", ref["content"][0]["text"])

    def test_agent_files_a_document_at_once_and_proposes_a_skill_for_review(self):
        skill = self.call("propose_skill", {
            "name": "client-kickoff", "category": "design",
            "description": "Run a client kickoff meeting.",
            "body": "# /client-kickoff\n\n1. Agenda.\n2. Goals.\n",
            "files": [{"path": "assets/agenda.md", "content": "# Kickoff agenda\n"}]})
        self.assertFalse(skill["isError"], skill)
        self.assertIn("for review", skill["content"][0]["text"])
        document = self.call("add_file", {"content": "# Studio rates\n\nDay rate: 900.",
                                          "filename": "rates.md", "title": "Studio rates"})
        self.assertFalse(document["isError"], document)
        self.assertIn("Filed Studio rates", document["content"][0]["text"])
        self.assertIn("can use it now", document["content"][0]["text"])
        asked = self.call("get_task_context", {"request": "What is the studio day rate?"})
        self.assertIn("From your files", asked["content"][0]["text"])
        self.assertIn("Day rate: 900.", asked["content"][0]["text"])
        unsafe = self.call("add_file", {"content": "TOKEN=1", "filename": ".env"})
        self.assertTrue(unsafe["isError"])

    def test_agent_searches_in_its_own_words_and_the_session_remembers(self):
        first = self.call("get_task_context", {"request": "What is our favourite colour?"})
        session = first["content"][0]["text"].split("session_id: ", 1)[1].split()[0]
        found = self.call("search_notes", {"query": "how long web design projects take",
                                           "session_id": session})
        self.assertFalse(found["isError"], found)
        text = found["content"][0]["text"]
        self.assertIn("facts-services-002", text)
        self.assertIn("get_note", text)
        opened = self.call("get_note", {"id": "facts-services-002", "session_id": session})
        self.assertFalse(opened["isError"], opened)
        again = self.call("search_notes", {"query": "how long web design projects take",
                                           "session_id": session})
        self.assertIn("already in this conversation", again["content"][0]["text"])
        packet = self.call("get_task_context", {"request": "How long do web design projects run?",
                                                "session_id": session})
        self.assertIn("Already in this conversation", packet["content"][0]["text"])

    def test_a_search_says_when_nothing_is_a_close_match(self):
        # "clients" reaches two notes, both far below what a request would be handed
        far = self.call("search_notes", {"query": "quantum pastry for clients next winter abroad"})
        text = far["content"][0]["text"]
        self.assertIn("No close match", text)
        self.assertIn("rules-delivery-001", text)  # the nearest are still listed
        near = self.call("search_notes", {"query": "how long web design projects take"})
        self.assertNotIn("No close match", near["content"][0]["text"])

    def test_writes_and_refusals(self):
        proposal = self.call("propose_note", {"layer": "facts", "topic": "services",
                                              "scope": "company",
                                              "text": "Workshops are sold as half days."})
        self.assertFalse(proposal["isError"], proposal)
        self.assertIn("not live until approved", proposal["content"][0]["text"])
        update = self.call("record_focus_update", {"focus": "website redesign",
                                                   "summary": "Nav built",
                                                   "changes": {"next": "Footer"}})
        self.assertFalse(update["isError"], update)
        missing = self.call("record_focus_update", {"focus": "nope", "summary": "x"})
        self.assertTrue(missing["isError"])
        forbidden = self.call("approve", {"id": "anything"})
        self.assertTrue(forbidden["isError"])
        health = self.call("brain_health", {})
        self.assertIn("Brain health", health["content"][0]["text"])
        unknown = self.rpc("no/such/method")
        self.assertEqual(unknown["error"]["code"], -32601)


class HTTPServerCase(unittest.TestCase):
    """A loopback server on a fresh fixture brain, shared by the tests of one class."""

    files_wait = False

    @classmethod
    def setUpClass(cls):
        cls.vault = fixture.build(files_wait=cls.files_wait)
        cls.brain = Brain(cls.vault, embeddings=False)
        cls.server, url, cls.token = http_server.start(cls.brain, 0)
        cls.base = url.split("/#", 1)[0]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.brain.close()
        fixture.remove(cls.vault)

    def request(self, path, body=None, token=True):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method="POST" if data else "GET")
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("X-Brain-Token", self.token)
        try:
            with urllib.request.urlopen(req, timeout=20) as res:
                return res.status, json.loads(res.read().decode())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read().decode() or "{}")


class HTTPTests(HTTPServerCase):
    def test_token_required_and_ui_served(self):
        status, _ = self.request("/api/status", token=False)
        self.assertEqual(status, 401)
        with urllib.request.urlopen(self.base + "/", timeout=10) as res:
            self.assertIn(b"<title>Brain</title>", res.read())

    def test_review_flow_over_http(self):
        status, body = self.request("/api/status")
        self.assertEqual((status, body["pending"]), (200, 0))
        status, created = self.request("/api/notes", {"layer": "facts", "topic": "services",
                                                      "scope": "company",
                                                      "text": "Retainers renew quarterly."})
        self.assertEqual(status, 200, created)
        proposal = created["data"]["proposal_id"]
        status, inbox = self.request("/api/inbox")
        self.assertEqual([p["id"] for p in inbox["data"]["proposals"]], [proposal])
        status, decided = self.request("/api/inbox/decide",
                                       {"decisions": [{"id": proposal, "action": "approve"}]})
        self.assertEqual(status, 200, decided)
        self.assertIn(created["data"]["id"], self.brain.state().index.notes)
        status, preview = self.request("/api/context", {"request": "When do retainers renew?"})
        self.assertEqual(status, 200)
        self.assertIn("Retainers renew quarterly", preview["text"])
        status, focus = self.request("/api/focus/state-focus-website-redesign/update",
                                     {"summary": "QA pass", "changes": {"next": "Launch"}})
        self.assertEqual(status, 200, focus)


class HTTPUploadTests(HTTPServerCase):
    """Uploads over the JSON API, on a server of their own (they leave proposals behind)."""

    files_wait = True

    def test_files_skills_and_sync_over_http(self):
        status, created = self.request("/api/files", {
            "filename": "rates.md", "content": "# Studio rates\n\nDay rate: 900.",
            "title": "Studio rates"})
        self.assertEqual(status, 200, created)
        self.assertEqual(created["data"]["status"], "pending")
        status, inbox = self.request("/api/inbox")
        row = next(p for p in inbox["data"]["proposals"] if p["kind"] == "file.add")
        self.assertIn("Day rate", row["preview"])
        status, applied = self.request("/api/skills", {
            "name": "kickoff", "category": "design", "description": "Run a client kickoff.",
            "body": "# /kickoff\n\n1. Agenda.\n", "apply": True})
        self.assertEqual(status, 200, applied)
        self.assertIn("kickoff", self.brain.state().index.skills)
        status, swept = self.request("/api/sync", {})
        self.assertEqual(status, 200, swept)


class OwnerOnlyDecisionTests(unittest.TestCase):
    def test_decide_batch(self):
        vault = fixture.build()
        brain = Brain(vault, embeddings=False)
        try:
            a = brain.propose(layer="facts", topic="services", scope="company", text="A one.")
            b = brain.propose(layer="facts", topic="services", scope="company", text="B two.")
            res = governance.decide(brain, [{"id": a.data["proposal_id"], "action": "approve"},
                                            {"id": b.data["proposal_id"], "action": "reject",
                                             "reason": "no"}])
            self.assertFalse(res.is_error, res.text)
            self.assertEqual(brain.inbox().data["proposals"], [])
        finally:
            brain.close()
            fixture.remove(vault)


if __name__ == "__main__":
    unittest.main()
