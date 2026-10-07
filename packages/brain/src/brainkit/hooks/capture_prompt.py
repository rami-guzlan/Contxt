#!/usr/bin/env python3
"""UserPromptSubmit hook: when the person's message states something durable, tell the agent.

Claude Code runs this on every message before the model sees it, with the message as JSON on
stdin. If the message states a rule, correction, preference, decision, changed fact, procedure
or lasting document, the hook adds a short note to the model's context saying what looks
durable and which brain tool keeps it. Otherwise it prints nothing.

It reads the raw message, so it works even when the agent does not call get_task_context for a
follow-up. It never blocks a message, never writes anything, and never fails a session: any
problem means silence. It imports only the detector, so it adds a few milliseconds.
"""
import json
import os
import re
import sys

ASK = ("If this message asks for something new, call get_task_context with it first (pass "
       "your session_id): the brain sends only what this conversation does not hold yet.")
SMALL_TALK = re.compile(r"^\s*(?:thanks|thank you|ok(?:ay)?|great|cool|perfect|got it|"
                        r"sounds good|yes|no|sure|nice)\b[\s.!]*$", re.IGNORECASE)


def _asks_for_something(prompt: str) -> bool:
    """A message with a request in it, not small talk ("thanks!", "ok")."""
    words = re.findall(r"[a-z0-9']+", prompt.lower())
    return len(words) >= 3 and not SMALL_TALK.match(prompt)


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = str(payload.get("prompt") or "")
    except Exception:
        return 0
    if not prompt.strip():
        return 0
    try:
        from brainkit import capture
        text = capture.nudge(capture.detect(prompt))
    except Exception:
        return 0
    # Models call the brain for a task's first message and then tend to answer follow-ups
    # from memory; the brain's rules for the new part ("add a call to action", "can I add a
    # script?") never arrive. The reminder rides on every message that asks for something.
    if os.environ.get("BRAIN_HOOK_ASK", "1") != "0" and _asks_for_something(prompt):
        text = f"{text} {ASK}".strip() if text else ASK
    if text:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": "[brain] " + text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
