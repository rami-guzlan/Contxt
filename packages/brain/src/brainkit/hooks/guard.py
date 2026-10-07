#!/usr/bin/env python3
"""PreToolUse hook: block shell commands that match hooks/patterns.txt.

Reads the tool call as JSON on stdin; exit code 2 blocks the call and shows the reason to the
agent. The patterns cover irreversible actions the action policy says need a human: forced
pushes, hard resets, recursive deletes, and deleting the vault's governed history.
"""
import json
import os
import re
import sys


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("tool_name") not in ("Bash", "bash", "shell", "PowerShell"):
        return 0
    command = str((payload.get("tool_input") or {}).get("command") or "")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patterns.txt")
    try:
        with open(path, encoding="utf-8") as handle:
            patterns = [line.strip() for line in handle
                        if line.strip() and not line.lstrip().startswith("#")]
    except OSError:
        return 0
    for pattern in patterns:
        try:
            if re.search(pattern, command):
                sys.stderr.write(f"BLOCKED by hooks/patterns.txt ({pattern}). This action needs "
                                 "explicit human approval: ask the user to run it.")
                return 2
        except re.error:
            continue
    return 0


if __name__ == "__main__":
    sys.exit(main())
