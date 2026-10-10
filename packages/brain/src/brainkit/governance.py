"""Governance: how knowledge changes, and who has to agree.

ONE RULE, DECLARED IN brain.json:

    auto_apply_own_scope   a change inside the proposer's own person scope applies at once
    auto_apply_scopes      extra scope patterns that apply at once (fnmatch, e.g. "person:*")
    everything else        waits in vault/inbox/ for the approver

Every outcome is appended to `journal/decisions.jsonl` with the full proposed content, so a
rejected proposal is recoverable and an applied one is attributable. With `git.auto_commit`
on, each change is committed with exactly the files it touched.

NAMING AND PLACEMENT (area layout). A new note gets a `title` saying what it is for, a
one-line `summary`, and an id made from the title; its file is `<added>-<id>.md` under
`knowledge/<area>/<topic>/`. A note proposed into a topic that does not exist yet comes back
with the closest existing topics, and the owner can move it when approving (`edits` with
`area`, `topic` or `title`), so new knowledge is not stranded in a folder of its own.

AUTOMATIC CAPTURE. Agents propose as work happens (see capture.py), so two guards keep the
inbox a place a person can actually review: proposing the same text twice returns the waiting
proposal instead of a second one, and one conversation (session) may make at most
`governance.max_proposals_per_session` proposals (default 12). Every decision records the
session that produced it. Skills, documents and assets go through uploads.py, staged outside
git until approved.

PRESETS AND THE CAPTURE POLICY. What the owner's own AI notes in a conversation (`chat`), and
what a swept folder brings (`folder`), applies at once or waits by what it is: a fact, a
decision, progress, a preference, a rule, a convention, a change to an entry, or a file. A
preset (`governance.preset`: personal, careful or regulated) is the starting point; brain.json
`governance.capture` keeps only what the owner changed on top of it. A vault without a preset
is `careful`: only files go in at once. Whatever the policy says, a capture that names an entry
it replaces or contradicts, nearly repeats a live one, or carries text that does not belong in
a note waits for the owner. Each capture that applies is an undo point of its own.

WHAT THIS MODULE NEVER DOES: approve on behalf of an AI. `approve` and `reject` are owner
operations for the CLI and the local UI; the MCP agent surface cannot reach them, and no
text inside a proposal can change who is asking.
"""
from __future__ import annotations

import fnmatch
import re

from . import frontmatter as fm
from . import statements, uploads, util
from .model import CONFIDENCE, LEGACY_KINDS, LOADS, MAX_CRITICAL, MUST_HOLD, listish
from .scopes import Scopes

KINDS = ("note.create", "note.update", "note.archive", "focus.create")
RESERVED = {"status", "proposal", "approved_by", "approved_at", "revised"}
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,120}$")
NOTE_KINDS = statements.NOTE_KINDS  # one vocabulary (statements.py)
RULE_START = re.compile(r"^\s*(never|always|do not|don't|avoid|must|every|only|stage|use|run|"
                        r"keep|check|verify|i prefer|i'd prefer|i want|i'd like|i would like|"
                        r"i like|i don't want|i do not want|i'd rather|i would rather|"
                        r"please always|please never)\b", re.IGNORECASE)


def title_from(text: str) -> str:
    """A short title for a note that was proposed without one: its first clause."""
    first = re.split(r"(?<=[.!?:;])\s|\n", str(text or "").strip(), maxsplit=1)[0]
    words = first.strip(" .:;").split()
    return " ".join(words[:10]) if words else "Note"


def summary_from(text: str, limit: int = 200) -> str:
    """A one-line summary for a note proposed without one: its first sentence when that fits,
    else the sentence's first words, cut at a word boundary."""
    flat = " ".join(str(text or "").split())
    first = re.split(r"(?<=[.!?])\s", flat, maxsplit=1)[0]
    return first if len(first) <= limit else util.excerpt(first, limit - 3)


def slug_from(title: str) -> str:
    """An id that says what the note is for: the title's content words, kebab-cased."""
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    content = [w for w in words if w not in util.STOPWORDS] or words
    return "-".join(content[:7])[:72].strip("-") or "note"


def unique_id(st, wanted: str) -> str:
    taken = set(st.index.notes) | set(st.index.archived) | set(st.snapshot.proposals)
    if wanted not in taken:
        return wanted
    for n in range(2, 100):
        if f"{wanted}-{n}" not in taken:
            return f"{wanted}-{n}"
    return f"{wanted}-{util.short_hash(wanted + util.now_iso(), 4)}"


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def auto_applies(config, principal: str, scope: str) -> bool:
    """Own person scope applies at once (unless the preset says otherwise); shared scopes wait
    unless a pattern says otherwise."""
    policy = config.governance
    own = policy.get("auto_apply_own_scope", PRESETS[preset_of(config)]["auto_apply_own_scope"])
    if own and scope == principal and ":" in scope:
        return True
    return any(fnmatch.fnmatch(scope, pattern)
               for pattern in policy.get("auto_apply_scopes") or [])


# WHAT THE OWNER'S OWN CAPTURES DO, by what is captured and where it came from:
# `apply` (in at once, as an undo point) or `wait` (in the review queue). An origin is `app`
# (the owner, in the workspace or the CLI), `chat` (the owner's AI, in a conversation) or
# `folder` (a folder the brain sweeps). Anyone else's changes to shared knowledge follow
# scopes (auto_applies) and wait for the approver.
CAPTURE_TYPES = statements.CAPTURE_TYPES
CAPTURE_ORIGINS = ("app", "chat", "folder")
# What changes how every AI behaves, and changes to what is there, never apply from a chat or
# a folder under any preset; a person may still let them in, one type at a time.
SHAPING = ("preference", "rule", "convention", "change")


def _matrix(chat: tuple, folder: tuple, *, files_wait: bool = False) -> dict:
    """A capture matrix: the owner's own (`app`) captures apply; `chat` and `folder` apply
    for the types named."""
    out = {}
    for kind in CAPTURE_TYPES:
        apply_file = kind == "file" and not files_wait
        out[kind] = {"app": "apply",
                     "chat": "apply" if kind in chat or apply_file else "wait",
                     "folder": "apply" if kind in folder or apply_file else "wait"}
    return out


# personal: what the owner's own AI notes as facts, decisions and progress goes in at once;
#   what changes how every AI behaves waits.
# careful: only files go in at once (a vault without a preset).
# regulated: nothing a chat or a folder brings applies without approval, files and the owner's
#   own preferences included.
PRESETS = {
    "personal": {"capture": _matrix(("fact", "decision", "progress"), ("progress",)),
                 "auto_apply_own_scope": True},
    "careful": {"capture": _matrix((), ()), "auto_apply_own_scope": True},
    "regulated": {"capture": _matrix((), (), files_wait=True), "auto_apply_own_scope": False},
}
DEFAULT_PRESET = "careful"
DEFAULT_CAPTURE = PRESETS["personal"]["capture"]  # the matrix a personal Brain starts from


def preset_of(config) -> str:
    """The Brain's preset: brain.json `governance.preset`, else careful."""
    value = str(config.governance.get("preset") or "").strip().lower()
    return value if value in PRESETS else DEFAULT_PRESET


RETENTION_DAYS = {"regulated": 730}  # else 90 (brain-logic plan 6, decision 9)


def retention_days(config) -> int:
    """How long brief text stays in the ledger: brain.json `sessions.retention_days`, else 90
    days under the personal and careful presets and 730 under regulated."""
    try:
        own = int((config.data.get("sessions") or {}).get("retention_days") or 0)
    except (TypeError, ValueError):
        own = 0
    return own if own > 0 else RETENTION_DAYS.get(preset_of(config), 90)


def capture_policy(config) -> dict:
    """{type: {origin: "apply" | "wait"}}: brain.json's `governance.capture` over the
    preset's matrix."""
    base = PRESETS[preset_of(config)]["capture"]
    out = {kind: dict(origins) for kind, origins in base.items()}
    for kind, origins in (config.governance.get("capture") or {}).items():
        if kind in out and isinstance(origins, dict):
            for origin, value in origins.items():
                if origin in CAPTURE_ORIGINS and value in ("apply", "wait"):
                    out[kind][origin] = value
    return out


def capture_type(kind: str, target: dict) -> str:
    """What a note proposal is, as the capture policy names it: a change to an entry, a rule
    (or the preference or convention it is), a convention (who you are, how you are known),
    progress (where things stand), a decision or a fact (statements.capture_type)."""
    if kind in ("note.update", "note.archive"):
        return "change"
    # An older vault's layer says what its notes are (rules, facts, ...).
    note_kind = str(target.get("kind") or LEGACY_KINDS.get(str(target.get("layer") or ""))
                    or "").strip().lower()
    return statements.capture_type(
        note_kind, str(target.get("subtype") or ""),
        decision=str(target.get("type") or "").strip().lower() == "decision")


def captures_apply(brain, who, kind, origin) -> bool:
    """Does this capture by the owner (or their AI) apply at once? Never for anyone else."""
    config = brain.state().config
    approver = config.governance.get("approver") or config.owner
    if who not in {approver} | set(config.governance.get("approvers") or []):
        return False
    origin = origin if origin in CAPTURE_ORIGINS else "chat"
    return capture_policy(config).get(kind, {}).get(origin) == "apply"


DEFAULT_SESSION_BUDGET = 12
CLOSE = 0.75  # a live note this near may say the same thing (review.CLOSE)


def check_budget(brain, session_id):
    """A refusal when this conversation has used its proposal budget, else None."""
    if not session_id:
        return None
    st = brain.state()
    limit = int(st.config.governance.get("max_proposals_per_session")
                or DEFAULT_SESSION_BUDGET)
    used = sum(1 for p in st.snapshot.proposals.values()
               if str(p.meta.get("session") or "") == session_id)
    used += sum(1 for d in brain.vault.decisions() if d.get("session") == session_id)
    if used < limit:
        return None
    return _result(
        f"This conversation has made {used} proposals, its limit is {limit}. Keep the rest "
        "for the session receipt, or ask the owner to review the inbox first.",
        {"status": "limit", "used": used, "limit": limit}, True)


def pending_duplicate(st, kind, text):
    """A waiting proposal of this kind with the same text, if any."""
    key = util.canonical(text)
    if not key:
        return None
    return next((p for p in st.snapshot.proposals.values()
                 if p.kind == kind and util.canonical(p.body) == key), None)


def _similar(brain, text, chain, partitions, limit=3):
    st = brain.state()
    notes = st.router.admitted_notes(chain, partitions)
    ranked = st.router.score_notes(text, notes)
    return [{"id": s.item.id, "score": s.score} for s in ranked[:limit] if s.score >= 0.55]


def must_hold_fields(st, base, load, applies_to, triggers, must_text, critical,
                     problems) -> dict:
    """Check the must-hold fields of a proposal and return the front matter they set.

    `applies_to` names areas (`food`), topics (`food/diet`), project ids or `*`; `triggers`
    are words and phrases that put the domain in play; `must_text` is the one line a brief
    shows; `critical` puts that line in the startup context (at most MAX_CRITICAL notes)."""
    given = {key: value for key, value in (("applies_to", applies_to), ("triggers", triggers),
                                           ("must_text", must_text), ("critical", critical))
             if value not in (None, "", [])}
    if not given:
        return {}
    effective = str(load or (base.load if base is not None else "") or "").strip().lower()
    if effective != MUST_HOLD:
        problems.append("applies_to, triggers, must_text and critical are for must-holds "
                        "(load: domain)")
        return {}
    out: dict = {}
    if "applies_to" in given:
        targets = listish(applies_to)
        unknown = [t for t in targets if t != "*" and t not in st.index.focuses
                   and t.split("/", 1)[0] not in st.config.areas]
        if unknown:
            problems.append("applies_to names no area, topic or project: "
                            + ", ".join(repr(t) for t in unknown))
        out["applies_to"] = targets
    if "triggers" in given:
        words = [t.lower() for t in listish(triggers)]
        long = [t for t in words if len(t.split()) > 6 or len(t) > 60]
        if long:
            problems.append("each trigger is a word or a short phrase: "
                            + ", ".join(repr(t) for t in long))
        if len(words) > 40:
            problems.append("at most 40 triggers")
        out["triggers"] = list(dict.fromkeys(words))
    if "must_text" in given:
        line = " ".join(str(must_text).split())
        if len(line.split()) > 40:
            problems.append("must_text is one line of at most 40 words")
        out["must_text"] = line
    if "critical" in given:
        wanted = str(critical).strip().lower() in ("true", "yes", "1", "on")
        if wanted:
            others = [n for n in st.index.notes.values() if n.must_hold and n.critical
                      and (base is None or n.id != base.id)]
            if len(others) >= MAX_CRITICAL:
                problems.append(f"at most {MAX_CRITICAL} must-holds can be critical; "
                                f"{', '.join(n.id for n in others)} already are")
        out["critical"] = wanted
    return out


def propose_note(brain, *, area=None, topic=None, text=None, scope=None, load=None,
                 principal=None, evidence="", source="", supersedes=None, summary=None,
                 title=None, note_kind=None, startup_text=None, note_id=None, target_id=None,
                 archive=False, partition=None, reason="", review_by=None, kind=None,
                 extra=None, session_id=None, force_pending=False, layer=None,
                 index_line=None, conflicts=None, origin=None, capture_origin=None,
                 applies_to=None, triggers=None, must_text=None, critical=None,
                 as_of=None, valid_until=None, **_ignored):
    """Propose a new note, a change to one (`target_id`), or its retirement (`archive`).

    `kind` is the proposal kind (note.create, note.update, ...); `note_kind` is what the note
    is (fact, rule, identity, state). `layer` and `index_line` are the older names for
    `area` and `summary`. `supersedes` names the notes a new one replaces (archived when it
    is approved), or, on a change, the notes this one now covers (a merge of two notes that
    say the same thing); `conflicts` names notes it contradicts without replacing, for the
    reviewer to settle. Both must name existing notes. `origin` says where a new note came
    from, as `<kind>:<reference>` (`file:...`, `meeting:...`, `output:...`); a proposal made
    in a conversation without one records that conversation. `capture_origin` (`chat`,
    `folder`) says the owner's own AI or a swept folder brought it: the capture policy may then
    apply it at once (see PRESETS). `as_of` is the day a changing value was true (a total, a
    count, a version) and `valid_until` the last day it holds; a newer dated value for the
    same thing is an update, not a disagreement.
    """
    st = brain.state()
    config = st.config
    area = area or layer
    placed = bool(area and topic)      # the proposer chose where it goes
    summary = summary or index_line
    layer = None
    who = brain.principal(principal)
    caller = brain.caller(who)
    if not isinstance(caller, tuple):
        return caller
    chain, seen = caller
    base = None
    if target_id:
        base = st.index.note(target_id)
        if base is None:
            return _result(f"No live note {target_id!r} to change.", {"status": "invalid"}, True)
        area = area or base.area
        topic = topic or base.topic
        scope = scope or base.scope
        partition = partition or base.partition
        text = text if text is not None else base.body
        kind = "note.archive" if archive else "note.update"
    kind = kind or "note.create"
    if not target_id and (not area or not topic) and text:
        guessed_area, guessed_topic = guess_placement(brain, text, chain)
        area = area or guessed_area
        topic = topic or guessed_topic
        extra = dict(extra or {}, placement="guessed")
    area = str(area or "").strip().lower()
    topic = str(topic or "").strip().lower()
    scope = str(scope or default_scope(brain, area, topic, chain)).strip()
    text = str(text or "").strip()
    note_kind = str(note_kind or "").strip().lower() or None
    problems = []
    if area not in config.areas:
        problems.append(f"area must be one of {', '.join(config.area_order())}")
    if note_kind and note_kind not in NOTE_KINDS and kind != "focus.create":
        problems.append(f"kind must be one of {', '.join(NOTE_KINDS)}")
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", topic):
        problems.append("topic must be a lowercase slug, for example 'voice'")
    if not st.scopes.exists(scope):
        problems.append(f"scope {scope!r} is not declared in brain.json")
    if partition and partition not in st.scopes.partitions:
        problems.append(f"partition {partition!r} is not declared in brain.json")
    if kind != "note.archive" and not text:
        problems.append("text is required")
    if load is not None and str(load).strip().lower() not in LOADS:
        problems.append("load must be standing, domain, on-demand or manual")
    if note_kind == "goal":
        # A goal steers what is kept and what agents do, never what a request receives.
        problems += statements.goal_problems(extra or {})
        load = load or "manual"
    must = must_hold_fields(st, base, load, applies_to, triggers, must_text, critical,
                            problems)
    dates = {}
    for name, value in (("as_of", as_of), ("valid_until", valid_until)):
        if str(value or "").strip():
            found = util.parse_date(value)
            if found is None:
                problems.append(f"{name} is a date (YYYY-MM-DD)")
            else:
                dates[name] = found.isoformat()
    for key in (extra or {}):
        if key in RESERVED:
            problems.append(f"{key} is set by governance, not by a proposal")
    named = {}
    for field_name, value in (("supersedes", supersedes), ("conflicts", conflicts)):
        ids = [part.strip() for part in re.split(r"[,\s]+", str(value or ""))
               if part.strip() and part.strip().lower() != "none"]
        unknown = [i for i in ids if st.index.note(i, include_archived=True) is None]
        if unknown:
            problems.append(f"{field_name} names no note {', '.join(repr(i) for i in unknown)}")
        named[field_name] = ", ".join(dict.fromkeys(ids))
    supersedes = named["supersedes"] or None
    if problems:
        return _result("Proposal refused: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    if kind == "note.create":
        duplicate = next((n for n in st.index.notes.values()
                          if util.canonical(n.body) == util.canonical(text)), None)
        if duplicate is not None:
            return _result(f"Already governed as {duplicate.id}; nothing proposed.",
                           {"status": "duplicate", "id": duplicate.id})
    waiting = pending_duplicate(st, kind, text) if kind in ("note.create",
                                                            "note.update") else None
    if waiting is not None:
        return _result(f"The same proposal is already waiting for review ({waiting.id}).",
                       {"status": "duplicate", "proposal_id": waiting.id,
                        "id": waiting.target.get("id")})
    refusal = check_budget(brain, session_id)
    if refusal:
        return refusal
    if config.uses_areas and not base:
        title = str(title or "").strip() or title_from(summary or text)
        note_id = note_id or unique_id(st, slug_from(title))
    note_id = note_id or (base.id if base else f"{area}-{topic}-{util.short_hash(text, 6)}")
    if not ID_PATTERN.match(note_id):
        return _result(f"Proposal refused: {note_id!r} is not a valid note id.",
                       {"status": "invalid"}, True)
    if kind == "note.create" and (note_id in st.index.notes or note_id in st.index.archived):
        note_id = f"{note_id}-{util.short_hash(text + util.now_iso(), 4)}"
    target = dict(base.meta) if base else {}
    area_key = "area" if (config.uses_areas or "area" in target) else "layer"
    target.pop("layer" if area_key == "area" else "area", None)
    target.update({
        "id": note_id, area_key: area, "topic": topic, "scope": scope,
        "load": str(load or target.get("load") or "on-demand").strip().lower(),
        "source": source or target.get("source") or f"proposed by {who}",
        "evidence": evidence or target.get("evidence") or "",
        "classification": target.get("classification") or "internal",
    })
    if kind == "note.create":
        target["added"] = util.today()
        target["supersedes"] = supersedes or "none"
        origin = str(origin or "").strip() or (f"conversation:{session_id}" if session_id
                                               else "")
        if origin:
            target["origin"] = origin
    elif kind == "note.update" and supersedes:
        # A merge: this note now covers what the named notes say, and they retire with it.
        earlier = [i.strip() for i in str(target.get("supersedes") or "").split(",")
                   if i.strip() and i.strip().lower() != "none"]
        merged = [i for i in dict.fromkeys(earlier + supersedes.split(", ")) if i != note_id]
        target["supersedes"] = ", ".join(merged) or "none"
    if partition:
        target["partition"] = partition
    if area_key == "area":
        if title:
            target["title"] = str(title).strip()
        target.setdefault("title", title_from(summary or text))
        if summary:
            target["summary"] = " ".join(str(summary).split())
            target.pop("index_line", None)
        elif not target.get("summary") and not target.get("index_line"):
            target["summary"] = summary_from(text)
        if kind == "focus.create":
            target["kind"] = "focus"
        elif note_kind:
            target["kind"] = note_kind
        elif not target.get("kind"):
            target["kind"] = "rule" if RULE_START.match(text) else "fact"
    elif summary:
        target["index_line"] = summary
    if startup_text:
        target["startup_text"] = startup_text
    target.update(must)
    target.update(dates)
    if review_by:
        target["review_by"] = review_by
    if load is None and kind == "note.create" and st.scopes.kind(scope) == "person" \
            and target.get("kind") == "rule":
        # A rule someone sets for themselves ("I want plain-text drafts") governs all of their
        # work, so it rides in their startup context unless they say otherwise.
        target["load"] = "standing"
    for key, value in (extra or {}).items():
        target[key] = value
    if placed and "placement" not in (extra or {}):
        target["placement"] = "chosen"     # replaces a "guessed" the note may carry
    target.pop("status", None)
    proposal_id = (note_id if kind == "note.create" else
                   f"{kind.split('.')[1]}-{note_id}-{util.short_hash(text + util.now_iso(), 4)}")
    header = {"kind": kind, "status": "pending", "created": util.now_iso(), "proposer": who,
              "reason": reason or "", "session": session_id or ""}
    if base is not None:
        header["base_hash"] = base.body_hash
    if named["conflicts"]:
        header["conflicts"] = named["conflicts"]
    similar = _similar(brain, text, chain, []) if kind == "note.create" and text else []
    if similar:
        header["similar"] = ", ".join(f"{s['id']} ({s['score']:.2f})" for s in similar)
    placement_note = ""
    route_key = f"{area}/{topic}"
    if kind == "note.create" and text and not any(
            n.route_key == route_key for n in st.index.notes.values()):
        suggestions = [s for s in suggest_placement(brain, text, chain) if s["topic"] != route_key]
        if suggestions:
            header["suggested"] = ", ".join(f"{s['topic']} ({s['score']:.2f})"
                                            for s in suggestions)
            placement_note = (f" {route_key} is a new topic. Closest existing topics: "
                              f"{header['suggested']}; propose it there if one fits, or the "
                              "owner can move it when approving.")
    capture = capture_type(kind, target) if capture_origin in CAPTURE_ORIGINS else None
    if capture:
        header["capture"] = f"{capture}:{capture_origin}"
    applies = auto_applies(config, who, scope)
    if not applies and capture and not force_pending and not (
            named["conflicts"] or supersedes or util.text_flags(text)
            or any(s["score"] >= CLOSE for s in similar)):
        applies = captures_apply(brain, who, capture, capture_origin)
    held = None
    if applies and not force_pending:
        # Nothing goes in on its own over a note it may disagree with, or over a baseline:
        # checks 1 and 2 read it first, and what they find waits for the owner.
        from . import baseline
        held = baseline.guard(brain, kind, text, base=base, area=area, topic=topic,
                              chain=chain, partitions=seen or (),
                              supersedes=supersedes or "", note_id=note_id,
                              as_of=target.get("as_of") or "")
        if held:
            applies = False
            header["tension"] = held["id"]
            header["tension_why"] = held["why"]
    if applies and not force_pending:
        from . import checkpoints
        label = f"Went in on its own: {target.get('title') or note_id}"
        with checkpoints.batch(brain, actor=who, label=label) as batch:
            applied = _apply(brain, proposal_id, header, target, text, actor=who, auto=True)
            if not applied.is_error:
                batch.decisions.append({"action": "approved", "proposal": proposal_id,
                                        "kind": kind, "note": note_id,
                                        "title": str(target.get("title") or note_id)})
        if not applied.is_error:
            applied.data["checkpoint"] = batch.checkpoint
            if header.get("capture") and not auto_applies(config, who, scope):
                applied.text = applied.text.replace(
                    " It applied immediately because it is inside your own scope.",
                    f" It applied at once: the owner lets {capture} from {capture_origin} in.")
        if placement_note and not applied.is_error:
            applied.text += placement_note
            applied.data["suggested"] = header.get("suggested")
        return applied
    relpath = brain.vault.write_proposal(proposal_id, header, target, text)
    outcome = brain.after_write([brain.vault.path(relpath)],
                                f"Propose {kind} {note_id} ({scope})")
    return _result(
        f"Proposed {note_id} ({area}/{topic}, {scope}) for review by "
        f"{config.governance.get('approver') or config.owner}. It is not live until approved."
        + (f" It would have applied at once, but it waits: {held['why']} "
           f"(“{held['title']}”, {held['id']})." if held else "")
        + (f" Similar existing notes: {header['similar']}." if similar else "")
        + placement_note,
        {"status": "pending", "proposal_id": proposal_id, "id": note_id, "path": relpath,
         "similar": similar, "suggested": header.get("suggested"), "held": held,
         "commit": outcome.get("commit")})


def default_scope(brain, area, topic, chain):
    """Where a note goes when the proposer names no scope: where its topic already lives.

    Most shared topics live at company scope, so an unscoped rule or fact is proposed there
    and waits for review, instead of quietly becoming a personal note that applies at once.
    A topic that only exists in the caller's own scope (preferences) stays personal.
    """
    counts: dict[str, int] = {}
    for note in brain.state().index.notes.values():
        if note.area == area and note.topic == topic and note.scope in chain:
            counts[note.scope] = counts.get(note.scope, 0) + 1
    if counts:
        return max(counts, key=lambda scope: (counts[scope], -chain.index(scope)))
    return chain[0]


def suggest_placement(brain, text, chain, partitions=(), limit=3) -> list[dict]:
    """The existing topics a piece of text fits best: [{"topic", "score"}], best first.

    A topic's score is the better of its own description's match and its best note's match,
    so a topic fits when it is about the subject or already holds something close to it."""
    st = brain.state()
    notes = [n for n in st.router.admitted_notes(chain, partitions)
             if not st.config.is_focus(n) and n.kind != "identity"]
    best: dict[str, float] = {}
    for scored in st.router.score_notes(text, notes):
        key = scored.item.route_key
        best[key] = max(best.get(key, 0.0), scored.score)
    for key, value in st.router.topic_relevance(text, set(best)).items():
        best[key] = max(best.get(key, 0.0), value)
    ranked = sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"topic": key, "score": round(value, 3)} for key, value in ranked[:limit]
            if value >= 0.3]


FIRST_PERSON = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|my|me|mine|myself)\b", re.I)


def personal_topic(brain, person) -> tuple[str, str] | None:
    """Where a person's own notes belong: their folder in the people area (where their
    profile already is, else people/<their name>), else where their standing notes live."""
    st = brain.state()
    own = [n for n in st.index.notes.values()
           if n.scope == person and not st.config.is_focus(n)]

    def most(notes):
        counts: dict[str, int] = {}
        for note in notes:
            counts[note.route_key] = counts.get(note.route_key, 0) + 1
        area, _, topic = max(counts.items(), key=lambda kv: (kv[1], kv[0]))[0].partition("/")
        return area, topic

    for level in st.config.structure.get("scope_levels") or []:
        container = str(level.get("container") or "")
        if level.get("kind") != "person" or container not in st.config.areas:
            continue
        inside = [n for n in own if n.area == container]
        if inside:
            return most(inside)
        name = st.scopes.label(person).split(":")[-1]
        return container, slug_from(name) or "me"
    standing = [n for n in own if n.standing]
    return most(standing) if standing else None


def guess_placement(brain, text, chain, partitions=()):
    """(area, topic) that fits the text best, or a general fallback when nothing is close."""
    st = brain.state()
    suggestions = suggest_placement(brain, text, chain, partitions, limit=1)
    if suggestions and suggestions[0]["score"] >= 0.45:
        area, _, topic = suggestions[0]["topic"].partition("/")
        return area, topic
    return ("topics", "general") if st.config.uses_areas else ("facts", "notes")


def remember(brain, text, *, principal=None, scope=None, session_id=None, capture_origin=None):
    """Capture one durable thought fast: guess its topic, file it in the caller's own scope."""
    text = str(text or "").strip()
    if not text:
        return _result("Nothing to remember.", {"status": "invalid"}, True)
    who = brain.principal(principal)
    caller = brain.caller(who)
    if not isinstance(caller, tuple):
        return caller
    chain, partitions = caller
    area, topic = guess_placement(brain, text, chain, partitions)
    own = scope or who
    if brain.state().scopes.kind(own) == "person" and FIRST_PERSON.search(text):
        # "I prefer plain-text drafts" is about the person, not the company topic its words
        # happen to match: it goes where that person's own notes live.
        area, topic = personal_topic(brain, own) or (area, topic)
    return propose_note(brain, area=area, topic=topic, text=text, scope=scope or who,
                        principal=who, source=f"captured by {who} with remember",
                        evidence="owner capture", reason="quick capture; placement guessed",
                        extra={"placement": "guessed"}, session_id=session_id,
                        capture_origin=capture_origin)


def inbox(brain, **_ignored):
    st = brain.state()
    rows = []
    for proposal in sorted(st.snapshot.proposals.values(), key=lambda p: p.created):
        area = proposal.target.get("area") or proposal.target.get("layer")
        route_key = f"{area}/{proposal.target.get('topic')}"
        extra = {"files": [], "purpose": None, "preview": None}
        if proposal.kind in uploads.UPLOAD_KINDS:
            extra.update(uploads.preview(brain, proposal))
        if proposal.kind.startswith("skill."):
            route_key = f"skills/{proposal.target.get('category')}/{proposal.target.get('name')}"
        if proposal.kind == "note.challenge":
            challenged = st.index.note(str(proposal.target.get("id") or ""))
            route_key = challenged.route_key if challenged is not None else ""
        rows.append({
            "id": proposal.id, "kind": proposal.kind, "scope": proposal.scope,
            "route_key": route_key, **extra,
            "title": proposal.target.get("title") or proposal.target.get("name") or "",
            "note_summary": proposal.target.get("summary") or proposal.target.get("index_line")
            or "", "suggested": proposal.meta.get("suggested") or "",
            "created": proposal.created, "proposer": proposal.proposer,
            "summary": proposal.summary, "similar": proposal.meta.get("similar") or "",
            "conflicts": proposal.meta.get("conflicts") or "",
            "session": str(proposal.meta.get("session") or ""),
            "reason": proposal.meta.get("reason") or "", "path": proposal.path,
            "body": proposal.body, "target": proposal.target,
            "current_body": (st.index.note(proposal.target.get("id")).body
                             if proposal.kind != "note.create"
                             and st.index.note(proposal.target.get("id")) else None),
        })
    if not rows:
        return _result("The inbox is empty.", {"proposals": []})
    text = "\n".join(f"- `{r['id']}` [{r['kind']}] {r['route_key']} ({r['scope']}, "
                     f"{r['created'][:10]}): {r['summary']}" for r in rows)
    return _result(f"{len(rows)} pending proposal(s):\n{text}", {"proposals": rows})


def _require_approver(brain, actor):
    config = brain.state().config
    approver = config.governance.get("approver") or config.owner
    approvers = {approver} | set(config.governance.get("approvers") or [])
    who = brain.principal(actor)
    if who not in approvers:
        return None, _result(f"{who} cannot decide proposals; approver is {approver}.",
                             {"status": "forbidden"}, True)
    return who, None


def approve(brain, proposal_id, *, actor=None, edits=None, body=None, reason=""):
    """The owner keeps a proposal. One that revises or retires a baseline needs a `reason`
    (baseline.reason_problem), and with `revision_delay` on, a revision of a rule, a standing
    note or a must-hold is scheduled for DELAY_HOURS later instead of applied now."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    st = brain.state()
    proposal = st.snapshot.proposals.get(str(proposal_id))
    if proposal is None:
        return _result(f"No pending proposal {proposal_id!r}.", {"status": "missing"}, True)
    if proposal.kind == "note.challenge":
        from . import dissent
        return dissent.apply(brain, proposal, actor=who)
    target = dict(proposal.target)
    for key, value in (edits or {}).items():
        if key in RESERVED or key == "id":
            continue
        target[key] = value
    if {"area", "topic", "layer"} & set(edits or {}):
        target["placement"] = "chosen"     # the approver chose the place
    text = proposal.body if body is None else str(body)
    if proposal.kind in uploads.UPLOAD_KINDS:
        return uploads.apply(brain, proposal, actor=who, edits=edits, body=body)
    if proposal.kind in ("note.update", "note.archive"):
        current = st.index.note(target.get("id"))
        if current is None:
            return _result(f"{target.get('id')} is no longer live; reject this proposal.",
                           {"status": "conflict"}, True)
        base_hash = proposal.meta.get("base_hash")
        if base_hash and current.body_hash != base_hash and body is None:
            return _result(
                f"{current.id} changed since this proposal was written. Review the current text "
                "and approve with an explicit body, or reject.", {"status": "conflict",
                                                                  "current": current.body}, True)
    from . import baseline
    revision = None
    found = baseline.revised(brain, proposal.kind, target)
    if found:
        note, why = found
        problem = baseline.reason_problem(brain, note, reason)
        if problem:
            return _result(f"“{note.title}” is a baseline ({why}). {problem}",
                           {"status": "needs_reason", "note": note.id, "baseline": why}, True)
        revision = {"note": note.id, "why": why, "reason": " ".join(str(reason).split())}
        if delays(st.config) and baseline.weighty(note):
            return _schedule(brain, proposal, target, text, revision, who)
    return _apply(brain, proposal.id, dict(proposal.meta), target, text, actor=who,
                  proposal_path=proposal.path, revision=revision)


DELAY_HOURS = 24  # how long a scheduled revision of a rule or must-hold waits


def delays(config) -> bool:
    """Does the owner want a day to think before a rule or a must-hold changes?"""
    return bool(config.governance.get("revision_delay"))


def _schedule(brain, proposal, target, text, revision, who):
    """Keep the decision, apply it DELAY_HOURS from now: the proposal waits, marked with when
    it goes in, who decided and why, until `apply_scheduled` applies it or the owner cancels
    (`unschedule`)."""
    import datetime as dt
    due = (util.now() + dt.timedelta(hours=DELAY_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = dict(proposal.meta, scheduled_for=due, scheduled_by=who,
                  scheduled_reason=revision["reason"])
    relpath = brain.vault.write_proposal(proposal.id, header, target, text)
    record = {"at": util.now_iso(), "action": "scheduled", "by": who, "proposal": proposal.id,
              "kind": proposal.kind, "note": revision["note"], "due": due,
              "reason": revision["reason"]}
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(relpath), brain.vault.path(decisions)],
                                f"Scheduled {proposal.id} for {due}")
    title = str(target.get("title") or target.get("id") or proposal.id)
    return _result(f"Scheduled: “{title}” goes in at {due} unless you cancel it "
                   "before then.",
                   {"status": "scheduled", "id": str(target.get("id") or ""), "due": due,
                    "title": title, "commit": outcome.get("commit")})


def unschedule(brain, proposal_id, *, actor=None):
    """The owner cancels a scheduled revision: the proposal waits for a decision again."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    proposal = brain.state().snapshot.proposals.get(str(proposal_id))
    if proposal is None or not proposal.meta.get("scheduled_for"):
        return _result(f"Nothing scheduled for {proposal_id!r}.", {"status": "missing"}, True)
    header = {k: v for k, v in proposal.meta.items() if not str(k).startswith("scheduled_")}
    relpath = brain.vault.write_proposal(proposal.id, header, dict(proposal.target),
                                         proposal.body)
    record = {"at": util.now_iso(), "action": "unscheduled", "by": who,
              "proposal": proposal.id, "kind": proposal.kind}
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(relpath), brain.vault.path(decisions)],
                                f"Cancelled the scheduled {proposal.id}")
    title = str(proposal.target.get("title") or proposal.id)
    return _result(f"Cancelled: “{title}” waits for your decision again.",
                   {"status": "unscheduled", "id": proposal.id, "title": title,
                    "commit": outcome.get("commit")})


def apply_scheduled(brain, *, now=None):
    """Scheduled revisions whose time has come go in, each as an undo point of its own. One
    whose note changed or went since waits for a decision again."""
    from . import baseline, checkpoints
    moment = (now or util.now()).strftime("%Y-%m-%dT%H:%M:%SZ")
    st = brain.state()
    due = sorted((p for p in st.snapshot.proposals.values()
                  if str(p.meta.get("scheduled_for") or "")
                  and str(p.meta["scheduled_for"]) <= moment),
                 key=lambda p: (str(p.meta["scheduled_for"]), p.id))
    applied, returned = [], []
    for proposal in due:
        who = str(proposal.meta.get("scheduled_by") or "")
        target = dict(proposal.target)
        header = {k: v for k, v in proposal.meta.items() if not str(k).startswith("scheduled_")}
        current = (brain.state().index.note(target.get("id"))
                   if proposal.kind in ("note.update", "note.archive") else None)
        base = proposal.meta.get("base_hash")
        if proposal.kind in ("note.update", "note.archive") and (
                current is None or (base and current.body_hash != base)):
            unschedule(brain, proposal.id, actor=who)
            returned.append(proposal.id)
            continue
        found = baseline.revised(brain, proposal.kind, target)
        revision = ({"note": found[0].id, "why": found[1],
                     "reason": str(proposal.meta.get("scheduled_reason") or "")}
                    if found else None)
        title = str(target.get("title") or target.get("id") or proposal.id)
        with checkpoints.batch(brain, actor=who, label=f"Went in as scheduled: {title}") as batch:
            result = _apply(brain, proposal.id, header, target, proposal.body, actor=who,
                            proposal_path=proposal.path, revision=revision)
            if not result.is_error:
                batch.decisions.append(_summary("approve", proposal.id, proposal, result.data))
        if not result.is_error:
            applied.append(proposal.id)
    return _result(f"{len(applied)} scheduled change(s) went in."
                   + (f" {len(returned)} wait(s) for a decision again: the note changed."
                      if returned else ""),
                   {"applied": applied, "returned": returned})


def reject(brain, proposal_id, reason="", *, actor=None):
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    st = brain.state()
    proposal = st.snapshot.proposals.get(str(proposal_id))
    if proposal is None:
        return _result(f"No pending proposal {proposal_id!r}.", {"status": "missing"}, True)
    record = {"at": util.now_iso(), "action": "rejected", "by": who, "proposal": proposal.id,
              "kind": proposal.kind, "reason": str(reason or ""), "target": proposal.target,
              "body": proposal.body, "proposer": proposal.proposer,
              "session": str(proposal.meta.get("session") or "")}
    if proposal.meta.get("capture"):
        record["capture"] = str(proposal.meta["capture"])
    decisions = brain.vault.append_decision(record)
    brain.vault.remove_file(proposal.path)
    if proposal.kind in uploads.UPLOAD_KINDS:
        uploads.discard(brain, proposal)
    outcome = brain.after_write([brain.vault.path(decisions), brain.vault.path(proposal.path)],
                                f"Reject {proposal.id}" + (f": {reason}" if reason else ""))
    return _result(f"Rejected {proposal.id}.", {"status": "rejected", "id": proposal.id,
                                                "commit": outcome.get("commit")})


def _apply(brain, proposal_id, header, target, text, *, actor, auto=False, proposal_path=None,
           revision=None):
    st = brain.state()
    config = st.config
    kind = str(header.get("kind") or "note.create")
    note_id = str(target["id"])
    touched = []
    now = util.now_iso()
    moved_from = None
    if kind in ("note.update", "note.archive"):
        current = st.index.note(note_id)
        relpath = current.path
        meta = dict(current.meta)
        meta.update({k: v for k, v in target.items() if k not in RESERVED})
        meta["updated"] = util.today()
        meta["status"] = "archived" if kind == "note.archive" else "approved"
        body = current.body if kind == "note.archive" else text
        if meta.get("area") and (meta.get("area"), meta.get("topic")) != (current.area,
                                                                            current.topic):
            # Moved to another area or topic: the file follows, keeping its dated name.
            moved_from = relpath
            relpath = brain.vault.note_path(meta, config.structure.get("scope_levels") or [],
                                            config.structure.get("partition_kinds") or [])
    else:
        meta = dict(target)
        meta["status"] = "approved"
        body = text
        relpath = brain.vault.note_path(meta, config.structure.get("scope_levels") or [],
                                        config.structure.get("partition_kinds") or [])
    meta["approved_by"] = actor
    meta["approved_at"] = now
    if kind in ("note.update", "note.archive") and \
            util.canonical(body) == util.canonical(current.body):
        # A new title, summary or place is not new knowledge: the note keeps the date its
        # text last changed, which is what the router's freshness lift reads.
        meta["revised"] = (current.meta.get("revised") or current.meta.get("approved_at")
                           or current.meta.get("added") or now)
    else:
        meta["revised"] = now
    brain.vault.write_note(relpath, meta, body)
    touched.append(brain.vault.path(relpath))
    if moved_from and moved_from != relpath:
        brain.vault.remove_file(moved_from)
        touched.append(brain.vault.path(moved_from))
    superseded = []
    for old_id in str(meta.get("supersedes") or "").split(","):
        old_id = old_id.strip()
        old = st.index.note(old_id) if old_id and old_id.lower() != "none" else None
        if old is not None and old.id != note_id:
            old_meta = dict(old.meta, status="archived", superseded_by=note_id,
                            updated=util.today())
            brain.vault.write_note(old.path, old_meta, old.body)
            touched.append(brain.vault.path(old.path))
            superseded.append(old.id)
    record = {"at": now, "action": "auto-applied" if auto else "approved", "by": actor,
              "proposal": proposal_id, "kind": kind, "note": note_id, "path": relpath,
              "scope": meta.get("scope"), "superseded": superseded,
              "proposer": header.get("proposer") or actor,
              "session": str(header.get("session") or ""), "hash": util.sha256(body.strip()),
              "file_hash": brain.vault.file_hash(relpath)}
    if header.get("capture"):
        record["capture"] = str(header["capture"])
    if kind in ("note.update", "note.archive"):
        record["previous_hash"] = current.body_hash
    if header.get("reason"):
        record["reason"] = str(header["reason"])
    if revision:
        # A baseline revised: which note, why it was a baseline, and the owner's reason.
        record["baseline_revised"] = dict(revision)
    decisions = brain.vault.append_decision(record)
    touched.append(brain.vault.path(decisions))
    if proposal_path:
        brain.vault.remove_file(proposal_path)
        touched.append(brain.vault.path(proposal_path))
    verb = "Applied" if auto else "Approved"
    outcome = brain.after_write(touched, f"{verb} {kind} {note_id} ({meta.get('scope')})")
    return _result(
        f"{verb} {note_id} ({meta.get('area') or meta.get('layer')}/{meta.get('topic')}, "
        f"{meta.get('scope')})."
        + (" It applied immediately because it is inside your own scope." if auto else "")
        + (f" Superseded: {', '.join(superseded)}." if superseded else ""),
        {"status": "applied" if auto else "approved", "id": note_id, "path": relpath,
         "superseded": superseded, "commit": outcome.get("commit"),
         "kernel": outcome.get("kernel")})


def decide(brain, decisions, *, actor=None, label=None, source=None):
    """Apply a batch as one undo point: [{"id", "action", "reason", "edits", "body"}].

    `action` is approve (with a `reason` when it revises a baseline), reject or unschedule
    (a scheduled revision) (`id` a proposal); or, for an entry (`id` a note): archive,
    edit (`body`, `edits` title and summary), restore (`ref`, a version from `history`),
    unarchive, update (`fields`, see FIELDS), verify (`confidence`), or mark (`state` stale
    or disputed, with a `reason`). The result carries each outcome and the undo point
    (`checkpoint`), or None when nothing changed."""
    from . import checkpoints
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    results = []
    # One undo point, and one kernel refresh and commit for the whole batch.
    with checkpoints.batch(brain, actor=who, label=label, source=source) as batch:
        with brain.deferring() as deferred:
            for item in decisions or []:
                action = str(item.get("action") or "").lower()
                item_id = str(item.get("id") or "")
                proposal = brain.state().snapshot.proposals.get(item_id)
                if action == "approve":
                    res = approve(brain, item_id, actor=who, edits=item.get("edits"),
                                  body=item.get("body"), reason=item.get("reason") or "")
                elif action == "unschedule":
                    res = unschedule(brain, item_id, actor=who)
                elif action == "reject":
                    res = reject(brain, item_id, item.get("reason") or "", actor=who)
                elif action == "archive":
                    res = archive(brain, item_id, item.get("reason") or "", actor=who)
                elif action == "edit":
                    edits = item.get("edits") or {}
                    res = edit(brain, item_id, item.get("body"), title=edits.get("title"),
                               summary=edits.get("summary"), reason=item.get("reason") or "",
                               actor=who, minor=bool(item.get("minor")))
                elif action == "restore":
                    res = restore(brain, item_id, item.get("ref"),
                                  reason=item.get("reason") or "", actor=who)
                elif action == "unarchive":
                    res = unarchive(brain, item_id, reason=item.get("reason") or "", actor=who)
                elif action == "update":
                    res = update(brain, item_id, item.get("fields") or {},
                                 reason=item.get("reason") or "", actor=who)
                elif action == "verify":
                    res = verify(brain, item_id, actor=who, confidence=item.get("confidence"))
                elif action == "mark":
                    res = mark(brain, item_id, str(item.get("state") or ""),
                               reason=item.get("reason") or "", actor=who)
                else:
                    res = _result(f"Unknown action {action!r} for {item_id}.", {}, True)
                results.append({"id": item_id, "action": action, "ok": not res.is_error,
                                "message": res.text, "data": res.data})
                if not res.is_error and res.data.get("status") != "unchanged":
                    batch.decisions.append(_summary(action, item_id, proposal, res.data))
            deferred.message = label or checkpoints.describe(batch.decisions)
    ok = sum(1 for r in results if r["ok"])
    point = batch.checkpoint
    return _result(f"{ok} of {len(results)} decision(s) applied."
                   + (" Undo point saved." if point else ""),
                   {"results": results, "checkpoint": point,
                    "commit": (deferred.outcome or {}).get("commit")},
                   is_error=ok != len(results))


def _summary(action, item_id, proposal, data) -> dict:
    """One decision as an undo point lists it: what was decided, and what it was called."""
    done = {"approve": "approved", "reject": "rejected", "archive": "archived",
            "edit": "edited", "restore": "restored", "unarchive": "unarchived",
            "update": "updated", "verify": "verified", "mark": "marked",
            "unschedule": "unscheduled"}[action]
    if data.get("status") == "scheduled":
        done = "scheduled"
    out = {"action": done}
    if proposal is not None:
        target = proposal.target
        out.update(proposal=proposal.id, kind=proposal.kind,
                   title=str(target.get("title") or target.get("name") or proposal.summary))
        note = (data.get("pointer") if proposal.kind == "file.add"
                else data.get("id") if proposal.kind.startswith("note.") else None)
        if action == "approve" and note:
            out["note"] = note
    else:
        out.update(note=item_id, title=str(data.get("title") or item_id))
    if data.get("superseded"):
        out["superseded"] = list(data["superseded"])
    return out


def archive(brain, note_id, reason="", *, actor=None):
    """The owner retires a live note: it leaves every packet, stays on disk as history, and
    the journal records why."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to archive.", {"status": "missing"}, True)
    meta = dict(note.meta, status="archived", updated=util.today())
    brain.vault.write_note(note.path, meta, note.body)
    record = {"at": util.now_iso(), "action": "archived", "by": who, "note": note.id,
              "path": note.path, "reason": str(reason or "").strip(),
              "file_hash": brain.vault.file_hash(note.path)}
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions)],
                                f"Archived {note.id}" + (f": {reason}" if reason else ""))
    return _result(f"Archived {note.id}.", {"status": "archived", "id": note.id,
                                            "title": note.title,
                                            "commit": outcome.get("commit")})


def edit(brain, note_id, text, *, title=None, summary=None, reason="", actor=None,
         minor=False):
    """The owner rewrites a live note in place: same id, same file, new words. The journal
    keeps what it said before, and an undo point (when inside a batch) can put it back.

    A `minor` edit (a typo, a cleanup) is not new knowledge: it does not renew freshness. A
    new text for a baseline is a revision: it needs a `reason` (baseline.reason_problem),
    which the journal keeps with it."""
    from . import baseline
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to edit.", {"status": "missing"}, True)
    text = str(text or "").strip()
    if not text:
        return _result("An edit needs the note's new text.", {"status": "invalid"}, True)
    revision = None
    if not minor and util.canonical(text) != util.canonical(note.body):
        why = baseline.why(note, brain.state().config, baseline.uses(brain).get(note.id, 0))
        if why:
            problem = baseline.reason_problem(brain, note, reason)
            if problem:
                return _result(f"“{note.title}” is a baseline ({why}). {problem}",
                               {"status": "needs_reason", "note": note.id, "baseline": why},
                               True)
            revision = {"note": note.id, "why": why, "reason": " ".join(str(reason).split())}
    meta = dict(note.meta, updated=util.today())
    if not minor and util.canonical(text) != util.canonical(note.body):
        meta["revised"] = util.now_iso()
    if str(title or "").strip():
        meta["title"] = " ".join(str(title).split())
    if str(summary or "").strip():
        meta["summary"] = " ".join(str(summary).split())
        meta.pop("index_line", None)
    brain.vault.write_note(note.path, meta, text)
    record = {"at": util.now_iso(), "action": "edited", "by": who, "note": note.id,
              "path": note.path, "reason": str(reason or "").strip(), "previous": note.body,
              "minor": bool(minor), "hash": util.sha256(text.strip()),
              "previous_hash": note.body_hash, "file_hash": brain.vault.file_hash(note.path)}
    if revision:
        record["baseline_revised"] = revision
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions)],
                                f"Edited {note.id}" + (f": {reason}" if reason else ""))
    return _result(f"Edited {note.id}.", {"status": "edited", "id": note.id,
                                          "title": meta.get("title") or note.title,
                                          "commit": outcome.get("commit")})


RESTORED_FIELDS = ("title", "summary", "index_line", "kind", "load", "startup_text")


def restore(brain, note_id, ref, *, reason="", actor=None):
    """The owner puts an earlier version of a live entry back: what it said then (text,
    title, summary, kind, load) with today's place, owner and checks. The journal says which
    version, and inside a batch it is an undo point like any other decision."""
    from . import history
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to restore; bring it back first.",
                       {"status": "missing"}, True)
    old = history.version(brain, note.id, ref)
    if old is None:
        return _result(f"No version {ref!r} of {note.id}.", {"status": "missing"}, True)
    text = str(old.get("body") or "").strip()
    if not text:
        return _result(f"Version {ref} of {note.id} has no text to restore.",
                       {"status": "invalid"}, True)
    meta = dict(note.meta)
    for key in RESTORED_FIELDS:
        meta.pop(key, None)
        value = (old.get("meta") or {}).get(key)
        if value not in (None, ""):
            meta[key] = value
    same_text = util.canonical(text) == util.canonical(note.body)
    if same_text and all(meta.get(k) == note.meta.get(k) for k in RESTORED_FIELDS):
        return _result(f"{note.id} already says what version {ref} says.",
                       {"status": "unchanged", "id": note.id})
    meta["updated"] = util.today()
    if not same_text:
        meta["revised"] = util.now_iso()
    brain.vault.write_note(note.path, meta, text)
    when = str(old.get("at") or "")[:10]
    record = {"at": util.now_iso(), "action": "restored", "by": who, "note": note.id,
              "path": note.path, "from": str(old.get("commit") or old["ref"]),
              "from_at": old.get("at"), "reason": str(reason or "").strip(),
              "previous": note.body, "hash": util.sha256(text), "previous_hash": note.body_hash,
              "file_hash": brain.vault.file_hash(note.path)}
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions)],
                                f"Restored {note.id} to its version of {when}"
                                + (f": {reason}" if reason else ""))
    return _result(f"Restored {note.id} to its version of {when}.",
                   {"status": "restored", "id": note.id,
                    "title": meta.get("title") or note.title, "from": record["from"],
                    "commit": outcome.get("commit")})


def unarchive(brain, note_id, *, reason="", actor=None):
    """The owner brings an archived (or merged) entry back where it was filed. Whatever
    replaced it stays live, so the two may now repeat each other: the result says so."""
    from .model import LIVE
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    st = brain.state()
    note = st.index.note(note_id, include_archived=True)
    if note is None or note.live:
        return _result(f"No archived note {note_id!r} to bring back.", {"status": "missing"},
                       True)
    successor = str(note.meta.get("superseded_by") or "").strip()
    meta = dict(note.meta, status=LIVE, updated=util.today())
    meta.pop("superseded_by", None)
    brain.vault.write_note(note.path, meta, note.body)
    record = {"at": util.now_iso(), "action": "unarchived", "by": who, "note": note.id,
              "path": note.path, "reason": str(reason or "").strip(), "hash": note.body_hash,
              "file_hash": brain.vault.file_hash(note.path)}
    if successor:
        record["superseded_by"] = successor
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions)],
                                f"Brought back {note.id}" + (f": {reason}" if reason else ""))
    live_successor = st.index.note(successor) if successor else None
    return _result(
        f"Brought back {note.id}."
        + (f" {live_successor.id} replaced it and is still live; archive one of them if they "
           "say the same thing." if live_successor is not None else ""),
        {"status": "unarchived", "id": note.id, "title": note.title,
         "replaced_by": live_successor.id if live_successor is not None else None,
         "commit": outcome.get("commit")})


# What the owner sets on an entry directly: who answers for it, how often it is checked, how
# sensitive it is, and where it is filed; on a filed item's card, what kind of Library item it
# is, how often it is fetched again, where it came from, its title, the project it is for and,
# for a prompt, its tags and what it is used with. An empty value clears the field.
FIELDS = ("owner", "review_days", "review_by", "classification", "area", "topic", "aliases",
          "load", "applies_to", "triggers", "must_text", "critical", "baseline", "as_of",
          "valid_until", "library", "refresh", "origin", "tags", "prompt_skills",
          "prompt_agent", "prompt_docs", "prompt_reads", "title", "project_id", "said_by",
          "subtype", "objective", "goals")
CARD_FIELDS = ("library", "refresh", "origin", "tags", "prompt_skills", "prompt_agent",
               "prompt_docs", "prompt_reads", "title", "project_id")
# Card fields that hold a list, set as comma-separated words.
LIST_FIELDS = ("aliases", "tags", "prompt_skills", "prompt_docs", "prompt_reads", "goals")
# When a note reaches a model: in every session, whenever its domain comes up (a must-hold),
# when relevant, or only when asked for. Set together and checked by must_hold_fields.
MUST_FIELDS = ("load", "applies_to", "triggers", "must_text", "critical")
CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")


def update(brain, note_id, fields, *, reason="", actor=None):
    """The owner changes an entry's details (FIELDS) without touching what it says. Moving
    it (`area`, `topic`) moves its file, which keeps its dated name."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to update.", {"status": "missing"}, True)
    st = brain.state()
    config = st.config
    wanted = {str(k): ("" if v is None else str(v).strip()) for k, v in (fields or {}).items()}
    unknown = sorted(k for k in wanted if k not in FIELDS)
    problems = [f"{', '.join(unknown)} cannot be set this way"] if unknown else []
    if wanted.get("review_days") and not wanted["review_days"].isdigit():
        problems.append("review_days is a number of days")
    for name in ("review_by", "as_of", "valid_until"):
        if wanted.get(name) and util.parse_date(wanted[name]) is None:
            problems.append(f"{name} is a date (YYYY-MM-DD)")
    if wanted.get("classification") and wanted["classification"] not in CLASSIFICATIONS:
        problems.append(f"classification is one of {', '.join(CLASSIFICATIONS)}")
    if ("objective" in wanted or "goals" in wanted) and not st.config.is_focus(note):
        problems.append("only a project has an objective and the goals it serves")
    if wanted.get("objective") and statements.objective_problem(wanted["objective"]):
        problems.append(statements.objective_problem(wanted["objective"]))
    if "objective" in wanted and not str(reason or "").strip():
        # Like the rest of a project's baseline: a change says why, and makes an undo point.
        problems.append("a change to a project's objective needs a reason")
    if wanted.get("said_by") and wanted["said_by"] not in statements.SAID_BY:
        problems.append(f"said_by is one of {', '.join(statements.SAID_BY)}")
    if wanted.get("subtype") and wanted["subtype"] not in statements.RULE_SUBTYPES:
        problems.append(f"subtype is one of {', '.join(statements.RULE_SUBTYPES)}")
    if any(k in wanted for k in CARD_FIELDS) and str(note.meta.get("type")) != "file":
        problems.append("only a document's card goes in the Library")
    asset = str(note.meta.get("file") or "").startswith("assets/")
    if wanted.get("library") and wanted["library"] not in uploads.LIBRARY_KINDS:
        problems.append(f"library is one of {', '.join(uploads.LIBRARY_KINDS)}")
    elif wanted.get("library") and asset != (wanted["library"] == "asset"):
        problems.append("an asset's kind is asset, and a document's is guide, reference or "
                        "influence")
    elif wanted.get("library") and (wanted["library"] == "prompt") != (
            str(note.meta.get("library") or "") == "prompt"):
        # A prompt's card carries its words and is used only when named: it is filed as one.
        problems.append("a prompt is filed as a prompt; file the words again to change that")
    if "title" in wanted and not wanted["title"]:
        problems.append("a title cannot be empty")
    if wanted.get("project_id") and wanted["project_id"] not in st.index.focuses:
        problems.append(f"no project {wanted['project_id']!r}")
    if wanted.get("origin") and uploads.origin_kind(wanted["origin"]) not in uploads.ORIGINS:
        problems.append(f"origin is one of {', '.join(uploads.ORIGINS)}, optionally with "
                        "which one after a colon (capture:recording)")
    if wanted.get("refresh") and wanted["refresh"] not in uploads.LIBRARY_REFRESH:
        problems.append(f"refresh is one of {', '.join(uploads.LIBRARY_REFRESH)}")
    if wanted.get("owner") and not st.scopes.exists(wanted["owner"]):
        problems.append(f"owner {wanted['owner']!r} is not a scope declared in brain.json")
    area = wanted.get("area") or note.area
    topic = wanted.get("topic") or note.topic
    if "area" in wanted and area not in config.areas:
        problems.append(f"area must be one of {', '.join(config.area_order())}")
    if "topic" in wanted and not re.match(r"^[a-z0-9][a-z0-9-]*$", topic):
        problems.append("topic must be a lowercase slug, for example 'voice'")
    must: dict = {}
    if any(key in wanted for key in MUST_FIELDS):
        load = (wanted.get("load") or note.load).lower()
        if load not in LOADS:
            problems.append("load must be standing, domain, on-demand or manual")
        must = must_hold_fields(st, note, load, wanted.get("applies_to"),
                                wanted.get("triggers"), wanted.get("must_text"),
                                wanted.get("critical"), problems)
        if "load" in wanted:
            must["load"] = load
    if problems:
        return _result("Not updated: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    meta = dict(note.meta)
    for key, value in must.items():
        if key == "critical" and not value:
            meta.pop(key, None)
        else:
            meta[key] = value
    for key, value in wanted.items():
        if key in ("area", "topic") or key in MUST_FIELDS:
            continue
        if key == "baseline":
            # Marked a baseline by the owner: a change to it waits, with a reason.
            if fm.as_bool(value):
                meta[key] = True
            else:
                meta.pop(key, None)
            continue
        if key in LIST_FIELDS:
            # Comma separated: a project's other names (it is found by any of them), a
            # prompt's tags, what it was used with.
            names = list(dict.fromkeys(" ".join(a.split()) for a in value.split(",")
                                       if a.strip()))
            if names:
                meta[key] = names[:12 if key == "aliases" else 20]
            else:
                meta.pop(key, None)
            continue
        if value:
            meta[key] = value
        else:
            meta.pop(key, None)
    relpath = note.path
    if (area, topic) != (note.area, note.topic):
        area_key = "area" if ("area" in meta or config.uses_areas) else "layer"
        meta[area_key], meta["topic"] = area, topic
        relpath = brain.vault.note_path(meta, config.structure.get("scope_levels") or [],
                                        config.structure.get("partition_kinds") or [])
    if meta == note.meta:
        return _result(f"{note.id} already has those details.",
                       {"status": "unchanged", "id": note.id})
    meta["updated"] = util.today()
    brain.vault.write_note(relpath, meta, note.body)
    touched = [brain.vault.path(relpath)]
    if relpath != note.path:
        brain.vault.remove_file(note.path)
        touched.append(brain.vault.path(note.path))
    record = {"at": util.now_iso(), "action": "updated", "by": who, "note": note.id,
              "path": relpath, "fields": wanted,
              "was": {k: note.meta.get(k, "") for k in wanted if k not in ("area", "topic")},
              "reason": str(reason or "").strip(), "hash": note.body_hash,
              "file_hash": brain.vault.file_hash(relpath)}
    if relpath != note.path:
        record["moved_from"] = note.path
    decisions = brain.vault.append_decision(record)
    touched.append(brain.vault.path(decisions))
    changed = ", ".join(sorted(wanted))
    outcome = brain.after_write(touched, f"Updated {note.id}: {changed}")
    return _result(f"Updated {note.id} ({changed}).",
                   {"status": "updated", "id": note.id, "title": note.title, "path": relpath,
                    "commit": outcome.get("commit")})


def admitted(note, chain, partitions=()):
    return Scopes.admits(note.scope, note.partition, chain, partitions)


# ------------------------------------------------------------------ freshness (spec 05)

MARKS = ("stale", "disputed")


def _live_note(brain, note_id):
    note = brain.state().index.note(note_id)
    return note if note is not None and note.live else None


def verify(brain, note_id, *, actor=None, confidence=None):
    """The owner confirms a note is still true: verified today, no longer stale."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to verify.", {"status": "missing"}, True)
    if confidence is not None and confidence not in CONFIDENCE:
        return _result(f"Confidence is one of {', '.join(CONFIDENCE)}.", {"status": "invalid"},
                       True)
    meta = dict(note.meta)
    meta["verified"] = util.today()
    meta.pop("stale", None)
    if confidence:
        meta["confidence"] = confidence
    return _freshness_write(brain, note, meta, who,
                            {"action": "verified", "confidence": meta.get("confidence")},
                            f"Verified {note.id}")


def mark(brain, note_id, state, *, reason="", actor=None):
    """The owner marks a note stale or disputed. It stays in the brain, ranked lower and
    flagged in every packet, until someone verifies it again or it is superseded."""
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    if state not in MARKS:
        return _result(f"Mark a note {' or '.join(MARKS)}.", {"status": "invalid"}, True)
    if not str(reason or "").strip():
        return _result("Say why, so the next person knows what to check.",
                       {"status": "invalid"}, True)
    note = _live_note(brain, note_id)
    if note is None:
        return _result(f"No live note {note_id!r} to mark.", {"status": "missing"}, True)
    meta = dict(note.meta)
    if state == "stale":
        meta["stale"] = True
    else:
        meta["confidence"] = "disputed"
    return _freshness_write(brain, note, meta, who,
                            {"action": "marked", "state": state, "reason": str(reason).strip()},
                            f"Marked {note.id} {state}")


def _freshness_write(brain, note, meta, who, fields, message):
    brain.vault.write_note(note.path, meta, note.body)
    record = {"at": util.now_iso(), "by": who, "note": note.id, "path": note.path, **fields,
              "file_hash": brain.vault.file_hash(note.path)}
    decisions = brain.vault.append_decision(record)
    outcome = brain.after_write([brain.vault.path(note.path), brain.vault.path(decisions)],
                                message)
    return _result(f"{message}.", {"status": fields["action"], "id": note.id,
                                   "title": note.title, "verified": meta.get("verified"),
                                   "confidence": meta.get("confidence"),
                                   "stale": bool(meta.get("stale")),
                                   "commit": outcome.get("commit")})


# ------------------------------------------------------------------ policy
# How the brain is governed, set by its owner in brain.json: review cadences, what applies
# without review, the proposal limit per conversation, how long delivery detail is kept, and
# who answers for an entry that names nobody. One change is one undo point.

POLICY = {
    # key: (section, setting, kind)
    "review_days": ("governance", "review_days", "days_map"),
    "default_owner": ("governance", "default_owner", "scope"),
    "auto_apply_own_scope": ("governance", "auto_apply_own_scope", "bool"),
    "auto_apply_scopes": ("governance", "auto_apply_scopes", "patterns"),
    "max_proposals_per_session": ("governance", "max_proposals_per_session", "count"),
    "retention_days": ("sessions", "retention_days", "count"),
    "capture": ("governance", "capture", "capture"),
    "preset": ("governance", "preset", "preset"),
    # A day to think before a rule, a standing note or a must-hold changes (off by default).
    "revision_delay": ("governance", "revision_delay", "bool"),
    # The owner's own AI reads possible disagreements side by side (check 3), when one is
    # connected; on by default.
    "model_checks": ("governance", "model_checks", "bool"),
    # Once a week, the most used notes and the oldest baselines are read against what the
    # Brain holds (dissent.py); on by default.
    "cross_check": ("governance", "cross_check", "bool"),
    # The external challenger argues against a few beliefs each week; off until turned on.
    "challenger": ("governance", "challenger", "bool"),
}


def policies(brain) -> dict:
    """The policy as it stands, defaults filled in, with what each key may hold."""
    config = brain.state().config
    data = config.data
    return {
        "review_days": dict(data["governance"].get("review_days") or {}),
        "default_owner": config.default_owner,
        "auto_apply_own_scope": bool(data["governance"].get(
            "auto_apply_own_scope", PRESETS[preset_of(config)]["auto_apply_own_scope"])),
        "auto_apply_scopes": list(data["governance"].get("auto_apply_scopes") or []),
        "max_proposals_per_session": int(data["governance"].get("max_proposals_per_session")
                                         or DEFAULT_SESSION_BUDGET),
        "retention_days": retention_days(config),
        "approver": config.approver,
        "preset": preset_of(config),
        "presets": list(PRESETS),
        "areas": config.area_order(),
        "kinds": config.kind_order(),
        "scopes": sorted(brain.state().scopes.declared),
        "capture": capture_policy(config),
        "revision_delay": delays(config),
        "model_checks": bool(data["governance"].get("model_checks", True)),
        "cross_check": bool(data["governance"].get("cross_check", True)),
        "challenger": bool(data["governance"].get("challenger", False)),
        "capture_types": list(CAPTURE_TYPES),
        "capture_origins": list(CAPTURE_ORIGINS),
    }


def _policy_value(st, key, kind, value):
    """(clean value, problem or None) for one policy setting."""
    if kind == "bool":
        return bool(value), None
    if kind == "count":
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None, f"{key} is a whole number"
        return (number, None) if 1 <= number <= 3650 else (None, f"{key} is between 1 and 3650")
    if kind == "scope":
        text = str(value or "").strip()
        if text and not st.scopes.exists(text):
            return None, f"{key} {text!r} is not a scope declared in brain.json"
        return (text or None), None
    if kind == "patterns":
        items = value if isinstance(value, list) else [value]
        return [str(p).strip() for p in items if str(p or "").strip()], None
    if kind == "preset":
        text = str(value or "").strip().lower()
        if text not in PRESETS:
            return None, f"preset is one of {', '.join(PRESETS)}"
        return text, None
    if kind == "capture":
        # Only what differs from the preset is kept in brain.json.
        if not isinstance(value, dict):
            return None, "capture maps a type to {origin: apply or wait}"
        current = capture_policy(st.config)
        clean = {}
        for name, origins in value.items():
            if name not in CAPTURE_TYPES:
                return None, f"{name!r} is not a capture type ({', '.join(CAPTURE_TYPES)})"
            if not isinstance(origins, dict):
                return None, f"capture {name} maps an origin to apply or wait"
            for origin, setting in origins.items():
                if origin not in CAPTURE_ORIGINS:
                    return None, (f"{origin!r} is not an origin "
                                  f"({', '.join(CAPTURE_ORIGINS)})")
                if setting not in ("apply", "wait"):
                    return None, f"capture {name} {origin} is apply or wait"
                current[name][origin] = setting
        base = PRESETS[preset_of(st.config)]["capture"]
        for name, origins in current.items():
            for origin, setting in origins.items():
                if base[name][origin] != setting:
                    clean.setdefault(name, {})[origin] = setting
        return clean, None
    if not isinstance(value, dict):
        return None, f"{key} maps an area or kind to a number of days"
    known = set(st.config.areas) | set(st.config.kinds)
    clean = {}
    for name, days in value.items():
        if str(name) not in known:
            return None, f"{name!r} is neither an area nor a kind"
        if days in (None, "", 0, "0"):
            continue
        try:
            clean[str(name)] = int(days)
        except (TypeError, ValueError):
            return None, f"the cadence for {name} is a number of days"
        if not 1 <= clean[str(name)] <= 3650:
            return None, f"the cadence for {name} is between 1 and 3650 days"
    return clean, None


def set_policies(brain, changes, *, reason="", actor=None):
    """The owner changes the policy: brain.json is rewritten with the new settings, the
    journal records what they were, and the change is an undo point."""
    import copy
    import json

    from . import checkpoints
    who, refusal = _require_approver(brain, actor)
    if refusal:
        return refusal
    st = brain.state()
    unknown = sorted(k for k in (changes or {}) if k not in POLICY)
    problems = [f"{', '.join(unknown)} is not a policy setting"] if unknown else []
    clean = {}
    for key, value in (changes or {}).items():
        if key in POLICY:
            found, problem = _policy_value(st, key, POLICY[key][2], value)
            if problem:
                problems.append(problem)
            else:
                clean[key] = found
    if problems:
        return _result("Policy not changed: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    if "preset" in clean:
        # A preset is a fresh start: what was changed on top of the old one goes, and the
        # preset says whether the owner's own preferences apply at once, unless this change
        # says so itself.
        if "capture" not in clean:
            clean["capture"] = {}
        clean.setdefault("auto_apply_own_scope",
                         PRESETS[clean["preset"]]["auto_apply_own_scope"])
    path = brain.vault.path("brain.json")
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)
    before = policies(brain)
    was = {k: before.get(k) for k in clean}
    changed = copy.deepcopy(raw)
    for key, value in clean.items():
        section, setting, _kind = POLICY[key]
        part = changed.setdefault(section, {})
        if value is None or value == {} or value == []:
            part.pop(setting, None)
        else:
            part[setting] = value
    if changed == raw:
        return _result("The policy already says that.", {"status": "unchanged"})
    label = "Policy: " + ", ".join(sorted(clean))
    with checkpoints.batch(brain, actor=who, label=label) as batch:
        brain.vault.touch(path)
        util.atomic_write(path, json.dumps(changed, indent=2, ensure_ascii=False) + "\n")
        record = {"at": util.now_iso(), "action": "policy", "by": who, "changes": clean,
                  "was": was, "reason": str(reason or "").strip()}
        decisions = brain.vault.append_decision(record)
        batch.decisions.append({"action": "updated", "title": label})
        outcome = brain.after_write([path, brain.vault.path(decisions)],
                                    label + (f": {reason}" if reason else ""))
    return _result("Policy updated.", {"status": "updated", "policy": policies(brain),
                                       "checkpoint": batch.checkpoint,
                                       "commit": outcome.get("commit")})
