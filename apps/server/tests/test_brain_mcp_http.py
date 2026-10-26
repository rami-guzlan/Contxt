"""The Brain's own MCP tools, served by the running app at /brain/mcp: an AI app on this computer
connects by URL with its own token, instead of starting the Brain itself."""


def post(client, message, token=None, **headers):
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.post("/brain/mcp", json=message, headers=headers)


def test_an_ai_app_connects_by_url_with_its_token_and_gets_the_brains_tools(owner, model):
    token = model.connection["token"]
    hello = post(
        owner.client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "Claude Code"}},
        },
        token,
    )
    assert hello.status_code == 200, hello.text
    assert hello.json()["result"]["serverInfo"]["name"] == "brain"
    assert (
        post(
            owner.client, {"jsonrpc": "2.0", "method": "notifications/initialized"}, token
        ).status_code
        == 202
    )
    tools = post(owner.client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, token)
    names = {t["name"] for t in tools.json()["result"]["tools"]}
    assert {"gnomon_get_context", "notes", "projects"} <= names  # one tool per area
    packet = post(
        owner.client,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "gnomon_get_context", "arguments": {"request": "What is our tone?"}},
        },
        token,
    ).json()["result"]
    assert not packet["isError"] and "session_id" in packet["content"][0]["text"]


def test_without_a_token_or_from_a_foreign_page_it_is_refused(owner, model):
    asked = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    refused = post(owner.client, asked)
    assert refused.status_code == 401 and refused.headers["WWW-Authenticate"] == "Bearer"
    assert post(owner.client, asked, "not-a-token").status_code == 401
    foreign = post(owner.client, asked, model.connection["token"], Origin="https://evil.example")
    assert foreign.status_code == 403


def test_a_batch_and_a_bad_message_get_plain_answers(owner, model):
    token = model.connection["token"]
    both = post(
        owner.client,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        ],
        token,
    )
    assert [r["id"] for r in both.json()] == [1, 2]
    bad = owner.client.post(
        "/brain/mcp", content=b"{not json", headers={"Authorization": f"Bearer {token}"}
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == -32700
    assert owner.client.get("/brain/mcp").status_code == 405
