"""Reads through n8n: a workflow on this computer reads an app with the person's own n8n
credentials and posts what changed to Gnomon's inbox, so a read costs no tokens.

Read-only, by code: every node of a workflow must be on READ_NODES, with an operation listed
there for app nodes. A node type that isn't listed, an operation that isn't a read, a Code or
Function node (it could do anything), or an HTTP request that isn't the one post to this
connector's inbox, and the workflow is refused. The check runs before a workflow is approved
and again on every change.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from typing import Any

SECRET_HEADER = "x-gnomon-secret"
ERROR_WORKFLOW = "gnomonerrors"  # Gnomon's own workflow in its n8n that reports failures
ERROR_PATH = "/api/heartbeat/n8n/errors"

# Nodes that only start a workflow or shape its items.
SHAPING = frozenset(
    {
        "n8n-nodes-base.scheduleTrigger",
        "n8n-nodes-base.manualTrigger",
        "n8n-nodes-base.cron",
        "n8n-nodes-base.set",
        "n8n-nodes-base.filter",
        "n8n-nodes-base.if",
        "n8n-nodes-base.switch",
        "n8n-nodes-base.merge",
        "n8n-nodes-base.noOp",
        "n8n-nodes-base.limit",
        "n8n-nodes-base.sort",
        "n8n-nodes-base.splitOut",
        "n8n-nodes-base.aggregate",
        "n8n-nodes-base.removeDuplicates",
        "n8n-nodes-base.dateTime",
        "n8n-nodes-base.renameKeys",
        "n8n-nodes-base.itemLists",
        "n8n-nodes-base.stickyNote",
    }
)

# App nodes and the operations of theirs that only read. An app node without an operation
# here is refused, whatever it would do.
READ_NODES: dict[str, frozenset[str]] = {
    "n8n-nodes-base.gmail": frozenset({"get", "getAll"}),
    "n8n-nodes-base.googleCalendar": frozenset({"get", "getAll", "getAvailability"}),
    "n8n-nodes-base.googleDrive": frozenset({"search", "list", "get", "download"}),
    "n8n-nodes-base.googleSheets": frozenset({"read", "get", "getAll", "lookup"}),
    "n8n-nodes-base.hubspot": frozenset({"get", "getAll", "search", "getRecentlyCreatedUpdated"}),
    "n8n-nodes-base.notion": frozenset({"get", "getAll", "search", "getMany"}),
    "n8n-nodes-base.slack": frozenset({"get", "getAll", "history", "search", "replies"}),
    "n8n-nodes-base.linear": frozenset({"get", "getAll"}),
    "n8n-nodes-base.airtable": frozenset({"get", "search", "list"}),
    "n8n-nodes-base.microsoftOutlook": frozenset({"get", "getAll"}),
    "n8n-nodes-base.github": frozenset({"get", "getAll", "getIssues", "getRepositories"}),
    "n8n-nodes-base.rssFeedRead": frozenset({""}),  # reads a feed; it has no operation
}

HTTP = "n8n-nodes-base.httpRequest"
INBOX_PATH = re.compile(r"^/api/heartbeat/inbox/([A-Za-z0-9:_.-]+)$")


def new_secret() -> tuple[str, str]:
    """(the secret the workflow sends, the hash Gnomon keeps)."""
    secret = secrets.token_urlsafe(32)
    return secret, secret_hash(secret)


def secret_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def secret_ok(given: str, kept: str | None) -> bool:
    return bool(kept) and hmac.compare_digest(secret_hash(given or ""), kept or "")


def _inbox_target(url: str) -> str | None:
    """The connector a local inbox URL posts to, or None for any other address."""
    match = re.match(r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?(/[^?#]*)$", url or "")
    if not match:
        return None
    found = INBOX_PATH.match(match.group(3))
    return found.group(1) if found else None


def check_workflow(workflow: Any, connector_id: str) -> list[str]:
    """Why this workflow may not run as a read for `connector_id`, in words (empty: it may)."""
    if not isinstance(workflow, dict):
        return ["A workflow is a JSON object with its nodes."]
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return ["The workflow has no nodes."]
    problems: list[str] = []
    posts = 0
    for node in nodes:
        if not isinstance(node, dict):
            problems.append("A node is not an object.")
            continue
        kind = str(node.get("type") or "")
        name = str(node.get("name") or kind or "a node")
        given = node.get("parameters")
        params: dict[str, Any] = given if isinstance(given, dict) else {}
        if kind in SHAPING:
            continue
        if kind == HTTP:
            method = str(params.get("method") or "GET").upper()
            target = _inbox_target(str(params.get("url") or ""))
            if method == "POST" and target == connector_id:
                posts += 1
                continue
            problems.append(
                f"{name}: an HTTP request may only post to this connector's inbox on this computer."
            )
            continue
        allowed = READ_NODES.get(kind)
        if allowed is None:
            problems.append(f"{name}: {kind or 'this node'} is not a node Gnomon knows only reads.")
            continue
        operation = str(params.get("operation") or "")
        if operation not in allowed:
            problems.append(
                f"{name}: the {operation or 'default'} operation is not a read "
                f"(it may only {', '.join(sorted(o for o in allowed if o)) or 'read'})."
            )
    if posts != 1:
        problems.append("The workflow must post its items to this connector's inbox, once.")
    return problems


def items_of(body: Any) -> list[dict[str, Any]]:
    """The items a workflow posted: a list, or {"items": [...]}; each in the read shape."""
    raw = body.get("items") if isinstance(body, dict) else body
    out: list[dict[str, Any]] = []
    for entry in raw if isinstance(raw, list) else []:
        if not isinstance(entry, dict):
            continue
        wrapped = entry.get("json")  # n8n's own wrapping of an item
        item: dict[str, Any] = wrapped if isinstance(wrapped, dict) else entry
        if str(item.get("id") or "").strip():
            out.append(item)
    return out


def prepare(
    workflow: dict[str, Any], connector_id: str, inbox_url: str, secret: str
) -> dict[str, Any]:
    """The copy of a workflow that goes into n8n: a stable id, its post aimed at this
    connector's inbox on this computer, with the secret it sends in a header. The secret lives
    only in n8n's copy; Gnomon keeps its hash."""
    copy = json.loads(json.dumps(workflow))
    copy["id"] = "gnomon" + hashlib.sha256(connector_id.encode("utf-8")).hexdigest()[:10]
    copy.setdefault("name", f"Gnomon: {connector_id}")
    copy.setdefault("connections", {})
    settings = copy.setdefault("settings", {})
    settings["errorWorkflow"] = ERROR_WORKFLOW  # a failure is reported to Gnomon
    for node in copy.get("nodes") or []:
        if isinstance(node, dict) and node.get("type") == HTTP:
            params = node.setdefault("parameters", {})
            params.update(
                method="POST",
                url=inbox_url.rstrip("/") + f"/api/heartbeat/inbox/{connector_id}",
                sendHeaders=True,
                headerParameters={"parameters": [{"name": SECRET_HEADER, "value": secret}]},
            )
    return copy


def error_reporter(inbox_url: str, secret: str) -> dict[str, Any]:
    """Gnomon's own workflow in its n8n: when one of Gnomon's workflows fails, it posts which
    one and why to Gnomon, with its own secret. It reads nothing and changes nothing else."""
    return {
        "id": ERROR_WORKFLOW,
        "name": "Gnomon: report a failure",
        "nodes": [
            {
                "id": "failed",
                "name": "A Gnomon workflow failed",
                "type": "n8n-nodes-base.errorTrigger",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "report",
                "name": "Tell Gnomon",
                "type": HTTP,
                "typeVersion": 4.2,
                "position": [220, 0],
                "parameters": {
                    "method": "POST",
                    "url": inbox_url.rstrip("/") + ERROR_PATH,
                    "sendHeaders": True,
                    "headerParameters": {"parameters": [{"name": SECRET_HEADER, "value": secret}]},
                    "sendBody": True,
                    "specifyBody": "json",
                    "jsonBody": "={{ $json }}",
                },
            },
        ],
        "connections": {
            "A Gnomon workflow failed": {
                "main": [[{"node": "Tell Gnomon", "type": "main", "index": 0}]]
            }
        },
        "settings": {"executionOrder": "v1"},
    }


def failure_of(body: Any) -> tuple[str, str]:
    """(the failed workflow's id, why, in a line) from what n8n's Error Trigger sends."""

    def part(of: Any, key: str) -> dict[str, Any]:
        found = of.get(key) if isinstance(of, dict) else None
        return found if isinstance(found, dict) else {}

    workflow, execution = part(body, "workflow"), part(body, "execution")
    error = part(execution, "error")
    message = str(error.get("message") or "it stopped with an error").strip()
    node = str(execution.get("lastNodeExecuted") or "").strip()
    return str(workflow.get("id") or ""), message[:300] + (f" (at {node})" if node else "")
