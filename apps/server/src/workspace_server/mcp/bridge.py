"""A stdio bridge to the HTTP MCP endpoint, for clients that only launch local commands.

    contxt mcp --url http://127.0.0.1:8787/mcp      (token in CONTXT_TOKEN)

Reads one JSON-RPC message per line on stdin, POSTs it with the bearer token, and writes the
reply on stdout. It remembers the negotiated protocol version and sends it on later requests.
Standard library only.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Any, TextIO


def forward(
    url: str, token: str, message: dict[str, Any], version: str | None, timeout: float = 120
) -> dict[str, Any] | None:
    body = json.dumps(message).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if version:
        headers["MCP-Protocol-Version"] = version
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        if "id" not in message:
            return None
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {"code": -32000, "message": f"HTTP {exc.code}: {detail}"},
        }
    except urllib.error.URLError as exc:
        if "id" not in message:
            return None
        return {
            "jsonrpc": "2.0",
            "id": message.get("id"),
            "error": {
                "code": -32000,
                "message": f"The workspace server is not reachable at {url}: {exc.reason}",
            },
        }
    if not raw.strip():
        return None
    reply: dict[str, Any] = json.loads(raw)
    return reply


def run(url: str, token: str, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    version: str | None = None
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            stdout.write(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                )
                + "\n"
            )
            stdout.flush()
            continue
        reply = forward(url, token, message, version)
        if message.get("method") == "initialize" and reply and "result" in reply:
            version = reply["result"].get("protocolVersion")
        if reply is not None:
            stdout.write(json.dumps(reply) + "\n")
            stdout.flush()
    return 0
