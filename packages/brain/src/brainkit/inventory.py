"""The brain's stock, as one table: every entry, skill and filed document, with the details a
person governs it by (owner, origin, confidence, review cadence, sensitivity), how much it
has been used, and how often it has changed.

It reads three sources and writes nothing: the notes themselves, the decision journal
(changes, and the conversation a note was proposed in), and the session ledger (use).

ORIGIN. A note says where it came from in `origin` (`<kind>:<reference>`: `conversation:`,
`file:`, `meeting:`, `output:`, `work:`, `doc:`). Older notes only have a free-text `source`;
their origin is read from it (`origin_of`), so nothing has to be rewritten.
"""
from __future__ import annotations

from . import baseline, history, statements, util
from . import frontmatter as fm

ORIGIN_KINDS = {
    "conversation": "An AI conversation",
    "workspace": "The workspace",
    "work": "AI work",
    "file": "A file",
    "meeting": "A meeting",
    "output": "An output",
    "doc": "A doc",
    "you": "You",
    "import": "Imported",
    # Where a filed item (a document or an asset) came from (uploads.ORIGINS).
    "capture": "A capture",
    "library": "The Library",
    "project": "A project",
    "skill": "A skill",
    "run": "A run",
    "movein": "Moving in",
    "upload": "An upload in the app",
    "chat": "An AI conversation",
    "folder": "A swept folder",
    "unknown": "Not recorded",
}


def origin_of(note, created: dict | None = None) -> dict:
    """{"kind", "ref", "label"}: where a note came from. `created` is the journal record
    that made it live, when there is one (it names the conversation)."""
    session = str((created or {}).get("session") or "")
    raw = note.origin
    source = str(note.meta.get("source") or "").strip()
    if raw:
        kind, _, ref = raw.partition(":")
        kind = kind.strip().lower()
        return {"kind": kind if kind in ORIGIN_KINDS else "unknown", "ref": ref.strip(),
                "label": source or raw}
    low = source.lower()
    if low.startswith("workspace"):
        kind = "workspace"
    elif low.startswith(("sync:", "intake:")) or " proposed by " in low and low.split()[0] in (
            "document", "asset", "reference", "file"):
        kind = "file"
    elif low.startswith(("scout:",)) or "distill" in low or low.startswith("imported"):
        kind = "import"
    elif low.startswith(("captured by", "created by")):
        kind = "you"
    elif low.startswith("proposed by"):
        kind = "conversation"
    elif source:
        kind = "you"
    else:
        kind = "unknown"
    return {"kind": kind, "ref": session if kind == "conversation" else "", "label": source}


def _created(brain) -> dict[str, dict]:
    """{note id: the journal record that first made it live}."""
    out: dict[str, dict] = {}
    for record in brain.vault.decisions():
        if record.get("action") in ("approved", "auto-applied") and record.get("note") \
                and str(record.get("kind") or "").endswith(".create"):
            out.setdefault(str(record["note"]), record)
    return out


def note_row(st, note, *, created=None, changes=0, use=None) -> dict:
    """One entry as the inventory lists it."""
    config = st.config
    today = util.today_date()
    days = config.review_days_for(note)
    due = note.review_due(days)
    use = use or {}
    origin = origin_of(note, created)
    return {
        "type": "note", "id": note.id, "title": note.title, "summary": note.summary,
        "kind": note.kind, "area": note.area, "area_label": config.area_label(note.area),
        "topic": note.route_key, "topic_label": st.index.topic_label(note.route_key),
        "scope": note.scope, "partition": note.partition, "status": note.status,
        "live": note.live, "load": note.load, "tokens": note.tokens,
        # a must-hold's domains, the words that bring it in, its line, and whether the
        # startup context shows that line in full
        "applies_to": note.applies_to if note.must_hold else [],
        "triggers": note.triggers if note.must_hold else [],
        "must_text": note.must_text if note.must_hold else "",
        "critical": bool(note.must_hold and note.critical),
        # why a change to it waits for a reason (baseline.py), or ""; marked by the owner
        "baseline": (baseline.why(note, config, int(use.get("d30") or 0)) or "")
        if note.live else "",
        "baseline_marked": bool(fm.as_bool(note.meta.get("baseline"))),
        # when a changing value was true, and the last day it holds
        "as_of": note.as_of or None, "valid_until": note.valid_until or None,
        "added": note.added, "updated": util.day_text(note.meta.get("updated")),
        "revised": util.day_text(note.meta.get("revised")),
        "verified": note.verified, "confidence": note.confidence,
        # a person confirmed it since it went live (`verified`), not only approved it
        "checked": bool(str(note.meta.get("verified") or "").strip()),
        "stale": note.stale_reason(today, days) if note.live else None,
        "review_days": note.review_due_days(days),
        "review_days_set": bool(str(note.meta.get("review_days") or "").strip()),
        "review_by": str(note.meta.get("review_by") or "")[:10] or None,
        "review_due": due.isoformat() if due else None,
        "owner": note.owner or config.default_owner, "owner_set": bool(note.owner),
        "origin": origin, "classification": note.classification,
        # the note as a statement: its kind, who said it, when the Brain learned it, when it
        # was last confirmed, when to check it again, its tier (statements.py)
        "statement": statements.describe(note, config, origin["kind"]),
        "supersedes": [i.strip() for i in str(note.meta.get("supersedes") or "").split(",")
                       if i.strip() and i.strip().lower() != "none"],
        "superseded_by": str(note.meta.get("superseded_by") or "") or None,
        "changes": changes, "path": note.path, "hash": note.body_hash,
        "uses": {"total": use.get("total", 0), "d7": use.get("d7", 0),
                 "d30": use.get("d30", 0), "last": use.get("last")},
    }


def rows(brain, *, notes=None, include_archived=True) -> list[dict]:
    """Every entry (live, and archived when asked), skill and filed document, with use."""
    st = brain.state()
    try:
        used = brain.ledger.usage_table()
    except Exception:  # an unreadable ledger costs the counts, not the table
        used = {}
    created = _created(brain)
    changes = history.change_counts(brain)
    pool = list(notes) if notes is not None else (
        list(st.index.notes.values())
        + (list(st.index.archived.values()) if include_archived else []))
    out = [note_row(st, n, created=created.get(n.id), changes=changes.get(n.id, 0),
                    use=used.get(("note", n.id))) for n in pool]
    if notes is not None:
        return out
    for skill in st.index.skills.values():
        use = used.get(("skill", skill.name)) or {}
        out.append({"type": "skill", "id": skill.name, "title": skill.name,
                    "summary": skill.summary, "kind": "skill", "area": "skills",
                    "area_label": "Skills", "topic": f"skills/{skill.category}",
                    "topic_label": skill.category.replace("-", " ").capitalize(),
                    "scope": skill.scope, "partition": skill.partition, "status": "approved",
                    "live": True, "tokens": skill.tokens, "path": skill.path,
                    "owner": st.config.default_owner, "owner_set": False,
                    "uses": {"total": use.get("total", 0), "d7": use.get("d7", 0),
                             "d30": use.get("d30", 0), "last": use.get("last")}})
    for ref in st.index.references.values():
        use = used.get(("reference", ref.path)) or {}
        out.append({"type": "reference", "id": ref.path, "title": ref.title, "summary": "",
                    "kind": "reference", "area": "references", "area_label": "Documents",
                    "topic": "references", "topic_label": "Filed documents",
                    "scope": "", "partition": None, "status": "approved", "live": True,
                    "tokens": ref.tokens, "path": ref.path,
                    "owner": st.config.default_owner, "owner_set": False,
                    "uses": {"total": use.get("total", 0), "d7": use.get("d7", 0),
                             "d30": use.get("d30", 0), "last": use.get("last")}})
    return out
