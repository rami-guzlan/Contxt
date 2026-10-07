"""What each AI asked, and what it got: the requests the brain served, newest first.

Every packet the brain hands a conversation is in the session ledger (sessions.py) for the
retention window: the request, its tokens, and each piece with why it was picked. This adds
what a person needs to read it: the app that asked (the MCP client's own name, from its
handshake), the title of every piece, the share of the brain the request got, what the
conversation opened after the packet, and what it saved or suggested. It writes nothing.
"""
from __future__ import annotations

import os

from . import recap
from .sessions import Ledger

# The MCP client names apps give in their handshake, as people know the apps.
CLIENTS = (
    ("claude-code", "Claude Code"),
    ("claude-ai", "Claude Desktop"),
    ("claude", "Claude"),
    ("cursor", "Cursor"),
    ("codex", "Codex"),
    ("chatgpt", "ChatGPT"),
    ("openai", "ChatGPT"),
    ("vscode", "VS Code"),
    ("visual studio code", "VS Code"),
    ("copilot", "GitHub Copilot"),
    ("windsurf", "Windsurf"),
    ("zed", "Zed"),
    ("gemini", "Gemini CLI"),
    ("goose", "Goose"),
    ("cline", "Cline"),
)
MAX_LIMIT = 200


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def client_label(raw: str) -> str:
    """"claude-code 2.1.0" reads "Claude Code"; an unknown app keeps its own name."""
    text = " ".join(str(raw or "").split())
    low = text.lower()
    for key, label in CLIENTS:
        if low.startswith(key):
            return label
    return text.split(" ")[0] if text else "An AI app"


def _piece(st, kind: str, item: str, tokens: int, reason) -> dict:
    """One piece a request got, named as a person reads it."""
    out = {"kind": kind, "id": item, "tokens": int(tokens or 0), "why": str(reason or "")}
    if kind == "note":
        note = st.index.note(item, include_archived=True)
        if note is not None:
            out.update(title=note.title, note_kind=note.kind, topic=note.route_key,
                       topic_label=st.index.topic_label(note.route_key), live=note.live)
        else:
            out.update(title=item, live=False)
    elif kind == "section":
        path, _, number = item.rpartition("#")
        title = st.index.file_title(path) if path else item
        heading = next((s.heading for s in st.index.file_sections(path)
                        if str(s.n) == number), "") if path else ""
        out.update(title=f"{title}: {heading}" if heading else title, path=path)
    elif kind == "focus":
        focus = st.index.focuses.get(item)
        out.update(title=focus.title if focus is not None else item)
    elif kind == "skill":
        out.update(title=f"/{item}")
    elif kind == "reference":
        out.update(title=st.index.file_title(item), path=item)
    elif kind == "kernel":
        out.update(title="The startup context")
    elif kind == "system":
        out.update(title="How the brain works")
    else:
        out.update(title=item)
    return out


def requests(brain, *, limit=50, before=None, client=None, session=None):
    """The requests the brain served, newest first, each with the app that asked, what it got
    and why, what the conversation opened after it, and what it saved or suggested. With
    `session`, only that conversation's."""
    st = brain.state()
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    try:
        rows = brain.ledger.requests(limit=limit if not client else MAX_LIMIT, before=before,
                                     session=session)
    except Exception:  # an unreadable ledger is an empty page, not an error
        rows = []
    # The whole brain: its live notes, skills and filed documents.
    from . import runtime
    current = runtime.code_hash()  # the engine on disk now
    brain_tokens = (sum(n.tokens for n in st.index.notes.values())
                    + sum(s.tokens for s in st.index.skills.values())
                    + sum(r.tokens for r in st.index.references.values())) or 1
    saved = _saved(brain, st, {r["session_id"] for r in rows})
    out = []
    for row in rows:
        app = client_label(row.get("client") or "")
        if client and app != client:
            continue
        data = row.get("data") or {}
        got = [_piece(st, *piece) for piece in row["items"]]
        focus = data.get("focus_id")
        out.append({
            "id": row["id"], "session_id": row["session_id"], "at": row["at"],
            "request": row["request"] or "", "mode": row["mode"], "app": app,
            "client": row.get("client") or None, "tokens": int(row["tokens"] or 0),
            "share": round(int(row["tokens"] or 0) / brain_tokens, 4),
            "project": ({"id": focus, "title": st.index.focuses[focus].title}
                        if focus and focus in st.index.focuses else None),
            "skill": data.get("skill_id"),
            "got": [p for p in got if p["kind"] != "kernel"],
            "kernel": any(p["kind"] == "kernel" and p["tokens"] for p in got),
            "opened": [_piece(st, *piece) for piece in row["opened"]],
            "nothing": data.get("mode") == "lean" and not (
                data.get("note_ids") or data.get("standing_ids") or data.get("held_ids")
                or data.get("section_ids")),
            "saved": saved.get(row["session_id"], []) if row.get("last_in_session") else [],
            "engine": row.get("engine") or None,
            # a conversation still on older engine code: its app needs a restart
            "old_engine": bool(row.get("engine")) and row.get("engine") != current,
        })
        if len(out) >= limit:
            break
    apps = sorted({r["app"] for r in out})
    return _result(f"{len(out)} request(s).",
                   {"requests": out, "brain_tokens": brain_tokens, "apps": apps,
                    "engine": current})


def normal_path(path: str) -> str:
    """A file's path as the record keeps it: absolute, and on Windows in one case."""
    return os.path.normcase(os.path.abspath(str(path or "").strip()))


def record_output(brain, path, *, title="", session_id=None):
    """Note a file an AI saved for the person, with the conversation it was made in, so the
    person can see what that conversation was given."""
    text = str(path or "").strip()
    if not text or len(text) > 500:
        return _result("Give the saved file's full path.", {"status": "invalid"}, True)
    session = str(session_id or "").strip()
    if session and not Ledger.valid(session):
        return _result("That is not a session id from get_task_context.",
                       {"status": "invalid"}, True)
    brain.ledger.record_output(normal_path(text), session, title=" ".join(
        str(title or "").split())[:200], client=brain.client)
    return _result("Noted: the person can now see what this conversation was given when the "
                   "file was made." if session else
                   "Noted. Pass your session_id next time, so the file shows what it was made "
                   "from.", {"status": "recorded", "path": normal_path(text),
                             "session_id": session or None})


def made_from(brain, path):
    """What a saved file was made from, when an AI said so: the conversation's requests and
    what each got. None when nothing was recorded for the file."""
    found = brain.ledger.output(normal_path(path))
    if found is None:
        return None
    rows = (requests(brain, limit=MAX_LIMIT, session=found["session_id"]).data["requests"]
            if found.get("session_id") else [])
    return {"title": found.get("title") or "", "at": found.get("at"),
            "app": client_label(found.get("client") or ""),
            "session_id": found.get("session_id") or None, "requests": rows}


def work_given(brain, run_id):
    """What one run of the app's AI work was handed from the brain (its `work:<run>`)."""
    st = brain.state()
    return [_piece(st, *item) for item in brain.ledger.session_items(f"work:{run_id}")]


def _saved(brain, st, sessions: set) -> dict[str, list[dict]]:
    """{session: what it saved or suggested}: changes that went in (or were decided) and
    suggestions still waiting, each with its title and status."""
    out: dict[str, list[dict]] = {}
    if not sessions:
        return out
    for record in brain.vault.decisions():
        session = str(record.get("session") or "")
        if session not in sessions or record.get("action") not in (
                "auto-applied", "approved", "rejected"):
            continue
        note_id = str(record.get("pointer") or record.get("note") or "")
        note = st.index.note(note_id, include_archived=True) if note_id else None
        title = note.title if note is not None else (record.get("target") or {}).get(
            "title") or note_id or record.get("proposal")
        out.setdefault(session, []).append({
            "id": note_id or record.get("proposal"), "title": title,
            "status": {"auto-applied": "went in", "approved": "kept",
                       "rejected": "not kept"}[record["action"]],
            "source": recap.record_source(record, note)})
    for proposal in st.snapshot.proposals.values():
        session = str(proposal.meta.get("session") or "")
        if session in sessions:
            out.setdefault(session, []).append({
                "id": proposal.id,
                "title": str(proposal.target.get("title") or proposal.target.get("name")
                             or proposal.id),
                "status": "waiting", "source": "chat"})
    return out
