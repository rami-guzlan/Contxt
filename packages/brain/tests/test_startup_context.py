"""The startup context any reasoning model can operate the Brain from (the owner's list, item
6): the contract, then a short operating section, then the Brain map, then the constitution,
then the must-hold index; about 750 to 900 tokens with the map. The map comes once a session,
inside the startup context when it is sent, and after that only when it changed or after a
compaction."""
from __future__ import annotations

import unittest

from brainkit import brainmap, kernel, util
from brainkit.api import Brain
from tests import fixture


class StartupContextTest(unittest.TestCase):
    def setUp(self):
        self.vault = fixture.build()
        self.brain = Brain(self.vault, embeddings=False)
        st = self.brain.state()
        self.chain = st.scopes.chain(st.config.owner) or [st.scopes.root()]
        self.kernel = kernel.compile(st.config, st.index, st.scopes, self.chain)

    def tearDown(self):
        self.brain.close()
        fixture.remove(self.vault)

    def packet(self, request="What do we charge for a website?", **kw):
        found = self.brain.context(request, record=True, **kw)
        self.assertFalse(found.is_error, found.text)
        return found

    def test_the_operating_section_follows_the_contract_and_names_the_grouped_tools(self):
        text = self.kernel.shared
        start, operating = text.index("## Start"), text.index(kernel.OPERATING_HEADING)
        policy = text.index("## Action policy")
        self.assertLess(start, operating)
        self.assertLess(operating, policy)
        section = text[operating:policy]
        self.assertIn("Pull only what the task needs", section)
        self.assertIn('notes(action: "search")', section)
        self.assertIn('gnomon(action: "open"', section)
        self.assertIn('activity(action: "timeline"', section)  # for when and since
        self.assertNotIn("notes_search", section)
        self.assertLessEqual(util.tokens(section), 190)

    def test_a_tool_less_model_gets_no_operating_section(self):
        st = self.brain.state()
        bare = kernel.compile(st.config, st.index, st.scopes, self.chain, tools=False)
        self.assertNotIn(kernel.OPERATING_HEADING, bare.text)

    def test_the_first_packet_carries_the_map_inside_the_startup_context(self):
        found = self.packet()
        text = found.text
        self.assertIn("# Startup context", text)
        operating = text.index(kernel.OPERATING_HEADING)
        mapped = text.index(brainmap.HEADING)
        policy = text.index("## Action policy")
        self.assertLess(operating, mapped)
        self.assertLess(mapped, policy)
        self.assertEqual(text.count(brainmap.HEADING), 1)
        startup = text[text.index("# Startup context"):text.index("## Action policy")]
        whole = text[text.index("# Startup context"):]
        self.assertLessEqual(util.tokens(startup), 450)
        self.assertGreater(len(whole), len(startup))

    def test_the_startup_is_within_the_owner_s_size(self):
        st = self.brain.state()
        shown = brainmap.render(self.brain._brain_map(st, self.chain, ()), "")
        self.assertLessEqual(shown["tokens"], brainmap.MAP_TOKENS)
        self.assertLessEqual(self.kernel.tokens + shown["tokens"], 900)

    def test_a_client_holding_the_startup_gets_the_map_once_then_only_changes(self):
        first = self.packet(startup_fingerprint=self.kernel.fingerprint)
        self.assertNotIn("# Startup context", first.text)
        self.assertEqual(first.text.count(brainmap.HEADING), 1)
        session = first.data["session_id"]
        again = self.packet("And for a logo?", session_id=session,
                            startup_fingerprint=self.kernel.fingerprint)
        self.assertNotIn(brainmap.HEADING, again.text)
        after = self.packet("And for a logo?", session_id=session, fresh=True,
                            startup_fingerprint=self.kernel.fingerprint)
        self.assertIn(brainmap.HEADING, after.text)


if __name__ == "__main__":
    unittest.main()
