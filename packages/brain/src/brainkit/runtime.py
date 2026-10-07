"""Is this long-lived process still running the engine code on disk?

A stdio MCP server lives as long as the client session. Content changes are picked up per
request, but an ENGINE change (a new router, a fixed bug) is only picked up by a restart.
The server hashes its own code at start and compares on demand, so a stale process says so
instead of answering with yesterday's logic.
"""
from __future__ import annotations

import hashlib
import os

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION = "2.0.0"


def code_files():
    out = []
    for folder, dirs, files in os.walk(ENGINE_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for name in sorted(files):
            if name.endswith((".py", ".md", ".html", ".js", ".css")):
                out.append(os.path.join(folder, name))
    return sorted(out)


def code_hash() -> str:
    digest = hashlib.sha256()
    for path in code_files():
        try:
            with open(path, "rb") as handle:
                digest.update(os.path.relpath(path, ENGINE_DIR).encode() + b"\0" + handle.read())
        except OSError:
            continue
    return digest.hexdigest()[:12]


STARTED_WITH = code_hash()


def stale() -> tuple[bool, str]:
    now = code_hash()
    if now == STARTED_WITH:
        return False, f"engine {VERSION} ({STARTED_WITH}) is current"
    return True, (f"This process runs engine code {STARTED_WITH}, but the code on disk is {now}. "
                  "Reconnect the MCP server (or restart the process) to load the new engine.")
