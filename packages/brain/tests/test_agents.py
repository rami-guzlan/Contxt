"""Agents: roles kept in the Brain as agents/<name>/AGENT.md. Saved by the owner as one undo
point; checked (a line saying what it does, a known output and runner, a declared scope);
assembled with every pointer resolved to what it is now, naming what no longer resolves; hidden
when archived; and taken on by any connected AI through MCP agents_get.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from brainkit import agents, mcp_server  # noqa: E402
from brainkit import frontmatter as fm  # noqa: E402
from brainkit.api import Brain  # noqa: E402
from tests import fixture  # noqa: E402

ROLE = {
    "role": "Writes the studio's case studies from finished projects.",
    "responsibilities": ["Draft one case study a month", "Check every number against its source"],
    "skills": ["brand-sheet", "no-such-skill"],
    "library": ["references/style-guide.md"],
    "context": ["rules/style", "facts"],
    "projects": ["state-focus-studio-podcast"],
    "output": "outputs",
    "output_shape": "A one-page case study in Markdown.",
}
PROMPT = "You write case studies the way a senior designer explains their work to a peer."


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.vault = fixture.build(os.path.join(self.tmp, "brain"))
        self.brain = Brain(self.vault, embeddings=False)

    def tearDown(self):
        self.brain.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def save(self, name="case-writer", fields=None, prompt=PROMPT):
        return self.brain.save_agent(name, dict(ROLE, **(fields or {})), prompt)

    def test_an_agent_is_kept_as_a_file_with_its_role_and_prompt(self):
        saved = self.save()
        self.assertFalse(saved.is_error, saved.text)
        self.assertTrue(saved.data["checkpoint"])
        path = os.path.join(self.vault, "agents", "case-writer", "AGENT.md")
        with open(path, encoding="utf-8") as handle:
            meta, body, _errors = fm.parse(handle.read())
        self.assertEqual(meta["role"], ROLE["role"])
        self.assertEqual(meta["skills"], ["brand-sheet", "no-such-skill"])
        self.assertEqual(meta["boundaries"], list(agents.DEFAULT_BOUNDARIES))
        self.assertTrue(fm.as_bool(meta["review"]))
        self.assertEqual(body.strip(), PROMPT)
        listed = self.brain.agents().data["agents"]
        self.assertEqual([a["name"] for a in listed], ["case-writer"])

    def test_its_prompt_points_to_each_thing_as_it_is_now(self):
        self.save()
        found = self.brain.agent("case-writer")
        self.assertFalse(found.is_error, found.text)
        resolved = found.data["resolved"]
        self.assertEqual(resolved["broken"], ["/no-such-skill"])
        self.assertEqual([c["missing"] for c in resolved["context"]], [False, False])
        prompt = found.text
        self.assertIn("# You are working as case-writer", prompt)
        self.assertIn(PROMPT, prompt)
        self.assertIn("/brand-sheet", prompt)
        self.assertIn("references/style-guide.md", prompt)
        self.assertIn("Project ", prompt)
        self.assertIn("no longer resolve: /no-such-skill", prompt)
        self.assertIn("Never publish, send or post anything", prompt)
        self.assertIn("A one-page case study in Markdown.", prompt)
        self.assertNotIn("no-such-skill (", prompt)  # never listed as a skill to follow

    def test_the_role_is_checked_before_anything_is_written(self):
        for fields, why in (
            ({"role": ""}, "role"),
            ({"output": "email"}, "output is one of"),
            ({"runner": "gpt"}, "runner is"),
            ({"meetings_days": 400}, "meetings_days"),
            ({"scope": "person:nobody"}, "not declared"),
        ):
            res = self.save(fields=fields)
            self.assertTrue(res.is_error, fields)
            self.assertIn(why, res.text)
        self.assertTrue(self.save(name="Case Writer").is_error)
        self.assertFalse(os.path.isdir(os.path.join(self.vault, "agents")))
        local = self.save(fields={"runner": "ollama:qwen3:1.7b"})
        self.assertFalse(local.is_error, local.text)

    def test_archiving_hides_it_and_keeps_its_file(self):
        self.save()
        done = self.brain.archive_agent("case-writer")
        self.assertFalse(done.is_error, done.text)
        self.assertEqual(self.brain.agents().data["agents"], [])
        self.assertEqual([a["status"] for a in self.brain.agents(archived=True).data["agents"]],
                         ["archived"])
        again = self.save(fields={"role": "Writes case studies again."})
        self.assertFalse(again.is_error)
        self.assertEqual(self.brain.agent("case-writer").data["agent"]["status"], "active")

    def test_undo_takes_a_change_back(self):
        self.save()
        changed = self.save(fields={"role": "Writes short case studies."})
        undone = self.brain.undo(changed.data["checkpoint"]["id"])
        self.assertFalse(undone.is_error, undone.text)
        self.assertEqual(self.brain.agent("case-writer").data["agent"]["role"], ROLE["role"])

    def test_versions_list_what_is_saved(self):
        self.save()
        rows = self.brain.agent_versions("case-writer").data["versions"]
        self.assertTrue(rows and rows[0]["current"])
        self.assertTrue(self.brain.agent_versions("nobody").is_error)

    def test_a_connected_ai_takes_an_agent_on_through_mcp(self):
        self.save()
        server = mcp_server.Server(self.brain)
        listed = server.call("agents_list", {})
        self.assertIn("case-writer: Writes the studio's case studies", listed.text)
        taken = server.call("agents_get", {"name": "case-writer", "session_id": "s-1"})
        self.assertFalse(taken.is_error, taken.text)
        self.assertIn("# You are working as case-writer", taken.text)
        self.assertIn("call gnomon_get_context with the request and session_id s-1", taken.text)
        self.assertTrue(server.call("agents_get", {"name": "nobody"}).is_error)

    def test_work_procedures_ship_with_the_engine(self):
        builder = self.brain.work_skill("agent-builder")
        self.assertFalse(builder.is_error)
        self.assertIn("operating prompt", builder.data["text"])
        self.assertIn("prompt", self.brain.work_skill("prompt-improver").data["text"])
        self.assertTrue(self.brain.work_skill("tidy-repeats").is_error)


if __name__ == "__main__":
    unittest.main()
