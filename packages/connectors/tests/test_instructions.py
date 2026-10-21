"""Ask the Brain first is installed and removed between markers, leaving the rest of the
app's own instructions file as it was (Release 1 plan, M08)."""

from workspace_connectors import instructions
from workspace_connectors.providers import BRAIN_INSTRUCTION


def test_install_appends_between_markers_and_remove_restores_the_file(tmp_path):
    path = tmp_path / ".claude" / "CLAUDE.md"
    path.parent.mkdir()
    path.write_text("# My rules\n\nUse British spelling.\n", encoding="utf-8")
    found = instructions.install("claude-code", home=str(tmp_path))
    assert found["installed"] and found["path"] == str(path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# My rules\n\nUse British spelling.\n")
    assert BRAIN_INSTRUCTION in text and text.count(instructions.START) == 1
    instructions.install("claude-code", home=str(tmp_path))  # again: still one block
    assert path.read_text(encoding="utf-8").count(instructions.START) == 1
    assert not instructions.remove("claude-code", home=str(tmp_path))["installed"]
    assert path.read_text(encoding="utf-8") == "# My rules\n\nUse British spelling.\n"


def test_a_new_file_is_made_and_an_app_without_one_says_so(tmp_path):
    assert instructions.install("codex", home=str(tmp_path))["installed"]
    assert (
        (tmp_path / ".codex" / "AGENTS.md")
        .read_text(encoding="utf-8")
        .startswith(instructions.START)
    )
    assert instructions.status("claude-desktop", home=str(tmp_path))["supported"] is False
