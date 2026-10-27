"""The packet says what it doesn't cover (v4 backend plan, 16.1), built without a model call.

A request word that no item in the packet holds, while some note the caller may see does, is
not covered. Each line names where a missing part likely is and the exact call that fetches it:
- the note holding a missing word that best fits the whole request (with its heading), when
  the word is a strong signal: a name in the request, or a word in the note's id or title;
- else the request's runners-up, the notes that score next below the packet's cut, with the
  missing words each holds and its summary;
- for a request about when, or what changed, the timeline.
At most three lines, and none when every word is covered. Words count the way the Brain's
word index counts them (index.BM25).
"""
from __future__ import annotations

import re
from datetime import timedelta

from . import util

LINES = 3
# A word in more than this share of the notes (and in more than COMMON notes) says little
# about where the missing part is.
SHARE, COMMON = 0.1, 3
# Where a missing word is must fit the whole request about as well as what the packet holds:
# at least this share of the best delivered item's score, so a stray word doesn't count.
RUNNER_UP = 0.5
# The request's own runners-up: the notes that score next below the packet's cut. In the
# tuning Brains most needed items a packet missed were among its next eight.
RUNNERS = 2
# A question about when: its own time words are what the timeline answers, not missing parts.
TIME_WORDS = {"since", "recent", "recently", "lately", "changed", "change", "new", "last",
              "past", "week", "month", "year", "yesterday", "today", "timeline", "history"}
_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
# Looking back only: "this week" is as often a plan ("launch it this week") as a question.
_AGO = (("yesterday", 1), ("last week", 7), ("past week", 7), ("last month", 31),
        ("past month", 31), ("last year", 366), ("past year", 366))
_WHEN = re.compile(r"\b(since|recent(ly)?|lately|changed|what's new|what is new|"
                   r"timeline|history)\b", re.I)


def since(request: str) -> str | None:
    """The date a request about when, or what changed, looks back to; None when it isn't."""
    text = str(request or "").lower()
    found = _ISO.search(text)
    if found:
        return found.group(1)
    for words, days in _AGO:
        if words in text:
            return (util.today_date() - timedelta(days=days)).isoformat()
    if _WHEN.search(text):
        return (util.today_date() - timedelta(days=31)).isoformat()
    return None


def _heading(note, term: str) -> str:
    """The heading the first line holding `term` sits under, if any."""
    heading = ""
    for line in str(note.body or "").splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if term in {util.stem(w) for w in util.terms(line)}:
            return heading
    return ""


_NAME = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][A-Za-z0-9]+|[A-Z]{2,})\b")


def _names(request: str) -> set[str]:
    """The request's names: a capitalized word not starting a sentence, or one in capitals."""
    return {util.stem(w.lower()) for w in _NAME.findall(str(request or "").strip())}


def _labels(note) -> set[str]:
    """The words of a note's id and title: what it says it is about."""
    text = note.id.replace("-", " ") + " " + str(getattr(note, "title", "") or "")
    return {util.stem(w) for w in util.terms(text) if w not in util.STOPWORDS}


def block(index, request: str, *, delivered: set[str], admitted: set[str],
          runners: list[str] = ()) -> tuple[str, dict]:
    """The coverage lines for a packet holding `delivered`, and what they say as data.
    `runners` are the notes the request scores best by the router, best first. (A floor on
    their score relative to the best one kept fewer misses at the same share of good lines,
    about one in five, in the tuning Brains.)"""
    bm = index.note_bm25
    terms = bm.query_terms(str(request or ""))
    said = {}  # each stem as the request wrote it
    for word in util.content_terms(bm.fold(str(request or ""))):
        said.setdefault(util.stem(word), word)
    limit = max(COMMON, int(SHARE * max(1, len(admitted))))
    when = since(request)
    skip = {util.stem(w) for w in TIME_WORDS} | TIME_WORDS if when else set()
    held = bm.scores(str(request or ""), restrict=sorted(delivered & set(bm.docs)))
    bar = RUNNER_UP * max(held.values(), default=0.0)
    covered, missing = [], []
    for term in terms:
        if term in skip:
            continue
        holders = set(bm._postings.get(term, {})) & admitted
        if holders & delivered:
            covered.append(term)
        elif holders and len(holders) <= limit:
            missing.append((term, holders - delivered))
    names = _names(request)
    places: dict[str, list[str]] = {}
    for term, holders in missing:
        ranked = bm.scores(str(request or ""), restrict=sorted(holders))
        best = max(ranked, key=lambda k: ranked[k]) if ranked else ""
        note = index.notes.get(best)
        # Only a strong signal of where: a name, or a word the note is labeled by that fits
        # the request about as well as the packet does.
        if note is not None and (term in names or (ranked[best] >= bar
                                                   and term in _labels(note))):
            places.setdefault(best, []).append(term)
    rows = []
    for note_id, words in places.items():
        note = index.notes.get(note_id)
        heading = _heading(note, words[0]) if note is not None else ""
        rows.append({"words": [said.get(w, w) for w in words],
                     "likely": note_id + (f"#{heading}" if heading else ""),
                     "fetch": f'notes(action: "get", id: "{note_id}")'})
    missing_words = [t for t, _h in missing]
    # Runners-up only when a word is missing: shown always, more packets carried lines at
    # the same share of good ones (about one in five) in the tuning Brains.
    for note_id in [r for r in runners if r not in places and r not in delivered][
            :RUNNERS if missing else 0]:
        note = index.notes.get(note_id)
        if note is None or note_id not in admitted:
            continue
        holds = [said.get(t, t) for t in missing_words if t in bm.docs.get(note_id, {})]
        rows.append({"words": holds or ["close match"], "likely": note_id,
                     "fetch": f'notes(action: "get", id: "{note_id}")',
                     "summary": util.excerpt(getattr(note, "summary", "")
                                             or getattr(note, "title", "") or "", 80)})
    rows = rows[:LINES - (1 if when else 0)]
    if when:
        rows.append({"words": ["when"], "likely": f"the timeline since {when}",
                     "fetch": f'activity(action: "timeline", since: "{when}")'})
    covered = [said.get(w, w) for w in covered]
    found = {"covered": covered, "not_covered": rows}
    if not rows:
        return "", found
    lines = ["## Not covered here", ""]
    if covered:
        lines.append(f"The items above hold: {', '.join(covered)}. Missing, and where:")
    for row in rows:
        gist = f" ({row['summary']})" if row.get("summary") else ""
        lines.append(f"- {', '.join(row['words'])}: likely in `{row['likely']}`{gist}, "
                     f"{row['fetch']}")
    return "\n".join(lines) + "\n", found
