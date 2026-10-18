"""Lossless public conversation fixtures; labels stay outside retrieval inputs."""
from __future__ import annotations

import re
from datetime import date


def convert(item: dict) -> tuple[list[dict], dict]:
    """Use occurrence/turn identity, preserving speakers and complete text.

    Repeated session ids are not interchangeable. Unknown dates, missing sessions and
    absent turn annotations are explicit errors/diagnostics, never silently skipped.
    """
    ids, dates, sessions = (item[key] for key in
                            ("haystack_session_ids", "haystack_dates", "haystack_sessions"))
    if not len(ids) == len(dates) == len(sessions):
        raise ValueError("Conversation histories are not aligned")
    notes, groups, marked = [], {}, {}
    for occurrence, (sid, stamp, turns) in enumerate(zip(ids, dates, sessions, strict=True)):
        match = re.match(r"^(\d{4})/(\d{2})/(\d{2})(?:$|\s)", stamp)
        if not match:
            raise ValueError("Unknown conversation date")
        added = date(*map(int, match.groups())).isoformat()
        groups.setdefault(sid, [])
        marked.setdefault(sid, [])
        chunks: list[list[tuple[int, dict]]] = []
        for number, turn in enumerate(turns):
            if turn.get("role") not in ("user", "assistant", "system"):
                raise ValueError("Unknown speaker")
            if not isinstance(turn.get("content"), str):
                raise ValueError("Turn content must be text")
            if turn["role"] == "user" or not chunks:
                chunks.append([])
            chunks[-1].append((number, turn))
        for chunk in chunks:
            ident = f"session-{occurrence:04d}-turn-{chunk[0][0]:03d}"
            body = f"Conversation time: {stamp}\n\n" + "\n\n".join(
                f"{t['role']}:\n{t['content']}" for _, t in chunk)
            notes.append({
                "id": ident, "title": " ".join(chunk[0][1]["content"].split()[:8]),
                "summary": " ".join(body.split())[:150], "area": "me",
                "topic": f"session-{occurrence:04d}", "kind": "fact", "added": added,
                "source": "Public benchmark conversation", "body": body,
            })
            groups[sid].append(ident)
            if any(turn.get("has_answer") for _, turn in chunk):
                marked[sid].append(ident)
    targets = list(dict.fromkeys(item.get("answer_session_ids", [])))
    if any(sid not in groups for sid in targets):
        raise ValueError("An annotated answer session is absent")
    return notes, {
        "session_groups": [groups[sid] for sid in targets],
        "annotated_turn_groups": [marked[sid] for sid in targets],
        "missing_turn_labels": sum(not marked[sid] for sid in targets),
    }
