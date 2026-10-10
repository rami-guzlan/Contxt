#!/usr/bin/env python3
"""SessionStart hook: one line of brain status, the person's own kernel layer, the session id
this conversation shares with the brain, a sweep of the drop and skill folders, and a warning
when CLAUDE.md is stale.

Claude Code adds what this prints to the conversation. The person's layer (their own standing
notes) never sits in a shared startup file, so it arrives here, fresh each session. The session
id (`cc:` and Claude Code's own id) is the one the prompt hook pushes briefs under; the model
passes it to `get_task_context`, so neither sends what the other already did. After a
compaction or a clear the conversation holds nothing it was given before, and the brain is told
so.

The sweep is what makes shared material arrive without anyone asking: files put in the drop
folder, or skills written into a watched skills folder, are proposed for review as the session
opens (see brainkit/sync.py). It runs without the embedding model, so it takes well under a
second, and any failure is reported in the status line instead of breaking the session.
"""
import json
import sys

FORGOTTEN = ("compact", "clear")  # the conversation no longer holds what it was given


def claude_session(payload) -> str | None:
    """The brain session for a Claude Code conversation: `cc:` and Claude Code's own id."""
    from brainkit.sessions import Ledger
    found = str((payload or {}).get("session_id") or "").strip()
    session = f"cc:{found}" if found else ""
    return session if session and Ledger.valid(session) else None


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    brain = None
    try:
        from brainkit import kernel, util
        from brainkit.api import Brain
        brain = Brain(embeddings=False)
        swept = ""
        if brain.state().config.data.get("sync"):
            try:
                result = brain.sync()
                if result.data.get("proposed"):
                    swept = f"; sync proposed {result.data['proposed']} new item(s) for review"
            except Exception as exc:
                swept = f"; sync failed: {exc}"
        st = brain.state()
        chain = st.scopes.chain(brain.principal()) or [st.scopes.root()]
        found = kernel.compile(st.config, st.index, st.scopes, chain)
        on_disk = kernel.file_fingerprint(brain.repo_root)
        pending = len(st.snapshot.proposals)
        line = (f"[brain] {st.config.name}: acting as {chain[-1]}; kernel {found.fingerprint}"
                + (f"; {pending} proposal(s) waiting for review" if pending else "") + swept)
        if on_disk != found.fingerprint:
            line += ". CLAUDE.md is stale: run `brain kernel`."
        print(line)
        session = claude_session(payload)
        if session and payload.get("source") in FORGOTTEN:
            brain.ledger.refresh(session)
        held = brain.ledger.delivered(session) if session else {}
        if found.person and ("kernel-person", found.person_fingerprint) not in held:
            print("\n" + found.person.rstrip())
            if session:
                brain.ledger.hand(session, [("kernel-person", found.person_fingerprint,
                                             found.person_fingerprint,
                                             util.tokens(found.person))],
                                  principal=chain[-1], label="Claude Code")
        if session:
            print(f"\nBrain session_id: {session}. Pass it as `session_id` on every brain call "
                  "in this conversation: the brain then sends only what it does not hold yet.")
    except Exception as exc:
        print(f"[brain] status unavailable: {exc}")
    finally:
        if brain is not None:
            brain.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
