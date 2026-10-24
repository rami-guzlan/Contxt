"""The n8n workflows Gnomon suggests for the connectors it finds: one per known app, built by
code (no tokens), each a schedule, the app's own read node, a step that shapes what it read
into the heartbeat's items, and the post to the connector's inbox. Every one passes the
read-only check. The person signs in to the app on its node in n8n; nothing here holds a
sign-in. An app without a template is listed, for the knowledge agent to draft one later."""

from __future__ import annotations

from typing import Any

# app id: (words in a connector's name that mean it, the label, the n8n node, its read
# operation, extra parameters, how its items map to the heartbeat's {id, title, text, at,
# url, speaker})
APPS: dict[str, tuple[tuple[str, ...], str, str, str, dict[str, Any], dict[str, str]]] = {
    "gmail": (
        ("gmail",),
        "Gmail",
        "n8n-nodes-base.gmail",
        "getAll",
        {"resource": "message", "limit": 25, "filters": {"q": "newer_than:1h"}},
        {
            "id": "id",
            "title": "Subject",
            "text": "snippet",
            "at": "internalDate",
            "speaker": "From",
        },
    ),
    "google-calendar": (
        ("google calendar", "gcal"),
        "Google Calendar",
        "n8n-nodes-base.googleCalendar",
        "getAll",
        {
            "resource": "event",
            "limit": 25,
            "options": {"updatedMin": "={{ $now.minus(1, 'hour') }}"},
        },
        {"id": "id", "title": "summary", "text": "description", "at": "updated", "url": "htmlLink"},
    ),
    "google-drive": (
        ("google drive", "drive"),
        "Google Drive",
        "n8n-nodes-base.googleDrive",
        "search",
        {"resource": "fileFolder", "limit": 25, "filter": {"whatToSearch": "files"}},
        {"id": "id", "title": "name", "text": "name", "at": "modifiedTime", "url": "webViewLink"},
    ),
    "hubspot": (
        ("hubspot",),
        "HubSpot",
        "n8n-nodes-base.hubspot",
        "getRecentlyCreatedUpdated",
        {"resource": "deal", "limit": 25},
        {
            "id": "dealId",
            "title": "properties.dealname.value",
            "text": "properties.dealstage.value",
        },
    ),
    "notion": (
        ("notion",),
        "Notion",
        "n8n-nodes-base.notion",
        "search",
        {"resource": "page", "limit": 25},
        {"id": "id", "title": "name", "text": "url", "at": "last_edited_time", "url": "url"},
    ),
    "slack": (
        ("slack",),
        "Slack",
        "n8n-nodes-base.slack",
        "history",
        {"resource": "channel", "limit": 25},
        {"id": "ts", "title": "text", "text": "text", "at": "ts", "speaker": "user"},
    ),
    "linear": (
        ("linear",),
        "Linear",
        "n8n-nodes-base.linear",
        "getAll",
        {"resource": "issue", "limit": 25},
        {"id": "id", "title": "title", "text": "description", "at": "updatedAt", "url": "url"},
    ),
    "github": (
        ("github",),
        "GitHub",
        "n8n-nodes-base.github",
        "getIssues",
        {"resource": "repository", "limit": 25},
        {"id": "id", "title": "title", "text": "body", "at": "updated_at", "url": "html_url"},
    ),
}


def app_of(connector_name: str) -> str | None:
    """The app a connector reads, by its name ("claude.ai Gmail", "slack"), or None."""
    said = connector_name.lower()
    for app, (words, *_rest) in APPS.items():
        if any(w in said for w in words):
            return app
    return None


def label_of(app: str) -> str:
    return APPS[app][1]


def workflow_for(app: str, connector_id: str, inbox_url: str) -> dict[str, Any]:
    """The suggested workflow for one app: hourly, read, shape, post to the inbox."""
    _words, label, node, operation, extra, fields = APPS[app]
    assignments = [
        {"id": key, "name": key, "type": "string", "value": "={{ $json." + path + " }}"}
        for key, path in fields.items()
    ]
    return {
        "name": f"Gnomon reads {label}",
        "nodes": [
            {
                "id": "trigger",
                "name": "Every hour",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1.2,
                "position": [0, 0],
                "parameters": {"rule": {"interval": [{"field": "hours"}]}},
            },
            {
                "id": "read",
                "name": f"Read {label}",
                "type": node,
                "typeVersion": 1,
                "position": [220, 0],
                "parameters": {"operation": operation, **extra},
            },
            {
                "id": "shape",
                "name": "As Gnomon items",
                "type": "n8n-nodes-base.set",
                "typeVersion": 3.4,
                "position": [440, 0],
                "parameters": {"mode": "manual", "assignments": {"assignments": assignments}},
            },
            {
                "id": "post",
                "name": "To Gnomon",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 4.2,
                "position": [660, 0],
                "executeOnce": True,  # one post with every item, not one per item
                "parameters": {
                    "method": "POST",
                    "url": inbox_url.rstrip("/") + f"/api/heartbeat/inbox/{connector_id}",
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ { items: $input.all().map(i => i.json) } }}",
                },
            },
        ],
        "connections": {
            "Every hour": {"main": [[{"node": f"Read {label}", "type": "main", "index": 0}]]},
            f"Read {label}": {"main": [[{"node": "As Gnomon items", "type": "main", "index": 0}]]},
            "As Gnomon items": {"main": [[{"node": "To Gnomon", "type": "main", "index": 0}]]},
        },
        "settings": {"executionOrder": "v1"},
    }
