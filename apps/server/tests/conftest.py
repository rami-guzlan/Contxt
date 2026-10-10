import os
import sys
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from workspace_core.clock import FixedClock
from workspace_server.app import create_app, open_runtime
from workspace_server.settings import Settings

BRAIN_PACKAGE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "packages", "brain")
)
if BRAIN_PACKAGE not in sys.path:
    sys.path.insert(0, BRAIN_PACKAGE)

from tests import fixture as brain_fixture  # noqa: E402  (the brain's sample vault)

OWNER_TOKEN = "wst_" + "owner-token-for-tests-" + "x" * 20


class Api:
    """A TestClient that speaks as one credential."""

    def __init__(self, client: TestClient, token: str | None) -> None:
        self.client = client
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def get(self, path, **kw):
        return self.client.get(path, headers=self.headers, **kw)

    def post(self, path, json=None, **kw):
        headers = dict(self.headers, **kw.pop("headers", {}))
        return self.client.post(path, json=json, headers=headers, **kw)

    def patch(self, path, json=None):
        return self.client.patch(path, json=json, headers=self.headers)

    def put(self, path, json=None):
        return self.client.put(path, json=json, headers=self.headers)

    def delete(self, path):
        return self.client.delete(path, headers=self.headers)

    def ok(self, response, status=200):
        assert response.status_code == status, response.text
        return response.json() if response.content else None

    def mcp(self, method, params=None, msg_id=1, version="2025-06-18"):
        message = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}
        headers = dict(self.headers, **{"MCP-Protocol-Version": version})
        response = self.client.post("/mcp", json=message, headers=headers)
        assert response.status_code == 200, response.text
        return response.json()

    def tool(self, tool_name, /, **arguments):
        reply = self.mcp("tools/call", {"name": tool_name, "arguments": arguments})
        return reply["result"]


def _setting(name: str) -> bool:
    return name.startswith(("CONTXT_", "WORKSPACE_")) or name == "BRAIN_VAULT"


@pytest.fixture(autouse=True)
def no_live_configuration(monkeypatch):
    """Tests never inherit a developer's live Contxt (a real data folder or Brain), and what
    a test loads from a home's .env never outlives it."""
    for name in list(os.environ):
        if _setting(name):
            monkeypatch.delenv(name, raising=False)
    # No local model service: retrieval runs as it does without one, whatever this machine
    # runs (the engine's own tests point it at a stand-in service).
    monkeypatch.setenv("BRAIN_MODEL_SERVICE", "off")
    yield
    for name in list(os.environ):
        if _setting(name):
            os.environ.pop(name, None)


@pytest.fixture
def owner_token():
    return OWNER_TOKEN


@pytest.fixture
def brain_vault(tmp_path):
    """A fresh copy of the brain's sample vault (a small design studio)."""
    return brain_fixture.build(str(tmp_path / "brain"))


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 9, 28, 13, 0, tzinfo=UTC))


@pytest.fixture
def runtime(tmp_path, clock, brain_vault):
    settings = Settings(
        data_dir=str(tmp_path / "data"),
        brain_vault=brain_vault,
        owner_token=OWNER_TOKEN,
        name="Test workspace",
        timezone="America/New_York",
        exports_dir=str(tmp_path / "exports"),
        web_dist=str(tmp_path / "web-dist"),
    )
    opened = open_runtime(settings, clock=clock)
    yield opened
    opened.close()


@pytest.fixture
def client(runtime):
    with TestClient(create_app(runtime=runtime)) as test_client:
        yield test_client


@pytest.fixture
def owner(client):
    return Api(client, OWNER_TOKEN)


@pytest.fixture
def model(owner):
    created = owner.ok(
        owner.post("/api/connections", json={"name": "Claude Code", "provider": "claude-code"}), 201
    )
    api = Api(owner.client, created["token"])
    api.actor_id = created["actor"]["id"]
    api.connection = created
    return api


@pytest.fixture
def project(runtime):
    """A workspace project: the task bus's own boundary (people see the Brain's projects)."""
    ws = runtime.ws
    made = ws.projects.create(ws.owner(), title="Website redesign", summary="New site in Figma")
    return made.to_dict()


@pytest.fixture
def note(owner):
    return owner.ok(
        owner.post(
            "/api/notes",
            json={"title": "Client notes", "body": "Clients prefer async reviews on Fridays."},
        ),
        201,
    )


@pytest.fixture
def make_task(runtime):
    """AI work as the app starts it, ready for `assignee` (the bus does not care which)."""

    def _make(
        assignee_id,
        *,
        title="Find what to remember",
        instructions="Read the pinned notes and propose what will last.",
        **fields,
    ):
        ws = runtime.ws
        owner = ws.owner()
        task = ws.tasks.create(
            owner,
            title=title,
            instructions=instructions,
            assignee_id=assignee_id,
            schedule={"kind": "manual"},
            output_contract={"artifacts": [], "tool": "propose_brain_entry"},
            review_policy="auto",
            **fields,
        )
        return ws.tasks.mark_ready(owner, task.id).to_dict()

    return _make
