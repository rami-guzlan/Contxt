#!/usr/bin/env python3
"""UserPromptSubmit hook: push the brain's brief for a message when it holds something new for
it, and say when the message states something durable.

Claude Code runs this on every message before the model sees it, with the message as JSON on
stdin, and adds what it prints to the message.

PUSH. Retrieval that waits for the model to remember to ask fails whenever it forgets. So for a
message that asks for something, the hook asks the router itself, under the conversation's own
session (`cc:` and Claude Code's id, the one the session-start hook named), and when the brain
holds something this conversation has not been given (a note, a must-hold, a part of a document,
a procedure, the startup context when the file is stale), the brief comes with the message. The
model's own `gnomon_get_context` call with that session id then sends only what the push did not.
Nothing new: nothing pushed, and the reminder to ask instead. brain.json `hooks.push` sets how:
"words" (the default: about a second, no embedding model), "meaning" (the router exactly as
`gnomon_get_context` runs it, a few seconds while the model loads) or "off"; `BRAIN_HOOK_PUSH=0`
turns it off too. Every pushed brief is logged with `delivery: push`, so the report can weigh
push against pull.

CAPTURE, with no model call (section 17.4): a sentence that states a rule, correction,
preference, decision, something to remember or a changed fact is filed by the hook itself as a
proposal that waits for the owner, quoting the message, and one short line says so, so the
model does not propose it again. Procedures and documents still need the model
(propose(kind: "skill" | "file")). Nothing reminds the model to ask on every message: the push
brings what is new, and `BRAIN_HOOK_ASK=1` turns the old reminder back on.

It never blocks a message and never fails a session: any problem means no push.
"""
import json
import os
import re
import sys

ASK = ("If this message asks for something new, call context with it first (pass your "
       "session_id): the brain sends only what this conversation does not hold yet.")
SMALL_TALK = re.compile(r"^\s*(?:thanks|thank you|ok(?:ay)?|great|cool|perfect|got it|"
                        r"sounds good|yes|no|sure|nice)\b[\s.!]*$", re.IGNORECASE)
PUSHED = ("[brain] The brief for this message, under session_id {session}; pass it to "
          "context, which then sends only what is not here.")
# What the hook files itself: the kinds a sentence states plainly, as the note kind they
# become. A changed fact cued only by "our new" is too often a request ("announce our new
# program") to file unasked.
KEEP = {"rule": "rule", "correction": "fact", "preference": "rule", "decision": "decision",
        "memory": "fact", "fact": "fact"}
KEPT = "[brain] Filed for the owner's review, no need to propose it again: {quotes}."
# What a brief may hold that this conversation was not given: any of it makes it worth pushing.
NEW = ("note_ids", "section_ids", "system_ids", "skill_included", "kernel_included",
       "person_included")
MODES = ("words", "meaning", "off")


def _asks_for_something(prompt: str) -> bool:
    """A message with a request in it, not small talk ("thanks!", "ok")."""
    words = re.findall(r"[a-z0-9']+", prompt.lower())
    return len(words) >= 3 and not SMALL_TALK.match(prompt)


def claude_session(payload) -> str | None:
    """The brain session for a Claude Code conversation: `cc:` and Claude Code's own id."""
    from brainkit.sessions import Ledger
    found = str((payload or {}).get("session_id") or "").strip()
    session = f"cc:{found}" if found else ""
    return session if session and Ledger.valid(session) else None


def push_mode(vault_root: str) -> str:
    """brain.json `hooks.push`: words (the default), meaning or off."""
    try:
        with open(os.path.join(vault_root, "brain.json"), encoding="utf-8") as handle:
            hooks = json.load(handle).get("hooks") or {}
        mode = str(hooks.get("push") or "words").strip().lower()
    except (OSError, ValueError, AttributeError):
        mode = "words"
    return mode if mode in MODES else "words"


def is_new(data: dict, held: dict) -> bool:
    """Does this brief give the conversation something it does not hold? Must-holds come with
    every brief, so they count only the first time. When the local engine's gate or cut found
    nothing for the message, a push sends nothing (a pull would get one line)."""
    if data.get("mode") == "nothing":
        return False
    if any(data.get(key) for key in NEW):
        return True
    return any(("must", item) not in held for item in data.get("must_hold_ids") or [])


def push(prompt: str, payload) -> str:
    """The brief for this message when the brain holds something new for it; "" otherwise."""
    if os.environ.get("BRAIN_HOOK_PUSH", "1") == "0":
        return ""
    session = claude_session(payload)
    if not session:
        return ""
    from brainkit import kernel
    from brainkit.api import Brain
    brain = Brain(embeddings=False)
    try:
        mode = push_mode(brain.vault.root)
        if mode == "off":
            return ""
        if mode == "meaning":
            brain.close()
            brain = Brain()
        brain.client = "Claude Code (prompt hook)"
        held = brain.ledger.delivered(session)
        ask = {"session_id": session, "delivery": "push",
               "startup_fingerprint": kernel.file_fingerprint(brain.repo_root)}
        # Asked once without a record: a brief that is not pushed must not count as held.
        found = brain.context(prompt, record=False, **ask)
        if found.is_error or not is_new(found.data, held):
            return ""
        sent = brain.context(prompt, **ask)
        if sent.is_error:
            return ""
        from brainkit.mcp_server import public_text
        return PUSHED.format(session=session) + "\n\n" + public_text(sent.text)
    finally:
        brain.close()


def keep(prompt: str, payload) -> str:
    """File what the message states as lasting, as proposals that wait for the owner: the
    line saying so, or "" when nothing was filed."""
    if os.environ.get("BRAIN_HOOK_CAPTURE", "1") == "0":
        return ""
    from brainkit import capture, util
    found = [c for c in capture.detect(prompt) if c.kind in KEEP
             and not (c.kind == "fact" and c.cue.lower() == "our new")]
    session = claude_session(payload)
    if not found or not session:
        return ""
    from brainkit.api import Brain
    brain = Brain(embeddings=False)
    kept = []
    try:
        brain.client = "Claude Code (prompt hook)"
        for candidate in found:
            done = brain.propose(
                text=candidate.sentence, evidence=f'"{candidate.sentence}"',
                note_kind=KEEP[candidate.kind], session_id=session, capture_origin="chat",
                force_pending=True, op_id="hook-" + util.short_hash(session + candidate.sentence, 16))
            if not done.is_error:
                kept.append(f'"{candidate.sentence}"')
    finally:
        brain.close()
    return KEPT.format(quotes="; ".join(kept)) if kept else ""


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        prompt = str(payload.get("prompt") or "")
    except Exception:
        return 0
    if not prompt.strip():
        return 0
    try:
        text = keep(prompt, payload)
    except Exception:
        text = ""
    asks = _asks_for_something(prompt)
    brief = ""
    if asks:
        try:
            brief = push(prompt, payload)
        except Exception:
            brief = ""
    # Models call the brain for a task's first message and then tend to answer follow-ups
    # from memory; the brain's rules for the new part ("add a call to action", "can I add a
    # script?") never arrive. The reminder rides on every message that asks for something,
    # unless the brief came with it.
    if asks and not brief and os.environ.get("BRAIN_HOOK_ASK", "0") == "1":
        text = f"{text} [brain] {ASK}".strip()
    context = "\n\n".join(part for part in (text, brief) if part)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
