import json

from workspace_connectors.destinations import FolderDestination
from workspace_connectors.providers import PROVIDERS, mcp_setup
from workspace_core.domain.records import Artifact, ArtifactVersion


def _artifact(project_id="proj_1"):
    return Artifact(
        id="art_1",
        goal_id=None,
        project_id=project_id,
        task_id=None,
        run_id=None,
        type="document",
        title="Brief",
        status="approved",
        current_version=1,
        created_by="act_1",
        created_at="t",
        updated_at="t",
        version=1,
        archived_at=None,
    )


def _version(filename="brief-v1.md"):
    return ArtifactVersion(
        id="artv_1",
        artifact_id="art_1",
        number=1,
        object_key="0" * 64,
        filename=filename,
        mime="text/markdown",
        size=3,
        content_hash="0" * 64,
        preview_text=None,
        run_id=None,
        task_revision=None,
        prompt_version=None,
        inputs=[],
        context_used=[],
        note=None,
        created_by="act_1",
        created_at="t",
    )


def _read(path):
    with open(path, "rb") as handle:
        return handle.read()


def test_folder_destination_writes_once_and_never_overwrites(tmp_path):
    destination = FolderDestination(str(tmp_path))
    first = destination.deliver(artifact=_artifact(), version=_version(), data=b"one")
    assert _read(first["location"]) == b"one"
    same = destination.deliver(artifact=_artifact(), version=_version(), data=b"one")
    assert same["unchanged"] and same["location"] == first["location"]
    other = destination.deliver(artifact=_artifact(), version=_version(), data=b"two")
    assert other["location"] != first["location"]
    assert _read(first["location"]) == b"one"


def test_folder_destination_keeps_names_inside_its_root(tmp_path):
    destination = FolderDestination(str(tmp_path))
    result = destination.deliver(
        artifact=_artifact("../../etc"), version=_version("../../passwd"), data=b"x"
    )
    assert result["location"].startswith(str(tmp_path))


def test_every_provider_has_a_setup():
    for provider_id in PROVIDERS:
        setup = mcp_setup(provider_id, url="http://127.0.0.1:8787", token="wst_secret")
        assert setup["url"] == "http://127.0.0.1:8787/mcp"
        assert "wst_secret" in setup["config"]


def test_claude_code_setup_is_valid_json_over_http():
    setup = mcp_setup("claude-code", url="http://127.0.0.1:8787/", token="wst_x")
    config = json.loads(setup["config"])["mcpServers"]["contxt-app"]
    assert config == {
        "type": "http",
        "url": "http://127.0.0.1:8787/mcp",
        "headers": {"Authorization": "Bearer wst_x"},
    }
    assert setup["command"].startswith("claude mcp add --transport http contxt-app")


def test_without_a_token_the_setup_shows_a_placeholder():
    assert "<your token>" in mcp_setup("codex", url="http://localhost:8787")["config"]
