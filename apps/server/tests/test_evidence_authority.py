"""Authority and effective dates survive the engine/workspace/MCP boundary."""

from unittest.mock import Mock

from workspace_server.brain_adapter import BrainKitAdapter
from workspace_server.mcp.tools import get_brain_entry, search_context


def test_workspace_reads_keep_authority_date_and_matching_passage(brain_vault):
    adapter = BrainKitAdapter(brain_vault)
    try:
        made = adapter.brain.propose(
            layer="facts",
            topic="services",
            scope="person:alex",
            text="Workshop notes. The ceramic kiln needs six hours.",
            extra={"said_by": "agent"},
            as_of="2024-03-02",
            force_pending=True,
        )
        assert not adapter.brain.approve(made.data["proposal_id"]).is_error
        ident = made.data["id"]
        entry = adapter.entry(ident)
        assert entry is not None
        assert entry.said_by == "agent" and entry.as_of == "2024-03-02"
        hit = next(h for h in adapter.search("ceramic kiln") if h.id == ident)
        assert "kiln needs six hours" in hit.excerpt
        ws, who = Mock(), Mock()
        ws.brain.entry.return_value = entry
        text, data = get_brain_entry(ws, who, {"entry_id": ident})
        assert "Said by: agent" in text and "As of: 2024-03-02" in text
        assert data["entry"]["said_by"] == "agent"
        ws.context.search.return_value = []
        ws.brain.search.return_value = [hit]
        text, _ = search_context(ws, who, {"query": "ceramic kiln"})
        assert "kiln needs six hours" in text
    finally:
        adapter.close()
