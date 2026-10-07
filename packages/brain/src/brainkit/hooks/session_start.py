#!/usr/bin/env python3
"""SessionStart hook: one line of brain status, a sweep of the drop and skill folders, and a
warning when CLAUDE.md is stale.

The sweep is what makes shared material arrive without anyone asking: files put in the drop
folder, or skills written into a watched skills folder, are proposed for review as the session
opens (see brainkit/sync.py). It runs without the embedding model, so it takes well under a
second, and any failure is reported in the status line instead of breaking the session.
"""
import sys


def main():
    brain = None
    try:
        from brainkit import kernel
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
        _text, fingerprint = kernel.render(st.config, st.index, st.scopes, chain)
        on_disk = kernel.file_fingerprint(brain.repo_root)
        pending = len(st.snapshot.proposals)
        line = (f"[brain] {st.config.name}: acting as {chain[-1]}; kernel {fingerprint}"
                + (f"; {pending} proposal(s) waiting for review" if pending else "") + swept)
        if on_disk != fingerprint:
            line += ". CLAUDE.md is stale: run `brain kernel`."
        print(line)
    except Exception as exc:
        print(f"[brain] status unavailable: {exc}")
    finally:
        if brain is not None:
            brain.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
