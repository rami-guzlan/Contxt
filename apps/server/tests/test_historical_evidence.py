"""Historical tools must read the requested original without crossing visibility scopes."""

from workspace_server.brain_adapter import BrainKitAdapter


def test_workspace_mcp_can_find_and_open_the_original_history(owner, brain_vault):
    adapter = BrainKitAdapter(brain_vault)
    try:
        for ident, status, scope, text, extra in (
            (
                "earlier-kiln",
                "archived",
                "person:alex",
                "The kiln reservation lasts six hours.",
                {"superseded_by": "current-kiln"},
            ),
            (
                "current-kiln",
                "approved",
                "person:alex",
                "The kiln reservation now lasts eight hours.",
                {},
            ),
            ("private-kiln", "archived", "person:sam", "The kiln passcode is private.", {}),
        ):
            meta = dict(
                id=ident,
                layer="facts",
                topic="services",
                scope=scope,
                status=status,
                load="on-demand",
                title=ident,
                **extra,
            )
            adapter.brain.vault.write_note(f"knowledge/history/{ident}.md", meta, text)
        normal = owner.tool("get_brain_entry", entry_id="earlier-kiln")
        assert "eight hours" in normal["content"][0]["text"]
        history = owner.tool("get_brain_entry", entry_id="earlier-kiln", include_archived=True)
        assert not history.get("isError"), history
        assert "six hours" in history["content"][0]["text"]
        found = owner.tool("search_context", query="kiln reservation", include_archived=True)
        assert "earlier-kiln" in found["content"][0]["text"]
        assert "private-kiln" not in found["content"][0]["text"]
        denied = owner.tool("get_brain_entry", entry_id="private-kiln", include_archived=True)
        assert denied.get("isError")
    finally:
        adapter.close()
