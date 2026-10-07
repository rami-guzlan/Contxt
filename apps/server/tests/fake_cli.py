"""A stand-in for the Claude Code CLI in tests: the commands the workspace calls, the
stream-json lines it reads, and a report of exactly how it was started.

FAKE_CLI_SIGNED_IN=0 answers as signed out. FAKE_CLI_MODE is ok (default), hang (waits to be
stopped) or fail (exits with an error on stderr). FAKE_CLI_MAKE names files (comma-separated,
relative to its folder) it makes there, as a run of a skill that makes files would.
"""

import json
import os
import sys
import time

args = sys.argv[1:]
if args[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    signed_in = os.environ.get("FAKE_CLI_SIGNED_IN", "1") == "1"
    print(json.dumps({"loggedIn": signed_in, "authMethod": "claude.ai" if signed_in else "none"}))
    sys.exit(0 if signed_in else 1)

mode = os.environ.get("FAKE_CLI_MODE", "ok")
prompt = sys.stdin.read()
with open(args[args.index("--mcp-config") + 1], encoding="utf-8") as handle:
    config = json.load(handle)


def emit(message):
    print(json.dumps(message), flush=True)


emit(
    {
        "type": "system",
        "subtype": "init",
        "model": "fake-model",
        "mcp_servers": [{"name": "contxt-app", "status": "connected"}],
    }
)
listing = sorted(
    os.path.relpath(os.path.join(here, name), os.getcwd()).replace(os.sep, "/")
    for here, _folders, names in os.walk(os.getcwd())
    for name in names
)
report = {
    "argv": args,
    "cwd": os.getcwd(),
    "prompt": prompt,
    "config": config,
    "listing": listing,
}
for made in filter(None, os.environ.get("FAKE_CLI_MAKE", "").split(",")):
    os.makedirs(os.path.dirname(made) or ".", exist_ok=True)
    with open(made, "wb") as handle:
        handle.write(b"made by the run: " + made.encode())
emit(
    {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "debug " + json.dumps(report)}]},
    }
)
if mode == "hang":
    time.sleep(120)
if mode == "fail":
    print("boom: the model could not start", file=sys.stderr, flush=True)
    sys.exit(3)
emit(
    {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "mcp__contxt-app__claim_task",
                    "input": {"task_id": "task_x"},
                }
            ]
        },
    }
)
emit(
    {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": [{"type": "text", "text": "Claimed."}],
                    "is_error": False,
                }
            ]
        },
    }
)
emit(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Done: two proposals.",
        "num_turns": 3,
    }
)
