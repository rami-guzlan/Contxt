#!/usr/bin/env python3
"""Stop hook (goals plan 5.8): with a task active in this conversation, ask for a save before
the session ends, so the next session, or another agent, starts from the card.

The conversation's working context (`get_task_context` with `context`) names the task. When
that task is still open and its card was not saved since the conversation's last brief, the
session is sent back once with one line: save where you are with `hand_off`, pass it on, or
finish it. The second time it may stop. A hook that cannot read the Brain does nothing.

Register it for Claude Code under "Stop": `python -m brainkit.hooks.task_stop`.
"""
from __future__ import annotations

import json
import re
import sys

OPEN = ("open", "handed_off", "working", "waiting_for_you", "blocked")


def reminder(brain, session: str) -> str | None:
    """The line to send the session back with, or None."""
    from brainkit import handoff
    name = brain.ledger.session_context(session) or ""
    if not re.match(r"^T-\d+$", name, re.IGNORECASE):
        return None
    task = handoff.task(brain, name.upper())
    if task is None or task["status"] not in OPEN:
        return None
    last = brain.ledger.last_packet(session) or {}
    saved = str((task.get("card") or {}).get("at") or "")
    if saved and saved >= str(last.get("at") or ""):
        return None
    return (f"Before you stop: save where you are on {task['id']} with hand_off (done so "
            "far, next step), pass it on, or finish it, so the next session starts from the "
            "card.")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict) or payload.get("stop_hook_active"):
        return 0
    try:
        from brainkit.api import Brain
        from brainkit.hooks.session_start import claude_session
        session = claude_session(payload)
        if not session:
            return 0
        brain = Brain()
        try:
            line = reminder(brain, session)
        finally:
            brain.close()
    except Exception:  # a Brain that cannot answer never keeps a session open
        return 0
    if line:
        sys.stdout.write(json.dumps({"decision": "block", "reason": line}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
