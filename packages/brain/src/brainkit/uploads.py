"""Uploads: skills, documents and assets coming into the brain.

KINDS
    skill.create   a new procedure: SKILL.md (front matter and body) plus its files
    skill.update   a change to an existing skill: new SKILL.md text and fields, new or changed
                   files; files it does not mention stay as they are
    file.add       a document, filed under references/ as Markdown that keeps its shape (the
                   original bytes kept in the runtime library), or an asset, filed under assets/
                   byte for byte. Each gets a card: a note naming the file (`file`), what it
                   covers and its sections, which copy it is (`version`, `file_status`,
                   `dated`) and, in a project, the project's folder. With `replaces`, or a file
                   named like one already in the same project, a new version: its text replaces
                   the old one in place (what loads it by path gets the new text), its card says
                   which version it is, and git keeps every earlier one

STAGING. What a proposal would add waits in `vault/.brain/staging/<proposal id>/` until it is
decided, so nothing undecided enters knowledge/, skills/, references/, assets/ or git history.
Approval moves the files into place and commits them; rejection deletes the staging folder.

FILES APPLY BY POLICY. A document or asset from the owner, or from the owner's AI in a
conversation, or from a folder the brain sweeps, is filed at once when the capture policy
says so (governance.captures_apply; by default it does), as one undo point. Anyone else's
file, and skills always, wait for review. A filed document is information: packets quote it
as source material, never as instructions.

GATES, before anything is staged: relative paths only (no `..`, no drive letters, no absolute
paths), a name deny-list (keys, credentials, environment files, private folders), a type
allowlist, size ceilings per file and per proposal, content hashes against what is already
filed or waiting, and the sensitivity-label check for documents.
"""
from __future__ import annotations

import base64
import binascii
import fnmatch
import hashlib
import json
import os
import re
import shutil

from . import frontmatter as fm
from . import util

SKILL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
CATEGORY = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
DOC_EXT = (".md", ".txt", ".html", ".htm", ".docx", ".pptx", ".pdf", ".vtt", ".srt")
ASSET_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".ttf", ".otf", ".woff",
             ".woff2", ".csv", ".json", ".xlsx", ".mp3", ".wav", ".m4a", ".mp4", ".mov", ".webm")
CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".ps1", ".css", ".yaml", ".yml",
            ".toml", ".xml", ".dotx", ".potx", ".xltx")
SKILL_FILE_EXT = DOC_EXT + ASSET_EXT + CODE_EXT
DENY = (".env", ".env.*", "*.env", "*.pem", "*.key", "*.pfx", "*.p12", "*.crt", "*.cer",
        "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "*.kdbx", "credentials*", "*secret*",
        ".npmrc", ".pypirc", ".netrc", "*.sqlite", "*.db", ".git", ".ssh", ".aws", ".gnupg",
        "private", ".brain")
MAX_FILE = 10 * 1024 * 1024
MAX_PROPOSAL = 25 * 1024 * 1024
MAX_FILES = 50
SKILL_KEY_ORDER = ("name", "description", "index_line", "when_to_use", "scope", "invocation",
                   "triggers", "aliases", "cue_terms", "artifacts", "loads", "depends_on",
                   "quality_gates")
SKILL_LIST_FIELDS = ("triggers", "aliases", "cue_terms", "artifacts", "loads", "depends_on",
                     "quality_gates")
UPLOAD_KINDS = ("skill.create", "skill.update", "file.add")
# The Library: an item kept whole can say what kind of item it is (a guide to follow, a
# reference to read whole, an influence whose taste to borrow, a prompt the person keeps word
# for word, or an asset: an image, a font, a sheet, kept byte for byte), where it was fetched
# from, when, and how often to fetch it again. These live on the item's card. Only an asset is
# an asset; a document is any of the others.
#
# A PROMPT is the person's own words for later: filed under references/prompts/, its card
# carries the text word for word, so search_notes finds it and get_note returns it, and it is
# loaded `manual`: never routed into a brief or quoted as a file's section unless a request
# names it. Its tags, the skills, agent, docs and Library items it was used with, and the files
# that came with it (each filed with `attached_to` naming it) live on cards too.
LIBRARY_KINDS = ("guide", "reference", "influence", "prompt", "asset")
DOCUMENT_KINDS = ("guide", "reference", "influence", "prompt")
LIBRARY_REFRESH = ("never", "weekly", "monthly")
LIBRARY_LISTS = ("source_paths", "tags", "prompt_skills", "prompt_docs", "prompt_reads")
LIBRARY_KEYS = ("library", "source_url", "source_repo", "source_paths", "fetched_at", "refresh",
                "tags", "prompt_skills", "prompt_agent", "prompt_docs", "prompt_reads",
                "attached_to")
PROMPT_FOLDER = "references/prompts/"
MAX_PROMPT = 20000  # characters in one prompt
# Where a filed item came from, on its card as `origin`, `<kind>` or `<kind>:<which one>` like a
# note's: a capture (capture:recording, capture:transcript, capture:upload, capture:export),
# the Library, a project, a skill, a run's output (run:<id>), Moving in, a person in the app, an
# AI in a conversation, or a swept folder. Items filed before origins were kept have none: the
# app infers one where it can and lets the owner set it.
ORIGINS = ("capture", "library", "project", "skill", "run", "movein", "upload", "chat", "folder")
CHANNEL_ORIGINS = {"app": "upload", "chat": "chat", "folder": "folder"}


def origin_kind(value) -> str:
    return str(value or "").partition(":")[0].strip().lower()


def origin_meta(came_from, *, channel=None, library=None, project=None) -> dict:
    """The card's `origin` for a filing: what the caller says (`capture:recording`, `run:<id>`,
    `library`), else the Library or the project it goes to, else the channel it came through
    (a person in the app, an AI in a conversation, a swept folder)."""
    text = " ".join(str(came_from or "").split())[:160]
    kind = origin_kind(text)
    if kind and kind not in ORIGINS:
        raise Refused(f"origin is one of {', '.join(ORIGINS)}")
    if not kind:
        text = ("library" if library else "project" if project else
                CHANNEL_ORIGINS.get(str(channel or "chat"), "chat"))
    return {"origin": text}


class Refused(Exception):
    """An upload that fails a gate. Nothing has been staged when this is raised."""


def library_meta(fields) -> dict:
    """The Library's fields for a document's card, checked; empty ones are left out."""
    out: dict = {}
    for key, value in (fields or {}).items():
        if key not in LIBRARY_KEYS:
            raise Refused(f"{key} is not a Library field")
        if value in (None, "", [], ()):
            continue
        if key in LIBRARY_LISTS:
            items = value.split(",") if isinstance(value, str) else value
            kept = list(dict.fromkeys(" ".join(str(p).split())[:300] for p in items
                                      if str(p).strip()))
            if kept:
                out[key] = kept[:20]
            continue
        text = str(value).strip()
        if key == "library" and text not in LIBRARY_KINDS:
            raise Refused("a Library item is a guide, a reference, an influence, a prompt or "
                          "an asset")
        if key == "attached_to":
            text = clean_relpath(text)
        if key == "refresh" and text not in LIBRARY_REFRESH:
            raise Refused("refresh is never, weekly or monthly")
        if key in ("source_url", "source_repo") and not text.lower().startswith("https://"):
            raise Refused(f"{key} must be an https:// address")
        out[key] = text
    return out


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


# ------------------------------------------------------------------ gates

def _denied(parts) -> str | None:
    for part in parts:
        for pattern in DENY:
            if fnmatch.fnmatch(part.lower(), pattern):
                return part
    return None


def clean_relpath(path: str) -> str:
    """A safe path inside a skill folder, or Refused."""
    raw = str(path or "").replace("\\", "/").strip()
    if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise Refused(f"{path!r}: use a relative path inside the skill folder")
    parts = [p for p in raw.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts) or not parts or len(parts) > 6:
        raise Refused(f"{path!r}: a path may not leave the skill folder")
    denied = _denied(parts)
    if denied:
        raise Refused(f"{path!r}: {denied!r} looks like a secret or private file")
    return "/".join(parts)


def read_source(source_path: str) -> tuple[str, bytes]:
    """(file name, bytes) of a local file the proposer pointed at, after the gates."""
    path = os.path.abspath(os.path.expanduser(str(source_path or "")))
    parts = re.split(r"[\\/]", path)
    denied = _denied(parts[1:])
    if denied:
        raise Refused(f"{source_path}: {denied!r} looks like a secret or private file")
    if not os.path.isfile(path):
        raise Refused(f"{source_path}: no such file")
    if os.path.getsize(path) > MAX_FILE:
        raise Refused(f"{source_path}: over the {MAX_FILE // (1024 * 1024)} MB file limit")
    with open(path, "rb") as handle:
        return os.path.basename(path), handle.read()


def payload_bytes(entry: dict) -> tuple[str | None, bytes]:
    """(file name if known, bytes) from `source_path`, `content_base64` or `content`."""
    if entry.get("source_path"):
        return read_source(entry["source_path"])
    if entry.get("content_base64") is not None:
        try:
            data = base64.b64decode(str(entry["content_base64"]), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise Refused(f"content_base64 is not valid base64: {exc}") from exc
        return None, data
    if entry.get("content") is not None:
        return None, str(entry["content"]).encode("utf-8")
    raise Refused("give each file `content`, `content_base64` or `source_path`")


def _check_size(data: bytes, label: str) -> None:
    if len(data) > MAX_FILE:
        raise Refused(f"{label}: over the {MAX_FILE // (1024 * 1024)} MB file limit")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------------------ staging

def staging_dir(brain, proposal_id: str) -> str:
    return os.path.join(brain.vault.runtime_dir, "staging", proposal_id)


def _stage(brain, proposal_id: str, files: dict, manifest: dict) -> None:
    root = staging_dir(brain, proposal_id)
    if os.path.isdir(root):
        shutil.rmtree(root)
    os.makedirs(root, exist_ok=True)
    for relpath, data in files.items():
        target = os.path.join(root, *relpath.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(data)
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=1)


def manifest(brain, proposal_id: str) -> dict:
    path = os.path.join(staging_dir(brain, proposal_id), "manifest.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def discard(brain, proposal) -> None:
    root = staging_dir(brain, proposal.id)
    if os.path.isdir(root):
        brain.vault.touch(root)
        shutil.rmtree(root, ignore_errors=True)


def _read_staged(brain, proposal_id: str, relpath: str) -> bytes:
    with open(os.path.join(staging_dir(brain, proposal_id), *relpath.split("/")), "rb") as h:
        return h.read()


def _pending(brain, kind=None):
    for proposal in brain.state().snapshot.proposals.values():
        if kind is None or proposal.kind in (kind if isinstance(kind, tuple) else (kind,)):
            yield proposal


# ------------------------------------------------------------------ skills

def _categories(st) -> set[str]:
    return set(st.config.categories) | {s.category for s in st.index.skills.values() if s.category}


def _find_skill(st, name):
    wanted = str(name or "").strip().lstrip("/")
    return st.index.skills.get(wanted) or next(
        (s for s in st.index.skills.values()
         if wanted.lower() in [a.lower() for a in [s.name] + s.aliases]), None)


def propose_skill(brain, *, name=None, description=None, body=None, category=None,
                  when_to_use=None, triggers=None, aliases=None, cue_terms=None, artifacts=None,
                  loads=None, depends_on=None, invocation=None, files=None, scope=None, target=None,
                  principal=None, evidence="", source="", reason="", session_id=None,
                  force_pending=False, **_ignored):
    """Propose a new skill, or a change to one (`target`), with its files. Waits for review
    unless it lands in the proposer's own scope and the brain's policy applies those at once
    (never with `force_pending`: what an AI drafted in the app always waits)."""
    from . import governance
    st = brain.state()
    who = brain.principal(principal)
    caller = brain.caller(who, st=st)
    if not isinstance(caller, tuple):
        return caller
    chain, _ = caller
    refusal = governance.check_budget(brain, session_id)
    if refusal:
        return refusal
    existing = None
    if target:
        existing = _find_skill(st, target)
        if existing is None:
            return _result(f"No skill {target!r} to change.", {"status": "invalid"}, True)
        kind = "skill.update"
        meta = {k: v for k, v in existing.meta.items() if k in SKILL_KEY_ORDER}
        name, category = existing.name, existing.category
        scope = scope or existing.scope
        body = body if body is not None else existing.body
    else:
        kind = "skill.create"
        meta = {}
        name = str(name or "").strip()
        category = str(category or "").strip().lower()
        if not SKILL_NAME.match(name):
            return _result("Skill refused: name must be 2 to 64 letters, digits, - or _.",
                           {"status": "invalid"}, True)
        if _find_skill(st, name) is not None:
            return _result(f"A skill named {name!r} already exists; propose a change with "
                           f"target={name!r}.", {"status": "exists", "name": name}, True)
        if not CATEGORY.match(category):
            return _result("Skill refused: category must be a lowercase slug, for example "
                           f"one of {', '.join(sorted(_categories(st))) or 'ops'}.",
                           {"status": "invalid"}, True)
        if not str(description or "").strip() or not str(body or "").strip():
            return _result("Skill refused: a new skill needs a description and a body.",
                           {"status": "invalid"}, True)
    for pending in _pending(brain, ("skill.create", "skill.update")):
        if str(pending.target.get("name")) == name:
            return _result(f"A proposal for skill {name} is already waiting ({pending.id}); "
                           "decide it first.", {"status": "duplicate",
                                                "proposal_id": pending.id, "name": name})
    scope = str(scope or "company").strip()
    if not st.scopes.exists(scope):
        return _result(f"Skill refused: scope {scope!r} is not declared.", {"status": "invalid"},
                       True)
    try:
        staged, listing = {}, []
        total = 0
        for entry in list(files or [])[:MAX_FILES + 1]:
            relpath = clean_relpath(entry.get("path") or entry.get("name")
                                    or os.path.basename(str(entry.get("source_path") or "")))
            if relpath.lower() == "skill.md":
                raise Refused("SKILL.md is written from the proposal; pass its text as `body`")
            if not relpath.lower().endswith(SKILL_FILE_EXT):
                raise Refused(f"{relpath}: this file type is not accepted in a skill")
            _name, data = payload_bytes(entry)
            _check_size(data, relpath)
            total += len(data)
            staged[f"files/{relpath}"] = data
            listing.append({"path": relpath, "size": len(data), "sha256": sha(data)})
        if len(listing) > MAX_FILES:
            raise Refused(f"at most {MAX_FILES} files per skill proposal")
        if total > MAX_PROPOSAL:
            raise Refused(f"files total over the {MAX_PROPOSAL // (1024 * 1024)} MB limit")
    except Refused as exc:
        return _result(f"Skill refused: {exc}.", {"status": "refused"}, True)

    fields = {"description": description, "when_to_use": when_to_use, "invocation": invocation}
    for key, value in fields.items():
        if value not in (None, ""):
            meta[key] = str(value).strip()
    for key, value in (("triggers", triggers), ("aliases", aliases), ("cue_terms", cue_terms),
                       ("artifacts", artifacts), ("loads", loads), ("depends_on", depends_on)):
        if value is not None:
            meta[key] = [str(v).strip() for v in (value if isinstance(value, list) else [value])
                         if str(v).strip()]
    meta.update({"name": name, "scope": scope, "category": category})
    body = str(body or "").strip() + "\n"
    proposal_id = f"skill-{name.lower()}-{util.short_hash(body + util.now_iso(), 4)}"
    header = {"kind": kind, "status": "pending", "created": util.now_iso(), "proposer": who,
              "reason": reason or ("change to an existing skill" if existing else "new skill"),
              "session": session_id or "",
              "files": [f"{f['path']} ({f['size']:,} bytes)" for f in listing]}
    if existing is not None:
        header["base_hash"] = existing.body_hash
    target_meta = dict(meta, source=source or f"proposed by {who}", evidence=evidence or "")
    _stage(brain, proposal_id, staged, {"kind": kind, "files": listing})
    if not force_pending and governance.auto_applies(st.config, who, scope):
        proposal = _as_proposal(proposal_id, kind, scope, header, target_meta, body)
        return apply(brain, proposal, actor=who, auto=True)
    relpath = brain.vault.write_proposal(proposal_id, header, target_meta, body)
    outcome = brain.after_write([brain.vault.path(relpath)],
                                f"Propose {kind} {name} ({len(listing)} file(s))")
    verb = "a change to skill" if existing else "new skill"
    return _result(
        f"Proposed {verb} {name} ({category}, {len(listing)} file(s)) for review by "
        f"{st.config.governance.get('approver') or st.config.owner}. It is not live until "
        "approved.",
        {"status": "pending", "proposal_id": proposal_id, "kind": kind, "name": name,
         "category": category, "files": listing, "path": relpath,
         "commit": outcome.get("commit")})


def _as_proposal(proposal_id, kind, scope, header, target, body):
    from .model import Proposal
    return Proposal(id=proposal_id, kind=kind, scope=scope, meta=dict(header, id=proposal_id),
                    target=dict(target), body=body, path="")


# ------------------------------------------------------------------ files

VERSION_MARK = re.compile(
    r"\bcopy\s+of\b|\b(?:v|ver|version|rev|revision)[\s._-]*\d+(?:[._]\d+)*\b"
    r"|\b(?:final|draft|copy|latest|revised|updated)\b"
    r"|\b\d{4}[-_. ]?\d{2}[-_. ]?\d{2}\b|\(\d+\)", re.IGNORECASE)
VERSION_NUMBER = re.compile(r"\b(?:v|ver|version|rev|revision)[\s._-]*(\d+)", re.IGNORECASE)
# What a version mark leaves behind: "Planning call (2026-03-02)" is not "Planning call ( )".
EMPTY_BRACKETS = re.compile(r"[(\[{]\s*[)\]}]")


def document_stem(name) -> str:
    """A file's name without what changes from copy to copy: "Campaign proposal v3 FINAL
    (2).docx" and "campaign-proposal_v4.docx" are both "campaign proposal"."""
    stem = os.path.splitext(os.path.basename(str(name or "")))[0]
    stem = VERSION_MARK.sub(" ", stem.replace("_", " ").replace("-", " "))
    return " ".join(re.findall(r"[a-z0-9]+", stem.lower()))


def version_in(name) -> int | None:
    """The version a file name states ("v3", "version 2"), if it states one."""
    found = VERSION_NUMBER.search(os.path.basename(str(name or "")))
    return int(found.group(1)) if found else None


def title_from_name(name) -> str:
    """A readable title from a file name, without its version marks."""
    stem = os.path.splitext(os.path.basename(str(name or "")))[0]
    words = EMPTY_BRACKETS.sub(" ", VERSION_MARK.sub(
        " ", stem.replace("_", " ").replace("-", " "))).split()
    title = " ".join(words) or stem.replace("_", " ").replace("-", " ").strip()
    return title[:1].upper() + title[1:]


def _same_document(st, project, filename) -> str | None:
    """The document filed in this project that `filename` is another copy of."""
    stem = document_stem(filename)
    if not stem:
        return None
    for path, card in st.index.project_files(project):
        known = str(card.meta.get("filename") or "")
        if document_stem(known or card.title) == stem:
            return path
    return None


def _card_body(title, path, about, outline) -> str:
    text = (f"Pointer: {title} is filed whole at {path}. Read it before relying on its "
            f"detail. It covers: {util.excerpt(about, 220)}")
    if outline:
        text += " Sections: " + "; ".join(outline) + "."
    return text


def _as_int(value) -> int | None:
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def add_file(brain, *, source_path=None, content=None, content_base64=None, filename=None,
             title=None, description="", purpose=None, topic=None, scope=None, principal=None,
             evidence="", source="", reason="", session_id=None, replaces=None, project=None,
             status=None, version=None, dated=None, origin=None, wait=False, library=None,
             came_from=None, **_ignored):
    """File a document (a reference) or an asset with its card, or a new version of one
    already filed: `replaces` names it (references/brand-voice.md), or, in a project, a file
    named like one already there is its new version. `library` puts the Library's fields
    on its card (LIBRARY_KEYS: its kind, source, when it was fetched, its refresh); an asset's
    only kind is `asset`. `came_from` says where it came from (ORIGINS, optionally with which
    one: `capture:recording`, `run:<id>`); the card keeps it as `origin`.

    `project` files it in a project's folder (a Focus, by id or name); `status` (draft,
    sent, final, ...), `version` and `dated` say which copy this is. `origin` is where it
    came from (app, chat or folder): the capture policy decides whether it is filed at once,
    as one undo point, or waits for review; `wait` makes it wait whatever the policy says (a
    bulk import the owner did not pick file by file). Returns what happened, or a duplicate
    when the same bytes are already filed or waiting."""
    from . import governance, importers
    from . import focus as focus_mod
    from . import sections as sections_mod
    st = brain.state()
    who = brain.principal(principal)
    caller = brain.caller(who, st=st)
    if not isinstance(caller, tuple):
        return caller
    chain, partitions = caller
    refusal = governance.check_budget(brain, session_id)
    if refusal:
        return refusal
    home = None
    if project:
        home, missing = focus_mod.resolve(brain, project, who)
        if missing is not None:
            return _result(f"File refused: {missing.text}", {"status": "invalid"}, True)
    try:
        known_name, data = payload_bytes({"source_path": source_path, "content": content,
                                          "content_base64": content_base64})
        filename = os.path.basename(str(filename or known_name or "").replace("\\", "/"))
        if not filename and title:
            filename = util.slugify(title) + ".md"
        if not filename:
            raise Refused("give the file a `filename`")
        denied = _denied([filename])
        if denied:
            raise Refused(f"{filename}: looks like a secret or private file")
        _check_size(data, filename)
        ext = os.path.splitext(filename)[1].lower()
        wanted = str(purpose or "").strip().lower() or None
        if wanted not in (None, "reference", "asset"):
            raise Refused("purpose must be reference or asset")
        if wanted == "reference" and ext not in DOC_EXT:
            raise Refused(f"{filename}: a reference must be one of {' '.join(DOC_EXT)}")
        if ext not in DOC_EXT + ASSET_EXT:
            raise Refused(f"{filename}: unsupported type {ext or '(none)'}")
        purpose = wanted or ("reference" if ext in DOC_EXT else "asset")
        extra = library_meta(library)
        kind = extra.get("library")
        if purpose == "asset" and kind not in (None, "asset"):
            raise Refused(f"{filename}: an asset is kept byte for byte, so its kind is asset; "
                          "only a document kept whole is a guide, a reference or an influence")
        if purpose == "reference" and kind == "asset":
            raise Refused(f"{filename}: a document kept whole is a guide, a reference or an "
                          "influence, not an asset")
        if kind == "prompt" and ext not in (".md", ".txt"):
            raise Refused(f"{filename}: a prompt is kept as text (.md or .txt)")
        if kind == "prompt" and len(data) > MAX_PROMPT * 4:
            raise Refused(f"keep a prompt under {MAX_PROMPT:,} characters")
        attached = extra.get("attached_to")
        if attached and attached not in st.index.cards:
            raise Refused(f"attach_to: {attached} is not a document the brain holds")
        came = origin_meta(came_from, channel=origin, library=bool(extra), project=project)
        if not replaces and home is not None and purpose == "reference":
            replaces = _same_document(st, home, filename)
        replacing = _replaceable(brain, replaces, purpose) if replaces else None
    except Refused as exc:
        return _result(f"File refused: {exc}.", {"status": "refused"}, True)

    digest = sha(data)
    for pending in _pending(brain, "file.add"):
        if pending.meta.get("sha256") == digest:
            return _result(f"The same file is already waiting for review ({pending.id}).",
                           {"status": "duplicate", "proposal_id": pending.id})
        if replacing and pending.meta.get("replaces") == replacing:
            return _result(f"A new version of {replacing} is already waiting ({pending.id}); "
                           "decide it first.", {"status": "duplicate",
                                                "proposal_id": pending.id})
    filed = _filed_copy(brain, digest)
    if filed:
        holder = next(((path, card) for path, card in sorted(st.index.cards.items())
                       if f"sha256 {digest}" in str(card.meta.get("evidence") or "")), None)
        if holder is not None:
            return _result(f"This exact file is already in the brain as {holder[1].title} "
                           f"({holder[0]}).", {"status": "duplicate", "path": holder[0],
                                               "id": holder[1].id})
        return _result(f"This exact file was filed before ({filed}); nothing changed.",
                       {"status": "duplicate", "path": filed})

    text = ""
    if purpose == "reference":
        probe = os.path.join(brain.vault.runtime_dir, "staging", f".probe-{digest[:12]}{ext}")
        os.makedirs(os.path.dirname(probe), exist_ok=True)
        try:
            with open(probe, "wb") as handle:
                handle.write(data)
            text = importers.to_markdown(probe).strip()
        except Exception as exc:
            return _result(f"File refused: could not read {filename}: {exc}.",
                           {"status": "unreadable"}, True)
        finally:
            if os.path.exists(probe):
                os.remove(probe)
        if not text:
            return _result(f"File refused: {filename} has no readable text.",
                           {"status": "unreadable"}, True)
    sample = (text or f"{title or ''} {description or ''}").lower()
    if any(label in sample for label in importers.SENSITIVE):
        return _result("File refused: it carries a sensitivity label.", {"status": "sensitive"},
                       True)

    title = str(title or "").strip() or title_from_name(filename)
    slug = util.slugify(title, 60) or digest[:12]
    if home is not None:
        area, topic_name = home.note.area, home.note.topic
    elif topic and "/" in str(topic):
        area, topic_name = str(topic).split("/", 1)
    else:
        area, topic_name = governance.guess_placement(
            brain, f"{title} {description} {text[:2000]}", chain, partitions)
    prompt = extra.get("library") == "prompt" or (card_kind(st, replacing) == "prompt")
    # A prompt is kept as the person wrote it, not as the reader converted it.
    verbatim = (data.decode("utf-8", errors="replace").replace("\r\n", "\n").strip()
                if prompt else text)
    if replacing:
        target_path = replacing
    elif prompt:
        target_path = _free_path(brain, f"{PROMPT_FOLDER}{slug}", ".md")
    elif purpose == "reference":
        folder = f"references/projects/{topic_name}/" if home is not None else "references/"
        target_path = _free_path(brain, f"{folder}{slug}", ".md")
    else:
        target_path = _free_path(brain, f"assets/{area}/{slug}", ext)
    size_label = f"{len(data):,} bytes"
    outline = sections_mod.outline(text) if text else []
    about = (str(description or "").strip() or (sections_mod.opening(text) if text else "")
             or title)
    dated = str(dated or "").strip()[:10] or util.today()
    status = str(status or "").strip().lower() or None
    stated = _as_int(version) or version_in(filename)
    # A new version replaces the text in place and brings its card up to date: which copy
    # it is, what it covers now. What loads the file by its path gets the new text.
    card = st.index.cards.get(replacing) if replacing else None
    keep_pointer = card.id if card is not None else (
        _pointer_to(st, replacing) if replacing else None)
    card_update = None
    if card is not None:
        previous = _as_int(card.meta.get("version"))
        meta = {k: v for k, v in card.meta.items() if k not in governance.RESERVED}
        meta.update(filename=filename, dated=dated, evidence=f"sha256 {digest}",
                    summary=util.excerpt(about, 140) if (description or text) else
                    card.meta.get("summary"))
        number = stated or (previous + 1 if previous else None)
        if number:
            meta["version"] = number
        if status:
            meta["file_status"] = status
        else:
            meta.pop("file_status", None)
        meta.setdefault("file", replacing)
        meta.setdefault("type", "file")
        meta.update(extra)
        for key, value in came.items():  # a new version keeps where the item came from
            meta.setdefault(key, value)
        card_update = {"id": card.id, "meta": meta,
                       "body": (prompt_body(card.title, replacing, verbatim) if prompt
                                else _card_body(card.title, replacing, about, outline)
                                if purpose == "reference" else card.body)}
    if replacing:
        pointer = (f"New version of {replacing} ({size_label}). It covers: "
                   f"{util.excerpt(about, 220)}"
                   + (f" Its card {keep_pointer} says which version it is." if card_update
                      else f" Pointer note {keep_pointer} stays as it is." if keep_pointer
                      else ""))
    elif prompt:
        pointer = prompt_body(title, target_path, verbatim)
    elif purpose == "reference":
        pointer = _card_body(title, target_path, about, outline)
    else:
        pointer = f"Asset: {title} ({filename}, {size_label}) is at {target_path}." + (
            f" {about}" if about and about != title else "")
    # A prompt is the person's own: kept in their own scope, and opened only when named.
    default_scope = chain[-1] if prompt else home.note.scope if home is not None else (
        chain[-2] if len(chain) > 1 else chain[0])
    scope = str(scope or default_scope).strip()
    if not st.scopes.exists(scope):
        return _result(f"File refused: scope {scope!r} is not declared.", {"status": "invalid"},
                       True)
    area_key = "area" if st.config.uses_areas else "layer"
    note_meta = {
        "id": governance.unique_id(st, governance.slug_from(title)), "title": title,
        "summary": util.excerpt(about, 140), area_key: area, "topic": topic_name,
        "kind": "fact", "type": "file", "scope": scope,
        "load": "manual" if prompt else "on-demand",
        "added": util.today(), "file": target_path, "filename": filename, "dated": dated,
        "source": source or f"{purpose} {filename} added by {who}",
        "evidence": evidence or f"sha256 {digest}", "classification": "internal",
        "supersedes": "none"}
    if home is not None:
        note_meta["project_id"] = home.id
    note_meta.update(extra)
    note_meta.update(came)
    if stated or purpose == "reference":
        note_meta["version"] = stated or 1
    if status:
        note_meta["file_status"] = status
    if not st.config.uses_areas:
        if not prompt:  # a prompt is found by its name, in any layout
            note_meta.pop("title")
        note_meta.pop("summary")
        note_meta.pop("kind")
    proposal_id = f"file-{slug[:40]}-{digest[:6]}"
    header = {"kind": "file.add", "status": "pending", "created": util.now_iso(),
              "proposer": who, "reason": reason or (f"new version of {replacing}" if replacing
                                                    else f"{purpose} to file"),
              "session": session_id or "", "purpose": purpose, "filename": filename,
              "size": len(data), "sha256": digest, "target": target_path,
              "origin": origin or "chat", "files": [f"{target_path} ({size_label})"]}
    base = None
    if replacing:
        with open(brain.vault.path(*replacing.split("/")), "rb") as handle:
            base = sha(handle.read())
        header.update(replaces=replacing, base_sha256=base, keep_pointer=keep_pointer or "")
    staged = {f"original{ext}": data}
    if text:
        staged["text.md"] = text.encode("utf-8")
    _stage(brain, proposal_id, staged, {
        "kind": "file.add", "purpose": purpose, "filename": filename, "sha256": digest,
        "size": len(data), "target": target_path, "original": f"original{ext}",
        "text": "text.md" if text else None, "title": title,
        "replaces": replacing, "base_sha256": base, "keep_pointer": keep_pointer,
        "card": card_update,
        "files": [{"path": target_path, "size": len(data), "sha256": digest}]})
    named = (card.title if card is not None and card.meta.get("title") else title)
    if not wait and governance.captures_apply(brain, who, "file", origin):
        return _file_now(brain, proposal_id, header, note_meta, pointer, who=who,
                         label=(f"New version of {named}" if replacing else f"Filed {named}"),
                         title=named, origin=origin, session_id=session_id, home=home)
    relpath = brain.vault.write_proposal(proposal_id, header, note_meta, pointer)
    outcome = brain.after_write([brain.vault.path(relpath)],
                                f"Propose {purpose} {filename} for {target_path}")
    approver = st.config.governance.get("approver") or st.config.owner
    if replacing:
        kept = f"; its pointer note {keep_pointer} stays" if keep_pointer else ""
        return _result(
            f"Proposed a new version of {replacing} ({filename}, {size_label}){kept}. It "
            f"waits for review by {approver}.",
            {"status": "pending", "proposal_id": proposal_id, "purpose": purpose,
             "target": target_path, "replaces": replacing, "sha256": digest,
             "size": len(data), "keep_pointer": keep_pointer, "pointer": pointer,
             "commit": outcome.get("commit")})
    return _result(
        f"Proposed {purpose} {filename} ({size_label}) for {target_path}, with a pointer note in "
        f"{area}/{topic_name}. It waits for review by {approver}.",
        {"status": "pending", "proposal_id": proposal_id, "purpose": purpose,
         "target": target_path, "sha256": digest, "size": len(data), "pointer": pointer,
         "commit": outcome.get("commit")})


def _file_now(brain, proposal_id, header, note_meta, pointer, *, who, label, title, origin,
              session_id, home):
    """File a document or asset at once, as one undo point: the capture policy says files
    from this origin need no review. The decision is recorded like an approval (by the owner,
    `auto-applied`), so the activity log and the file's history say where it came from."""
    from . import checkpoints
    target = str(header["target"])
    with checkpoints.batch(brain, actor=who, label=label,
                           source={"origin": origin or "chat", "session": session_id or "",
                                   "file": target}) as batch:
        with brain.deferring() as deferred:
            deferred.message = label
            brain.vault.write_proposal(proposal_id, header, note_meta, pointer)
            proposal = brain.state().snapshot.proposals.get(proposal_id)
            if proposal is None:
                return _result("File not filed: its proposal could not be read back.",
                               {"status": "error"}, True)
            applied = apply(brain, proposal, actor=who, auto=True)
            if not applied.is_error:
                batch.decisions.append({"action": "added", "proposal": proposal_id,
                                        "kind": "file.add", "title": title,
                                        "note": applied.data.get("pointer")})
    if applied.is_error:
        return _result(f"{applied.text} It waits for review instead ({proposal_id}).",
                       dict(applied.data, proposal_id=proposal_id), True)
    st = brain.state()
    st.index.warm()   # the new sections' vectors, ready for the first request that needs them
    card = st.index.cards.get(target)
    parts = len(st.index.file_sections(target))
    version = _as_int(card.meta.get("version")) if card is not None else None
    where = f" in the project {home.title}" if home is not None else ""
    replaced = header.get("replaces")
    text = (f"Filed {'version ' + str(version) + ' of ' if replaced and version else ''}"
            f"{title}{where}. Your AI can use it now"
            + (f": {parts} section(s) it can quote." if parts else ".")
            + (" The earlier text stays in its history." if replaced else ""))
    return _result(text, {
        "status": "applied", "proposal_id": proposal_id, "purpose": header.get("purpose"),
        "path": target, "id": card.id if card is not None else applied.data.get("pointer"),
        "pointer": applied.data.get("pointer"), "version": version,
        "file_status": card.meta.get("file_status") if card is not None else None,
        "replaced": replaced, "sections": parts, "project": home.id if home else None,
        "checkpoint": batch.checkpoint, "commit": (deferred.outcome or {}).get("commit")})


def card_kind(st, path) -> str | None:
    """The Library kind a filed document's card gives it, when it has a card."""
    card = st.index.cards.get(path) if path else None
    return str(card.meta.get("library") or "") or None if card is not None else None


def prompt_body(title: str, path: str, text: str) -> str:
    """A prompt's card: its words exactly as kept, so finding the card finds the prompt."""
    words = str(text or "").strip()
    first = words.splitlines()[0].strip() if words else ""
    if first.lstrip("# ").strip() == str(title).strip():
        words = "\n".join(words.splitlines()[1:]).strip()
    return (f"Prompt kept word for word (`{path}`); use it only when the person asks for it "
            f"by name.\n\n{words}")


def _replaceable(brain, replaces, purpose) -> str:
    """The filed path a new version replaces, or Refused."""
    path = clean_relpath(replaces)
    folder = "references/" if purpose == "reference" else "assets/"
    if not path.startswith(folder):
        raise Refused(f"a new {purpose} replaces a file under {folder}, not {path}")
    if purpose == "reference" and not path.endswith(".md"):
        raise Refused(f"{path}: a reference is filed as .md text")
    if not os.path.isfile(brain.vault.path(*path.split("/"))):
        raise Refused(f"{path} is not filed, so there is nothing to replace")
    return path


def _pointer_to(st, path) -> str | None:
    """The live note that points at a filed path, if one does."""
    for note in sorted(st.index.notes.values(), key=lambda n: n.id):
        if path in note.references or path in note.body:
            return note.id
    return None


def _free_path(brain, stem: str, ext: str) -> str:
    taken = {str(p.meta.get("target")) for p in _pending(brain, "file.add")}
    candidate = f"{stem}{ext}"
    n = 2
    while os.path.exists(brain.vault.path(*candidate.split("/"))) or candidate in taken:
        candidate = f"{stem}-{n}{ext}"
        n += 1
    return candidate


def _filed_copy(brain, digest: str) -> str | None:
    """Where the same bytes are already filed: a reference's original or an asset."""
    library = os.path.join(brain.vault.runtime_dir, "library")
    if os.path.isdir(library):
        for name in os.listdir(library):
            if name.startswith(digest):
                return f"library/{name}"
    assets = brain.vault.path("assets")
    if os.path.isdir(assets):
        for folder, _dirs, names in os.walk(assets):
            for name in names:
                path = os.path.join(folder, name)
                with open(path, "rb") as handle:
                    if sha(handle.read()) == digest:
                        return util.rel(path, brain.vault.root)
    return None


# ------------------------------------------------------------------ applying

def apply(brain, proposal, *, actor, auto=False, edits=None, body=None):
    """Install an approved upload: write its files, log the decision, commit, clear staging."""
    if proposal.kind in ("skill.create", "skill.update"):
        return _apply_skill(brain, proposal, actor=actor, auto=auto, body=body)
    if proposal.kind == "file.add":
        return _apply_file(brain, proposal, actor=actor, auto=auto, edits=edits, body=body)
    return _result(f"{proposal.kind} is not an upload.", {"status": "invalid"}, True)


def _apply_skill(brain, proposal, *, actor, auto, body):
    st = brain.state()
    target = dict(proposal.target)
    name, category = str(target["name"]), str(target.get("category") or "")
    existing = _find_skill(st, name)
    if proposal.kind == "skill.update" and existing is None:
        return _result(f"Skill {name} no longer exists; reject this proposal.",
                       {"status": "conflict"}, True)
    if proposal.kind == "skill.create" and existing is not None:
        return _result(f"A skill named {name} was added meanwhile; reject this proposal or "
                       "propose it as a change.", {"status": "conflict"}, True)
    folder_rel = (os.path.dirname(existing.path) if existing is not None
                  else f"skills/{category}/{name}")
    listing = manifest(brain, proposal.id).get("files") or []
    missing = [f["path"] for f in listing
               if not os.path.isfile(os.path.join(staging_dir(brain, proposal.id), "files",
                                                  *f["path"].split("/")))]
    if missing:
        return _result("Staged files are missing (" + ", ".join(missing) + "); the proposal "
                       "was probably made on another machine. Reject it and propose again.",
                       {"status": "conflict"}, True)
    meta = {k: v for k, v in target.items() if k in SKILL_KEY_ORDER and v not in (None, "", [])}
    meta["name"] = name
    text = proposal.body if body is None else str(body)
    touched = []
    skill_path = brain.vault.path(*folder_rel.split("/"), "SKILL.md")
    brain.vault.touch(skill_path)
    util.atomic_write(skill_path, fm.dump(meta, text.strip() + "\n", order=SKILL_KEY_ORDER))
    touched.append(skill_path)
    for entry in listing:
        data = _read_staged(brain, proposal.id, "files/" + entry["path"])
        destination = brain.vault.path(*folder_rel.split("/"), *entry["path"].split("/"))
        brain.vault.touch(destination)
        util.atomic_write_bytes(destination, data)
        touched.append(destination)
    return _finish(brain, proposal, actor=actor, auto=auto, touched=touched,
                   record={"skill": name, "path": folder_rel,
                           "files": [f["path"] for f in listing]},
                   message=f"{'Applied' if auto else 'Approved'} {proposal.kind} {name} "
                           f"({folder_rel}, {len(listing)} file(s)).",
                   data={"name": name, "path": folder_rel})


def _apply_file(brain, proposal, *, actor, edits, body, auto=False):
    from . import governance
    st = brain.state()
    info = manifest(brain, proposal.id)
    if not info:
        return _result("Staged file is missing; the proposal was probably made on another "
                       "machine. Reject it and propose again.", {"status": "conflict"}, True)
    target_path = str(info["target"])
    destination = brain.vault.path(*target_path.split("/"))
    replacing = bool(info.get("replaces"))
    if replacing:
        if not os.path.isfile(destination):
            return _result(f"{target_path} is gone; reject this proposal.",
                           {"status": "conflict"}, True)
        with open(destination, "rb") as handle:
            current = sha(handle.read())
        if info.get("base_sha256") and current != info["base_sha256"]:
            return _result(f"{target_path} changed since this new version was proposed; reject "
                           "it and propose the new version again.", {"status": "conflict"},
                           True)
    elif os.path.exists(destination):
        return _result(f"{target_path} was filed meanwhile; reject this proposal.",
                       {"status": "conflict"}, True)
    touched = []
    brain.vault.touch(destination)
    original = _read_staged(brain, proposal.id, info["original"])
    if info["purpose"] == "reference":
        text = _read_staged(brain, proposal.id, info["text"]).decode("utf-8").strip()
        source = (f"> Source: `{info['filename']}`, sha256 `{info['sha256']}`, filed "
                  f"{util.today()}. Converted text; the original is kept in the local library.")
        if text.startswith("# "):
            # The document has its own title: the source line goes under it.
            heading, _, rest = text.partition("\n")
            content = f"{heading}\n\n{source}\n\n{rest.strip()}\n"
        else:
            content = f"# {info['title']}\n\n{source}\n\n{text}\n"
        util.atomic_write(destination, content)
        ext = os.path.splitext(info["original"])[1]
        kept = os.path.join(brain.vault.runtime_dir, "library", info["sha256"] + ext)
        brain.vault.touch(kept)
        util.atomic_write_bytes(kept, original)
    else:
        util.atomic_write_bytes(destination, original)
    touched.append(destination)
    verb = "Filed" if auto else "Approved"
    if replacing:
        kept = str(info.get("keep_pointer") or "")
        kept = kept if kept and st.index.note(kept) is not None else None
        update = info.get("card") or {}
        card = st.index.note(update.get("id")) if update.get("id") else None
        record = {"note": kept, "path": target_path, "purpose": info["purpose"],
                  "sha256": info["sha256"], "replaced": target_path}
        if card is not None:
            # The card says which copy is current now, and what it covers.
            meta = dict(card.meta)
            meta.update({k: v for k, v in (update.get("meta") or {}).items()
                         if k not in governance.RESERVED and k != "id"})
            for key in ("version", "file_status"):
                if key not in (update.get("meta") or {}):
                    meta.pop(key, None)
            meta["revised"] = util.now_iso()
            body = str(update.get("body") or card.body)
            if body != card.body:
                # What the card said before (a prompt's earlier words): its history without git.
                record["previous"] = card.body
            brain.vault.write_note(card.path, meta, body)
            touched.append(brain.vault.path(card.path))
        return _finish(brain, proposal, actor=actor, auto=auto, touched=touched,
                       record=record,
                       message=f"{verb} the new version of {target_path}"
                               + (f"; card {kept} updated." if card is not None
                                  else f"; pointer note {kept} kept." if kept else "."),
                       data={"path": target_path, "pointer": kept, "purpose": info["purpose"],
                             "replaced": target_path})
    note_meta = dict(proposal.target)
    for key, value in (edits or {}).items():
        if key not in governance.RESERVED and key != "id":
            note_meta[key] = value
    if note_meta.get("id") in st.index.notes or note_meta.get("id") in st.index.archived:
        note_meta["id"] = governance.unique_id(st, str(note_meta["id"]))
    note_meta.update({"status": "approved", "approved_by": actor,
                      "approved_at": util.now_iso()})
    config = st.config
    note_rel = brain.vault.note_path(note_meta, config.structure.get("scope_levels") or [],
                                     config.structure.get("partition_kinds") or [])
    brain.vault.write_note(note_rel, note_meta, proposal.body if body is None else str(body))
    touched.append(brain.vault.path(note_rel))
    return _finish(brain, proposal, actor=actor, auto=auto, touched=touched,
                   record={"note": note_meta["id"], "path": target_path,
                           "purpose": info["purpose"], "sha256": info["sha256"]},
                   message=f"{verb} {info['purpose']} {target_path} with its card "
                           f"{note_meta['id']}.",
                   data={"path": target_path, "pointer": note_meta["id"],
                         "purpose": info["purpose"]})


def _finish(brain, proposal, *, actor, auto, touched, record, message, data):
    now = util.now_iso()
    decision = {"at": now, "action": "auto-applied" if auto else "approved", "by": actor,
                "proposal": proposal.id, "kind": proposal.kind, "scope": proposal.scope,
                "proposer": proposal.proposer or actor,
                "session": str(proposal.meta.get("session") or "")}
    decision.update(record)
    touched.append(brain.vault.path(brain.vault.append_decision(decision)))
    if proposal.path:
        brain.vault.remove_file(proposal.path)
        touched.append(brain.vault.path(proposal.path))
    discard(brain, proposal)
    outcome = brain.after_write(touched, message)
    return _result(message, dict(data, status="applied" if auto else "approved",
                                 id=proposal.id, commit=outcome.get("commit"),
                                 kernel=outcome.get("kernel")))


def preview(brain, proposal, limit=2000) -> dict:
    """What the inbox shows for an upload: its files and, for a document, its opening text."""
    info = manifest(brain, proposal.id)
    out = {"files": info.get("files") or [], "purpose": info.get("purpose"),
           "staged": bool(info)}
    if info.get("text"):
        try:
            out["preview"] = util.excerpt(
                _read_staged(brain, proposal.id, info["text"]).decode("utf-8"), limit)
        except OSError:
            out["preview"] = ""
    return out
