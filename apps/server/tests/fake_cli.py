"""A stand-in for the Claude Code CLI in tests: the commands the workspace calls, the
stream-json lines it reads, and a report of exactly how it was started. Asked for one answer
(`--output-format json`), the report is the answer.

FAKE_CLI_SIGNED_IN=0 answers as signed out. FAKE_CLI_MODE is ok (default), hang (waits to be
stopped) or fail (exits with an error on stderr). FAKE_CLI_MAKE names files (comma-separated,
relative to its folder) it makes there, as a run of a skill that makes files would.

FAKE_CLI_FLAGS says which version it plays: new (default, has --restricted), older (only
--setting-sources) or oldest (neither); an option it does not know stops it, as Claude Code
does. FAKE_CLI_AUTH=expired plays a login whose token no longer works: `auth status` still
says signed in, but every answer is an authentication error.
"""

import json
import os
import subprocess
import sys
import time

args = sys.argv[1:]
flags = os.environ.get("FAKE_CLI_FLAGS", "new")
known = {"new": ["--restricted", "--setting-sources"], "older": ["--setting-sources"]}.get(
    flags, []
)
if args[:1] == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if args[:1] == ["--help"]:
    print("Usage: claude [options] [command] [prompt]\n\nOptions:")
    for flag in ["--tools <tools...>", "--strict-mcp-config", *known]:
        print(f"  {flag}")
    sys.exit(0)
if args[:2] == ["auth", "status"]:
    signed_in = os.environ.get("FAKE_CLI_SIGNED_IN", "1") == "1"
    print(json.dumps({"loggedIn": signed_in, "authMethod": "claude.ai" if signed_in else "none"}))
    sys.exit(0 if signed_in else 1)
for flag in ("--restricted", "--setting-sources"):
    if flag in args and flag not in known:
        print(f"error: unknown option '{flag}'", file=sys.stderr)
        sys.exit(1)

mode = os.environ.get("FAKE_CLI_MODE", "ok")
prompt = sys.stdin.read()
if os.environ.get("FAKE_CLI_AUTH") == "expired":
    reason = (
        'Failed to authenticate. API Error: 401 {"type":"error","error":{"type":'
        '"authentication_error","message":"OAuth access token is invalid."}}'
    )
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": reason}))
    sys.exit(1)
with open(args[args.index("--mcp-config") + 1], encoding="utf-8") as handle:
    config = json.load(handle)
# What Claude Code reports a call used: a fixed system prompt plus the prompt, about four
# characters a token, so a longer prompt reads as more input.
USAGE = {
    "input_tokens": 5,
    "cache_read_input_tokens": 1000,
    "cache_creation_input_tokens": len(prompt) // 4,
    "output_tokens": 7,
}
SPENT = {"total_cost_usd": 0.0123, "modelUsage": {"claude-opus-5-5": {"costUSD": 0.0123}}}
if args[args.index("--output-format") + 1] == "json":
    started = {"argv": args, "cwd": os.getcwd(), "prompt": prompt, "config": config}
    print(
        json.dumps(
            {
                "type": "result",
                "is_error": False,
                "result": json.dumps(started),
                "usage": USAGE,
                **SPENT,
            }
        )
    )
    sys.exit(0)


def emit(message):
    print(json.dumps(message), flush=True)


emit(
    {
        "type": "system",
        "subtype": "init",
        "model": "fake-model",
        "mcp_servers": [
            {"name": "contxt-app", "status": os.environ.get("FAKE_CLI_MCP", "connected")}
        ],
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


def run_hooks(event, payload):
    """What the hooks a --settings file names for an event print, run as Claude Code runs
    them: each command through the shell, the event on its stdin."""
    if "--settings" not in args:
        return []
    with open(args[args.index("--settings") + 1], encoding="utf-8") as handle:
        settings = json.load(handle)
    outs = []
    for group in (settings.get("hooks") or {}).get(event) or []:
        for hook in group.get("hooks") or []:
            done = subprocess.run(
                hook["command"],
                shell=True,
                input=json.dumps(dict(payload, hook_event_name=event)),
                capture_output=True,
                text=True,
                timeout=60,
            )
            outs.append(done.stdout.strip())
    return outs


claim = {"tool_name": "mcp__contxt-app__claim_task", "tool_input": {"task_id": "task_x"}}
hooks = {
    "pre": run_hooks("PreToolUse", claim),
    "post": run_hooks("PostToolUse", dict(claim, tool_response="Claimed.")),
    "stop": run_hooks("Stop", {"stop_hook_active": False}),
}
if any(hooks["stop"]):  # sent back: Claude Code would go on; this one only stops again
    hooks["stop"] += run_hooks("Stop", {"stop_hook_active": True})
if "--settings" in args:
    emit(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hooks " + json.dumps(hooks)}]},
        }
    )
emit(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Done: two proposals.",
        "num_turns": 3,
        "usage": USAGE,
        **SPENT,
    }
)
