#!/usr/bin/env python3
"""Launch the MCP server a .mcp.json describes, exactly as a client would, and exercise it.

    python tools/mcp_check.py                              uses ../.mcp.json, else ./.mcp.json
    python tools/mcp_check.py --request "Can I publish this now?"
    python tools/mcp_check.py --config C:/path/.mcp.json --kernel --json

It runs the configured command with the configured args and cwd, performs the MCP handshake,
lists the tools, sends one task through gnomon_get_context, then a follow-up in the same session
to show deduplication, and prints what a model would receive. Exit code 0 means the server
started, answered every call, and reported no tool errors. Nothing is written to the vault;
the session ledger records the two packets like any other conversation.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def find_config(explicit):
    if explicit:
        return os.path.abspath(explicit)
    for candidate in (os.path.join(os.path.dirname(REPO), ".mcp.json"),
                      os.path.join(REPO, ".mcp.json")):
        if os.path.isfile(candidate):
            return candidate
    raise SystemExit("No .mcp.json found; pass --config.")


class Client:
    def __init__(self, command, args, cwd, timeout):
        self.timeout = timeout
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.proc = subprocess.Popen(
            [command, *args], cwd=cwd or None, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.next_id = 0

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def rpc(self, method, params=None):
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method,
                   "params": params or {}}
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        started = time.perf_counter()
        try:
            line = self.lines.get(timeout=self.timeout)
        except queue.Empty:
            raise SystemExit(f"FAILED: no reply to {method} within {self.timeout}s") from None
        if line is None:
            raise SystemExit("FAILED: the server exited.\n" + self.proc.stderr.read()[-2000:])
        return json.loads(line), round((time.perf_counter() - started) * 1000)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self.proc.kill()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--config")
    parser.add_argument("--server", default="brain")
    parser.add_argument("--request", default="Write a LinkedIn post about AI leadership")
    parser.add_argument("--followup", default="Make the opening line punchier")
    parser.add_argument("--search", help="also call notes_search with this query, in the "
                        "same session, as an agent would when the packet lacks something")
    parser.add_argument("--kernel", action="store_true", help="also print the startup kernel")
    parser.add_argument("--json", action="store_true", help="print raw JSON-RPC replies")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    path = find_config(args.config)
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
    server = (config.get("mcpServers") or {}).get(args.server)
    if not server:
        raise SystemExit(f"No server named {args.server!r} in {path}.")
    command, server_args = server["command"], list(server.get("args") or [])
    print(f"config : {path}")
    print(f"launch : {command} {' '.join(server_args)}"
          + (f"   (cwd {server['cwd']})" if server.get("cwd") else ""))

    client = Client(command, server_args, server.get("cwd"), args.timeout)
    failures = []
    try:
        init, ms = client.rpc("initialize", {"protocolVersion": "2025-06-18",
                                             "clientInfo": {"name": "mcp_check"}})
        info = (init.get("result") or {}).get("serverInfo") or {}
        print(f"server : {info}  ({ms} ms)")
        tools, ms = client.rpc("tools/list")
        names = [t["name"] for t in (tools.get("result") or {}).get("tools") or []]
        print(f"tools  : {', '.join(names)}  ({ms} ms)")
        if "gnomon_get_context" not in names:
            failures.append("gnomon_get_context is not advertised")

        def task(request, session=None):
            arguments = {"request": request}
            if session:
                arguments["session_id"] = session
            reply, ms = client.rpc("tools/call", {"name": "gnomon_get_context",
                                                  "arguments": arguments})
            result = reply.get("result") or {}
            text = "".join(part.get("text", "") for part in result.get("content") or [])
            if args.json:
                print(json.dumps(reply, indent=1, ensure_ascii=False))
            if result.get("isError"):
                failures.append(f"gnomon_get_context reported an error for {request!r}")
            return text, ms

        text, ms = task(args.request)
        session = text.split("session_id: ", 1)[1].split()[0] if "session_id: " in text else None
        kernel, _, packet = text.partition("# Task context")
        print(f"\n=== gnomon_get_context: {args.request!r}  ({ms} ms) ===")
        if kernel.strip() and args.kernel:
            print(kernel.strip() + "\n")
        elif kernel.strip():
            print(f"[startup kernel included: {len(kernel.split())} words; --kernel to show]\n")
        print(("# Task context" + packet).strip() if packet else text.strip())

        if args.followup and session:
            text2, ms2 = task(args.followup, session)
            print(f"\n=== follow-up in the same session: {args.followup!r}  ({ms2} ms) ===")
            print(text2.partition("# Task context")[2].strip() or text2.strip())

        if args.search:
            if "notes_search" not in names:
                failures.append("notes_search is not advertised")
            else:
                arguments = {"query": args.search}
                if session:
                    arguments["session_id"] = session
                reply, ms3 = client.rpc("tools/call", {"name": "notes_search",
                                                       "arguments": arguments})
                result = reply.get("result") or {}
                if args.json:
                    print(json.dumps(reply, indent=1, ensure_ascii=False))
                if result.get("isError"):
                    failures.append(f"notes_search reported an error for {args.search!r}")
                print(f"\n=== notes_search: {args.search!r}  ({ms3} ms) ===")
                print("".join(p.get("text", "") for p in result.get("content") or []).strip())
    finally:
        client.close()

    print("\n" + ("OK: the server started, answered every call, and reported no tool errors."
                  if not failures else "FAILED:\n- " + "\n- ".join(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
