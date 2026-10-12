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
    # The Claude desktop app, for the servers set in its own settings: "local-agent-mode-"
    # and the server's name.
    ("local-agent-mode", "Claude app"),
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


# What a request got as its startup context, not as a piece of the brief.
KERNEL_KINDS = ("kernel", "kernel-person")


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
    elif kind == "kernel-person":
        out.update(title="Your own startup layer")
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
    from . import runtime
    current = runtime.code_hash()  # the engine on disk now
    brain_tokens = _brain_tokens(st)
    saved = _saved(brain, st, {r["session_id"] for r in rows})
    out = []
    for row in rows:
        shaped = _shape(st, row, brain_tokens, current, saved)
        if client and shaped["app"] != client:
            continue
        out.append(shaped)
        if len(out) >= limit:
            break
    apps = sorted({r["app"] for r in out})
    return _result(f"{len(out)} request(s).",
                   {"requests": out, "brain_tokens": brain_tokens, "apps": apps,
                    "engine": current})


def _brain_tokens(st) -> int:
    """The whole brain: its live notes, skills and filed documents."""
    return (sum(n.tokens for n in st.index.notes.values())
            + sum(s.tokens for s in st.index.skills.values())
            + sum(r.tokens for r in st.index.references.values())) or 1


def _shape(st, row, brain_tokens: int, current: str, saved: dict) -> dict:
    """One ledger packet as a person reads it."""
    data = row.get("data") or {}
    got = [_piece(st, *piece) for piece in row["items"]]
    focus = data.get("focus_id")
    return {
        "id": row["id"], "session_id": row["session_id"], "at": row["at"],
        "request": row["request"] or "", "mode": row["mode"],
        "app": client_label(row.get("client") or ""),
        "client": row.get("client") or None, "tokens": int(row["tokens"] or 0),
        "share": round(int(row["tokens"] or 0) / brain_tokens, 4),
        "project": ({"id": focus, "title": st.index.focuses[focus].title}
                    if focus and focus in st.index.focuses else None),
        "skill": data.get("skill_id"),
        "got": [p for p in got if p["kind"] not in KERNEL_KINDS],
        "kernel": any(p["kind"] in KERNEL_KINDS and p["tokens"] for p in got),
        "opened": [_piece(st, *piece) for piece in row["opened"]],
        "nothing": data.get("mode") == "lean" and not (
            data.get("note_ids") or data.get("standing_ids") or data.get("held_ids")
            or data.get("section_ids")),
        "saved": saved.get(row["session_id"], []) if row.get("last_in_session") else [],
        "engine": row.get("engine") or None,
        # a conversation still on older engine code: its app needs a restart
        "old_engine": bool(row.get("engine")) and row.get("engine") != current,
    }


def request(brain, packet_id):
    """One request in full: everything `requests` says about it, the exact text it was
    handed (`text`), and the startup context when it went with this request (`startup`:
    its text as sent, or None when it was sent before the brain kept it)."""
    st = brain.state()
    try:
        rows = brain.ledger.requests(limit=1, packet=str(packet_id or ""))
    except Exception:  # an unreadable ledger has no requests
        rows = []
    if not rows:
        return _result(f"No request {packet_id} (requests are kept for "
                       f"{brain.ledger.retention_days} days).", {"status": "missing"},
                       is_error=True)
    row = rows[0]
    from . import runtime
    shaped = _shape(st, row, _brain_tokens(st), runtime.code_hash(),
                    _saved(brain, st, {row["session_id"]}))
    shaped["text"] = row.get("text") or ""
    data = row.get("data") or {}
    fingerprint = str(data.get("kernel_fingerprint") or "")
    startup = None
    if data.get("kernel_included") and fingerprint:
        kept = brain.ledger.kernel_text(fingerprint)
        startup = {"fingerprint": fingerprint,
                   "text": kept or _kernel_now(brain, st, row, fingerprint)}
    elif data.get("person_included") and data.get("person_fingerprint"):
        # Only the person's own layer went with it (the shared part was in their startup file).
        own = str(data["person_fingerprint"])
        startup = {"fingerprint": own, "text": brain.ledger.kernel_text(own)}
    shaped["startup"] = startup
    shaped["why"] = why(brain, st, row["id"], data)
    return _result(f"Request {row['id']}.", shaped)


def _kernel_now(brain, st, row, fingerprint: str) -> str | None:
    """The startup context as it reads now, when that is still the version the request got
    (requests from before the brain kept what it sent)."""
    from . import kernel as kernel_mod
    principal = brain.ledger.session_principal(row["session_id"])
    caller = brain.caller(principal or None, None, (row.get("data") or {}).get("partition"),
                          st=st)
    if not isinstance(caller, tuple):
        return None
    chain, partitions = caller
    text, now = kernel_mod.render(st.config, st.index, st.scopes, chain, partitions)
    return f"# Startup context (kernel {now})\n\n{text}" if now == fingerprint else None


def normal_path(path: str) -> str:
    """A file's path as the record keeps it: absolute, and on Windows in one case."""
    return os.path.normcase(os.path.abspath(str(path or "").strip()))


def record_output(brain, path, *, title="", session_id=None, project="", for_row="",
                  maker=""):
    """Note a file an AI saved for the person, with the conversation it was made in, so the
    person can see what that conversation was given; and what it is for (BL 16.5): the
    project, the State row (`sheet/row`, or a row's name) and who made it."""
    text = str(path or "").strip()
    if not text or len(text) > 500:
        return _result("Give the saved file's full path.", {"status": "invalid"}, True)
    session = str(session_id or "").strip()
    if session and not Ledger.valid(session):
        return _result("That is not a session id from get_task_context.",
                       {"status": "invalid"}, True)
    st = brain.state()
    project_id = str(project or "").strip()
    if project_id and project_id not in st.index.focuses:
        match = next((f for f in st.index.focuses.values()
                      if f.title.lower() == project_id.lower()), None)
        project_id = match.id if match else ""
    row_ref = ""
    if str(for_row or "").strip():
        from . import state as state_mod
        sheet_id, _, row_name = str(for_row).partition("/")
        pairs = ([(state_mod.sheet(brain, sheet_id),
                   state_mod.find_row(brain, sheet_id, row_name))] if row_name else
                 state_mod.named_rows(brain, str(for_row), limit=1))
        pairs = [(s, r) for s, r in pairs if s is not None and r is not None]
        if pairs:
            row_ref = f"{pairs[0][0].id}/{pairs[0][1].key}"
    brain.ledger.record_output(normal_path(text), session, title=" ".join(
        str(title or "").split())[:200], client=brain.client, project=project_id,
        row_ref=row_ref, maker=" ".join(str(maker or "").split())[:80])
    # Checked against the must-holds (BL 9): a violation flags the output, never changes it.
    violations = _check_file(brain, text)
    if violations:
        brain.ledger.flag_output(normal_path(text), violations)
        lines = "; ".join(f"{v['found']!r} ({v['rule']})" for v in violations[:3])
        return _result(f"Noted, and flagged: it breaks a must-hold: {lines}. Fix the file and "
                       "record it again.", {"status": "flagged", "path": normal_path(text),
                                            "violations": violations,
                                            "session_id": session or None})
    return _result("Noted: the person can now see what this conversation was given when the "
                   "file was made." if session else
                   "Noted. Pass your session_id next time, so the file shows what it was made "
                   "from.", {"status": "recorded", "path": normal_path(text),
                             "session_id": session or None})


TEXT_FILES = (".md", ".txt", ".html", ".htm", ".csv", ".json", ".eml")
MAX_CHECKED = 400_000


def _check_file(brain, path: str) -> list[dict]:
    """A recorded text file's must-hold violations (other files are not read)."""
    from . import outputcheck
    full = normal_path(path)
    if not full.lower().endswith(TEXT_FILES) or not os.path.isfile(full):
        return []
    try:
        if os.path.getsize(full) > MAX_CHECKED:
            return []
        with open(full, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return []
    found = outputcheck.check(text, outputcheck.must_holds_for(brain, text))
    return [v.to_dict() for v in found]


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


OUT_SHOWN = 30  # candidates that stayed out, shown at most (the ledger keeps them all)


def why(brain, st, packet_id: str, data: dict) -> dict | None:
    """Why each candidate went in or stayed out of one brief, as the ledger kept it: its
    keyword, meaning and reranker scores, the decision model's answers, the outcome and the
    reason, with the engine's mode, the lock, the gate, the cuts and each layer's time. Read
    back, never recomputed. None for a brief from before the ledger kept these."""
    try:
        rows = brain.ledger.decisions(packet_id)
    except Exception:  # an unreadable ledger has nothing to say
        rows = []
    engine = data.get("engine") or {}
    if not rows and not engine:
        return None
    shaped = []
    for row in rows:
        named = _piece(st, row["kind"], row["item"], 0, "")
        shaped.append(dict(row, title=named.get("title") or row["item"],
                           path=named.get("path")))
    inside = [r for r in shaped if r["outcome"] != "out"]
    outside = sorted((r for r in shaped if r["outcome"] == "out"),
                     key=lambda r: -max(r.get("rerank") or 0.0, r.get("keyword") or 0.0,
                                        r.get("meaning") or 0.0))
    return {"mode": engine.get("mode"), "reason": engine.get("reason") or "",
            "lock": engine.get("lock") or "", "gate": engine.get("gate"),
            "cuts": engine.get("cuts") or {}, "fitted": engine.get("fitted") or {},
            "timings": engine.get("timings") or {}, "rounds": engine.get("rounds") or 0,
            "ceiling_hit": bool(engine.get("ceiling_hit")), "notes": engine.get("notes") or [],
            "refit": bool(engine.get("refit")), "in": inside,
            "out": outside[:OUT_SHOWN], "out_count": len(outside)}
