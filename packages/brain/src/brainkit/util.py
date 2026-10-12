"""Small shared helpers: tokens, terms, hashing, time and atomic file writes.

Standard library only. `tiktoken` is used for exact token counts when it is installed and a
conservative character estimate is used otherwise, so the engine runs with no installs.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import tempfile
import time
from functools import lru_cache

# ------------------------------------------------------------------ tokens

TOKEN_ENCODING = "o200k_base"


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken  # type: ignore
    except ImportError:
        return None
    try:
        return tiktoken.get_encoding(TOKEN_ENCODING)
    except Exception:
        return None


def tokens(text) -> int:
    """Token count of `text`: exact with tiktoken, otherwise a ceil(chars / 4) estimate."""
    text = str(text or "")
    if not text:
        return 0
    encoder = _encoder()
    if encoder is not None:
        return len(encoder.encode(text))
    return (len(text) + 3) // 4


def tokenizer_status() -> dict:
    encoder = _encoder()
    if encoder is None:
        return {"exact": False, "implementation": "estimate", "encoding": None}
    return {"exact": True, "implementation": "tiktoken", "encoding": TOKEN_ENCODING}


# ------------------------------------------------------------------ text

_WORD = re.compile(r"[a-z0-9]+")

# Function words that carry no routing evidence. Kept deliberately small: domain words and
# verbs that express intent ("send", "write", "status") are NOT stop words, because the
# router reads them as cues.
STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "has",
    "have", "i", "if", "in", "into", "is", "it", "its", "me", "my", "of", "on", "or", "our",
    "so", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those",
    "to", "us", "was", "we", "were", "will", "with", "you", "your", "please", "can", "could",
    "would", "should", "do", "does", "did", "what", "which", "who", "how", "when", "where",
    "why", "about", "any", "some", "all", "just", "also", "than", "too", "very", "up",
    "out", "over", "under", "again", "more", "most", "such", "only", "own", "same", "no",
    "not", "nor", "now", "here", "get", "got", "let", "lets", "via", "per", "etc",
})

# Verbs that ask the assistant to produce something. Read as intent, and excluded from
# relevance scoring because every procedure description contains them.
ACTION_VERBS = frozenset({
    "create", "build", "write", "draft", "edit", "make", "produce", "design", "update",
    "publish", "generate", "format", "implement", "turn", "develop", "perform", "record",
    "revise", "rewrite", "tighten", "sharpen", "prepare", "compose", "continue", "finish",
    "plan", "outline", "summarize", "shorten", "expand", "polish", "fix", "refactor",
    "review", "audit", "translate", "convert", "add", "remove", "change",
})


def terms(text) -> list[str]:
    """Lowercase alphanumeric words longer than one character, in order."""
    return [w for w in _WORD.findall(str(text or "").lower()) if len(w) > 1]


def normalize(text) -> str:
    return " ".join(terms(text))


# Multiword terms read as one word. Split into words, "call to action" is "call" (which
# matches notes about cold calling) and "action". A vault adds its own in routing.json
# `phrases` ({"statement of work": "sow"}).
PHRASES = {"call to action": "cta", "calls to action": "cta"}
_FOLDERS: dict = {}


def phrase_folder(extra=None):
    """A function that rewrites each known multiword term in a text as its one word, ignoring
    case and the spaces or hyphens between the words: "Add a Call-to-Action" becomes
    "Add a cta". The same folding is applied to notes and requests, so both sides match."""
    table = dict(PHRASES)
    for key, value in (extra or {}).items():
        key, value = " ".join(str(key).lower().split()), str(value or "").strip().lower()
        if key and value and not key.startswith("_"):
            table[key] = value
    cache_key = tuple(sorted(table.items()))
    found = _FOLDERS.get(cache_key)
    if found is None:
        alternatives = sorted(table, key=len, reverse=True)
        pattern = re.compile(r"\b(?:" + "|".join(r"[\s-]+".join(map(re.escape, k.split()))
                                                  for k in alternatives) + r")\b",
                             re.IGNORECASE)

        def fold(text, _pattern=pattern, _table=table):
            return _pattern.sub(
                lambda m: _table[" ".join(re.split(r"[\s-]+", m.group(0).lower()))],
                str(text or ""))
        found = _FOLDERS[cache_key] = fold
    return found


REVIEWER_TEXT = re.compile(r"(?im)^\W*(?:reviewer'?s? note|note (?:to|for) (?:the )?reviewer|"
                           r"for the reviewer|review note)\b")
LOCAL_PATH = re.compile(r"(?<![\w/])(?:[A-Za-z]:[\\/]|/(?:Users|home)/)[^\s`'\"<>|]+")


def text_flags(text) -> list[str]:
    """What a note's text should not carry: words for its reviewer, which every model that
    reads the note repeats, and a path on one computer, which means nothing anywhere else."""
    text = str(text or "")
    out = []
    if REVIEWER_TEXT.search(text):
        out.append("speaks to its reviewer; that belongs in the proposal's reason, not the note")
    match = LOCAL_PATH.search(text)
    if match:
        out.append(f"names a path on one computer ({excerpt(match.group(0), 60)}); name the "
                   "file by its folder instead")
    return out


_CANONICAL = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*|[$%£€]")


def canonical(text) -> str:
    """Text reduced for "is this the same statement?": case and spacing ignored, every word,
    number and currency sign kept. Unlike `normalize` (for matching), "$4,500" and "$3,500"
    stay different."""
    return " ".join(_CANONICAL.findall(str(text or "").lower()))


def content_terms(text) -> list[str]:
    """Distinct relevance-bearing terms in request order (stop words and action verbs out)."""
    seen: dict[str, None] = {}
    for word in terms(text):
        if word in STOPWORDS or word in ACTION_VERBS:
            continue
        seen.setdefault(word, None)
    return list(seen)


def stem(word: str) -> str:
    """A light plural/verb-ending stemmer. Enough to match "posts" to "post" and
    "approved" to "approve", deliberately not a real morphological analyser."""
    for suffix, keep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            if suffix == "es" and not word.endswith(("sses", "ches", "shes", "xes")):
                continue
            if suffix == "s" and word.endswith("ss"):
                continue
            return word[: -len(suffix)] + keep
    return word


def stems(words) -> set[str]:
    return {stem(w) for w in words}


def phrase_in(phrase: str, normalized_text: str) -> bool:
    """Whole-word phrase containment over normalized text."""
    needle = normalize(phrase)
    if not needle:
        return False
    return f" {needle} " in f" {normalized_text} "


def cli_name(config=None) -> str:
    """How this vault's brain CLI is run: brain.json `cli` (a vault repository with its own
    launcher says `python brain.py`), else `brain`, the package's command. Startup files are
    rendered from the vault alone, so every process writes the same ones; $BRAIN_CLI only
    names the command in messages when no vault is at hand."""
    declared = str(getattr(config, "cli", "") or "").strip()
    if declared:
        return declared
    if config is not None:
        return "brain"
    return str(os.environ.get("BRAIN_CLI") or "brain").strip() or "brain"


def excerpt(text, limit=240) -> str:
    flat = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(flat) <= limit:
        return flat
    return flat[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "..."


def slugify(text, limit=60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
    return slug[:limit].rstrip("-") or "item"


# ------------------------------------------------------------------ hashing and time

def sha256(text) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def short_hash(text, length=12) -> str:
    return sha256(text)[:length]


def now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def now_iso() -> str:
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")


def local(moment: _dt.datetime) -> _dt.datetime:
    """`moment` on the owner's clock: the machine's time zone. Tests pin it to put the owner
    in a time zone of their choosing."""
    return moment.astimezone()


def today() -> str:
    """Today's date where the owner is (the machine's local date), as YYYY-MM-DD: the date
    written on notes and the day freshness is judged by."""
    return today_date().isoformat()


def today_date() -> _dt.date:
    """`today()` as a date."""
    return local(now()).date()


def local_date(stamp) -> _dt.date | None:
    """The owner's date at a moment the Brain stamped in UTC (`now_iso()`), or None when
    `stamp` is not one: on a New York evening, UTC is already on the next day."""
    try:
        return local(_dt.datetime.fromisoformat(str(stamp))).date()
    except (ValueError, OverflowError, OSError):
        return None


def parse_date(value):
    try:
        return _dt.date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ files

def read_text(path) -> str:
    """UTF-8 text, without the byte order mark some Windows editors put first (it would hide
    a first heading or front matter)."""
    with open(path, encoding="utf-8-sig") as handle:
        return handle.read()


def atomic_write(path, text) -> None:
    """Write through a temp file in the same folder, then replace. Newlines are LF."""
    _replace(path, lambda fd: _text_to(fd, text))


def atomic_write_bytes(path, data: bytes) -> None:
    """The same, for bytes written as they are."""
    _replace(path, lambda fd: _bytes_to(fd, data))


def _text_to(fd, text) -> None:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _bytes_to(fd, data) -> None:
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def _replace(path, write) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    try:  # a file keeps its permissions; a new one gets the usual 644, not mkstemp's 600
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        write(fd)
        os.chmod(tmp, mode)
        replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def replace(src, dst, *, tries: int = 6, wait: float = 0.05) -> None:
    """os.replace, tried again for a moment when Windows refuses it because another process
    (an antivirus scan, the search indexer) holds the file just then."""
    for attempt in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(wait * (attempt + 1))


def append_jsonl(path, record: dict) -> None:
    """Append one JSON object as one line. Append-only journals use this and nothing else."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def read_jsonl(path) -> list[dict]:
    rows = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def rel(path, root) -> str:
    return os.path.relpath(path, root).replace("\\", "/")
