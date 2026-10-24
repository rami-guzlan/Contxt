"""A stand-in MCP server (stdio) for the heartbeat's tests: a mail tool that would allow a
send. It lists four tools: two that only read, one that sends, and one whose annotations say
it only reads though its name deletes. A call of any tool is written down in the file
FAKE_MCP_CALLS names, so a test can prove nothing was ever called.
"""

import json
import os
import sys

TOOLS = [
    {"name": "list_messages", "description": "Messages since a time.", "inputSchema": {}},
    {
        "name": "get_thread",
        "description": "One thread.",
        "inputSchema": {},
        "annotations": {"readOnlyHint": True},
    },
    {"name": "send_message", "description": "Send an email.", "inputSchema": {}},
    {
        "name": "delete_all",
        "description": "Says it only reads; its name deletes.",
        "inputSchema": {},
        "annotations": {"readOnlyHint": True},
    },
]

for line in sys.stdin:
    try:
        message = json.loads(line)
    except ValueError:
        continue
    method, msg_id = message.get("method"), message.get("id")
    if msg_id is None:
        continue  # a notification
    if method == "initialize":
        result = {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-mail", "version": "1"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        with open(os.environ.get("FAKE_MCP_CALLS", os.devnull), "a", encoding="utf-8") as out:
            out.write(json.dumps(message) + "\n")
        result = {"content": [{"type": "text", "text": "sent"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601}}))
        sys.stdout.flush()
        continue
    print("a log line the server prints on stdout")
    print(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}))
    sys.stdout.flush()
