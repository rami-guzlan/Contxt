"""Moving in: what an AI already knows about a person, read into ideas for the brain.

A memory list from ChatGPT or Claude, a CLAUDE.md, AGENTS.md or Cursor rules file, or any
pasted text is read WITHOUT WRITING ANYTHING: split into ideas (one statement each), each
sorted by kind and placed in a topic, then checked against what the brain holds (already
known, might disagree) and for private detail. The workspace proposes the ideas the person
keeps; they wait for the owner like any proposal.

Splitting is plain reading, no model: these sources are lists already (the prompt the app
gives asks for one fact per line, grouped under headings), so headings say what a group is
about and each line or sentence becomes one idea. Matching is the router's own relevance,
the same evidence a packet is built from.
"""
from __future__ import annotations

import re

from . import governance, review, util

SOURCES = {
    "chatgpt": "ChatGPT memory",
    "claude": "Claude memory",
    "cursor": "Cursor rules",
    "instructions": "An instruction file",
    "paste": "Pasted text",
}
# What an AI app remembers is about the person; an instruction file is about the work.
ABOUT_THE_PERSON = ("chatgpt", "claude")
MAX_SOURCES = 8
MAX_CHARS = 200_000          # one paste; a full export is a file for Capture instead
MAX_IDEAS = 400
MIN_WORDS = 3
MAX_IDEA = 600               # characters; a longer line is split into sentences
KNOWN = 0.9                  # this near a live note, it says what the brain already says
OVERLAP = review.OVERLAP     # this near, a contradiction is worth a look

HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s+(?P<md>.+?)\s*#*\s*$|\*\*(?P<bold>[^*]{2,80})\*\*:?"
                     r"\s*$|(?P<colon>[A-Z][^.!?:]{1,60}):\s*$)")
BULLET = re.compile(r"^\s*(?:[-*+•‣▪◦]|\d{1,3}[.)])\s+(?P<text>.+)$")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
FENCE = re.compile(r"^\s*(?:```|~~~)")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
EMPHASIS = re.compile(r"(\*\*|__|\*|`)(?=\S)(.+?)(?<=\S)\1")
PREAMBLE = re.compile(
    r"^(?:sure|certainly|of course|absolutely|okay|ok|here(?:'s| is| are)|below (?:is|are)|"
    r"based on (?:our|my|what)|this is (?:what|everything)|i(?:'ve| have) (?:noted|saved|"
    r"remembered)|let me know|hope this helps|feel free|i'm not sure|i am not sure)\b",
    re.IGNORECASE)

# What a group heading says its lines are: (kind, words that say so), first match wins.
GROUP_KINDS = [
    ("identity", ("about me", "about you", "who i am", "who you are", "profile", "identity",
                  "background", "personal", "bio")),
    ("rule", ("how i like", "how you like", "how to work", "preference", "prefer", "style",
              "writing", "rules", "instruction", "guideline", "convention", "do and don",
              "always", "never", "workflow", "ways of working", "tone", "voice", "format")),
    ("state", ("project", "working on", "current", "goal", "now", "priorit", "focus",
               "this quarter", "plans", "roadmap")),
    ("fact", ("people", "team", "contacts", "family", "colleague", "client", "customer",
              "facts", "knowledge", "context", "company", "business", "work", "tools",
              "stack", "tech")),
]
IMPERATIVE = re.compile(
    r"^(?:use|run|prefer|write|keep|avoid|never|always|don't|do not|make sure|ensure|check|"
    r"add|put|call|name|start|end|lead|ask|reply|respond|answer|format|follow|stick to|"
    r"be |stay|skip|include|exclude|cite|explain|show|test|commit|open|close)\b", re.IGNORECASE)
WANTS = re.compile(r"\b(?:prefers?|likes?|wants?|dislikes?|hates?|would rather|'d rather|"
                   r"enjoys?|avoids?)\b", re.IGNORECASE)
ABOUT_PERSON = re.compile(r"^(?:i am|i'm|my name|i work|i live|i was|i have|i've been|"
                          r"user is|the user is|is an?|works as|works at|lives in)\b",
                          re.IGNORECASE)
# A memory line with no subject ("Prefers short answers"), or one about "the user": the note
# names the person instead, so every AI that reads it knows who.
SUBJECTLESS = re.compile(
    r"^(?:prefers|likes|loves|wants|dislikes|hates|enjoys|avoids|is|has|works|lives|uses|"
    r"runs|leads|manages|owns|writes|speaks|studies|plans|needs|values|cares|tends|"
    r"usually|often|always|never|does|did|was|teaches|builds|travels)\b")
THE_USER = re.compile(r"^(?:the user|user)('s)?\b", re.IGNORECASE)
# "Never use emojis" is an instruction; "Never uses emojis" says what the person does.
HABIT = re.compile(r"^(?:always|never|usually|often)\s+([a-z']+)")
GENERIC_NAMES = {"me", "you", "owner", "user", "i"}

# Private detail: what should not reach every AI without the person's say. (label, pattern)
SECRET = "a password or key"
PRIVATE = [
    (SECRET, re.compile(r"\b(?:password|passcode|passphrase|api[ -]?key|secret key|"
                        r"access token|private key|pin code)\b", re.I)),
    ("an email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("a phone number", re.compile(r"(?:\+?\d{1,3}[\s.-])?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}\b")),
    ("an ID or account number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b(?:\d{4}[ -]){3}\d{4}\b|"
                                           r"\b\d{9,19}\b")),
    ("a home address", re.compile(r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:Street|St|Avenue|"
                                  r"Ave|Road|Rd|Lane|Ln|Drive|Dr|Boulevard|Blvd|Court|Ct|"
                                  r"Way|Place|Pl|Terrace)\b")),
    ("a date of birth", re.compile(r"\b(?:date of birth|born on|birthday|d\.o\.b\.?)\b", re.I)),
    ("health detail", re.compile(r"\b(?:diagnos\w*|medication|prescri\w+|therap(?:y|ist)|"
                                 r"allerg\w+|pregnan\w+|disabilit\w+|depression|anxiety|"
                                 r"adhd|surgery|illness|medical condition)\b", re.I)),
    ("money detail", re.compile(r"\b(?:salary|income|net worth|bank account|credit score|"
                                r"debt|mortgage)\b", re.I)),
]
STATUSES = ("new", "known", "waiting", "disagree", "private")
# The goals an idea can serve, by the question whose answer holds them, in plain words.
GOAL_LABELS = (("purpose", "what your Brain is for"), ("slips", "what slips today"),
               ("how", "how you like work done"), ("never", "what an AI never does"),
               ("work", "your work"), ("working", "how you will know it works"))
FIT_WORDS = 2  # content words an idea shares with a goal's answer to serve it (3 for a project)
LEFT_OUT = {"off": "none of your goals or projects covers it",
            "asked": "you asked to leave this kind of thing out"}


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _plain(text: str) -> str:
    """A line as a statement: links as their words, emphasis and quotes dropped, spaced."""
    text = LINK.sub(r"\1", str(text or ""))
    for _ in range(2):
        text = EMPHASIS.sub(r"\2", text)
    text = " ".join(text.split()).strip().strip("\"'“”").strip()
    return text.rstrip(":").strip()


def _group_kind(group: str) -> str | None:
    low = group.lower()
    for kind, words in GROUP_KINDS:
        if any(word in low for word in words):
            return kind
    return None


def kind_of(text: str, group: str, source: str) -> str:
    """identity (about the person), rule (how work is done), state (where things stand) or
    fact: from the group's heading first, then from how the statement reads."""
    named = _group_kind(group)
    if named == "rule" or governance.RULE_START.match(text) or IMPERATIVE.match(text):
        return "rule"
    if named:
        return named
    if WANTS.search(text):
        return "rule"
    if ABOUT_PERSON.match(text) and source not in ("cursor", "instructions"):
        return "identity"
    return "fact"


def with_subject(text: str, name: str) -> str:
    """"Prefers short answers" reads "Sam prefers short answers"; "The user is..." reads
    "Sam is...". Without a usable name the text stays as it is."""
    if not name or name.lower() in GENERIC_NAMES:
        return text
    found = THE_USER.match(text)
    if found:
        rest = text[found.end():].lstrip()
        return f"{name}{chr(39) + 's' if found.group(1) else ''} {rest}".strip()
    lowered = text[:1].lower() + text[1:]
    habit = HABIT.match(lowered)
    if habit and not (habit.group(1).endswith("s") and not habit.group(1).endswith("ss")):
        return text  # an instruction to whoever reads it, not a habit of the person's
    if SUBJECTLESS.match(lowered):
        return f"{name} {lowered}"
    return text


def split(text: str) -> list[dict]:
    """[{"text", "group"}]: one idea per bullet, line or sentence, under the heading it sat
    in. Preambles ("Here is what I remember"), code blocks and tables are left out."""
    out: list[dict] = []
    group = ""
    fenced = False
    for raw in str(text or "").replace("\r\n", "\n").replace("﻿", "").split("\n"):
        line = raw.rstrip()
        if FENCE.match(line):
            fenced = not fenced
            continue
        stripped = line.strip()
        if fenced or not stripped or stripped in ("---", "***", "___"):
            continue
        if stripped.startswith(("|", "<!--")):
            continue
        bullet = BULLET.match(line)
        heading = None if bullet else HEADING.match(line)
        if heading:
            group = _plain(heading.group("md") or heading.group("bold") or heading.group("colon"))
            continue
        body = _plain((bullet.group("text") if bullet else stripped).lstrip(">").strip())
        if not body:
            continue
        parts = [body] if bullet and len(body) <= MAX_IDEA else SENTENCE.split(body)
        for part in parts:
            part = _plain(part)
            if len(part.split()) < MIN_WORDS or PREAMBLE.match(part):
                continue
            out.append({"text": part[:MAX_IDEA], "group": group})
    return out


def private_detail(text: str) -> str | None:
    """What private detail a statement holds, in plain words, or None."""
    return next((label for label, pattern in PRIVATE if pattern.search(text)), None)


def analyze(brain, sources, *, name: str = "", principal=None):
    """Read sources [{"kind", "text", "label"?}] into ideas, checked against the brain, and
    the counts each stage of the reading came to. `name` is how notes about the person name
    them ("Sam prefers..."). Writes nothing."""
    if not isinstance(sources, list) or not sources:
        return _result("Give at least one source to read.", {"status": "invalid"}, True)
    if len(sources) > MAX_SOURCES:
        return _result(f"Read at most {MAX_SOURCES} sources at a time.",
                       {"status": "invalid"}, True)
    st = brain.state()
    who = brain.principal(principal)
    caller = brain.caller(who)
    if not isinstance(caller, tuple):
        return caller
    chain, partitions = caller
    name = " ".join(str(name or "").split()).split(" ")[0] if str(name or "").strip() else ""
    if not name:
        label = st.scopes.label(who).split(":")[-1].strip()
        name = label.split()[0] if label else ""
    notes = [n for n in st.router.admitted_notes(chain, partitions) if not st.config.is_focus(n)]
    canon = {util.canonical(n.body): n for n in notes}
    canon.update({util.canonical(n.title): n for n in notes if len(n.title.split()) >= 4})
    waiting = {util.canonical(p.body): p for p in st.snapshot.proposals.values()}
    read, ideas, seen = [], [], set()
    for number, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            return _result("Each source is an object with a kind and its text.",
                           {"status": "invalid"}, True)
        kind = str(source.get("kind") or "paste").strip().lower()
        kind = kind if kind in SOURCES else "paste"
        text = str(source.get("text") or "")
        if len(text) > MAX_CHARS:
            return _result(f"One source is at most {MAX_CHARS:,} characters; bring a whole "
                           "export in as a file in Capture instead.", {"status": "invalid"},
                           True)
        label = " ".join(str(source.get("label") or SOURCES[kind]).split())[:80]
        read.append({"id": f"s{number}", "kind": kind, "label": label, "chars": len(text),
                     "ideas": 0})
        for item in split(text):
            if len(ideas) >= MAX_IDEAS:
                break
            about_person = kind in ABOUT_THE_PERSON
            statement = with_subject(item["text"], name) if about_person else item["text"]
            key = util.canonical(statement)
            if not key or key in seen:
                continue
            seen.add(key)
            read[-1]["ideas"] += 1
            idea_kind = kind_of(item["text"], item["group"], kind)
            ideas.append({"id": f"i{len(ideas) + 1}", "source": read[-1]["id"],
                          "source_kind": kind, "text": statement, "original": item["text"],
                          "group": item["group"], "kind": idea_kind,
                          # about the person, filed with their own notes: what an AI app
                          # remembers, who they are, and what they say they prefer
                          "personal": idea_kind == "identity" or (
                              idea_kind == "rule" and (
                                  about_person
                                  or bool(governance.FIRST_PERSON.search(item["text"]))))})
    sifter = sift(brain, st, chain, partitions)
    for idea in ideas:
        _check(brain, st, idea, notes, canon, waiting, chain, partitions, who)
        _fit(idea, sifter)
    counts = {status: sum(1 for i in ideas if i["status"] == status) for status in STATUSES}
    kinds = {k: sum(1 for i in ideas if i["kind"] == k and i["status"] not in ("known",
                                                                              "waiting"))
             for k in ("identity", "rule", "state", "fact")}
    keepable = [i for i in ideas if i["status"] in ("new", "disagree", "private")]
    projects: dict[str, int] = {}
    for idea in keepable:
        if idea["fits"] and idea["serves"]["project"]:
            title = idea["serves"]["project"]["title"]
            projects[title] = projects.get(title, 0) + 1
    stages = {"sources": len(read), "chars": sum(s["chars"] for s in read),
              "ideas": len(ideas), "kinds": kinds, **counts,
              # the sift: what serves the goals or a project (or says who the person is and
              # how they work), and what was left out, one tap from kept
              "sifted": sifter is not None,
              "fits": sum(1 for i in keepable if i["fits"]),
              "for_goals": sum(1 for i in keepable if i["fits"] and i["serves"]["goal"]),
              "for_projects": projects,
              "about_you": sum(1 for i in keepable if i["fits"] and i["serves"]["about_you"]),
              "left_out": sum(1 for i in keepable if not i["fits"]),
              "to_keep": sum(1 for i in keepable if i["fits"])}
    examples = {}
    if ideas:
        examples["split"] = next((i["id"] for i in ideas if i["text"] != i["original"]),
                                 ideas[0]["id"])
    for stage, statuses in (("known", ("known", "waiting")), ("disagree", ("disagree",)),
                            ("private", ("private",)), ("new", ("new",))):
        found = next((i for i in ideas if i["status"] in statuses), None)
        if found is not None:
            examples[stage] = found["id"]
    if sifter is not None:
        for stage, wanted in (("fits", True), ("left_out", False)):
            found = next((i for i in keepable if i["fits"] is wanted and (
                not wanted or i["serves"]["goal"] or i["serves"]["project"])), None)
            if found is not None:
                examples[stage] = found["id"]
    return _result(
        f"Read {len(read)} source(s) into {len(ideas)} idea(s): {counts['new']} new, "
        f"{counts['known'] + counts['waiting']} already known, {counts['disagree']} might "
        f"disagree, {counts['private']} with private detail.",
        {"sources": read, "ideas": ideas, "stages": stages, "examples": examples})


def _stems(text) -> set:
    return util.stems(util.content_terms(text))


def sift(brain, st, chain, partitions) -> dict | None:
    """What ideas are weighed against: the words of each of the owner's goals, what they asked
    to leave out, and the active projects (names, other names, what each is for). None until
    the owner has said what the Brain is for."""
    from . import goals as goals_mod
    answers = goals_mod.read(brain).get("answers") or {}
    if not str(answers.get("purpose") or "").strip():
        return None
    return {"goals": [(label, _stems(answers.get(key) or "")) for key, label in GOAL_LABELS
                      if str(answers.get(key) or "").strip()],
            "leave_out": _stems(answers.get("leave_out") or ""),
            "projects": [(f, [n for n in [f.title, *f.aliases] if n],
                          _stems(f"{f.title} {' '.join(f.aliases)} {f.note.summary}"))
                         for f in st.router.admitted_focuses(chain, partitions) if f.active]}


def _fit(idea, sifter) -> None:
    """Does an idea serve one of the goals, belong to an active project, or tell every AI who
    the person is or how they want work done? Sets `fits` and `serves` ({goal, project,
    about_you}); one that fits nothing gets `left_out`, the reason, and can still be kept."""
    serves = {"goal": None, "project": None,
              "about_you": bool(idea["personal"]) or idea["kind"] in ("identity", "rule")}
    idea["serves"] = serves
    idea["fits"] = True
    if sifter is None:
        return  # no goals yet: nothing to sift against
    words = _stems(idea["text"])
    plain = util.normalize(idea["text"])
    for focus, names, stems in sifter["projects"]:
        if any(util.phrase_in(name, plain) for name in names) or \
                len(words & stems) >= FIT_WORDS + 1:
            serves["project"] = {"id": focus.id, "title": focus.title}
            break
    shared, label = max(((len(words & stems), label) for label, stems in sifter["goals"]),
                        default=(0, None))
    if shared >= FIT_WORDS:
        serves["goal"] = label
    if not serves["project"] and len(words & sifter["leave_out"]) >= FIT_WORDS:
        idea.update(fits=False, left_out=LEFT_OUT["asked"])
    elif not (serves["goal"] or serves["project"] or serves["about_you"]):
        idea.update(fits=False, left_out=LEFT_OUT["off"])


def _check(brain, st, idea, notes, canon, waiting, chain, partitions, who) -> None:
    """Where an idea goes, and whether the brain already says it, says otherwise, or should
    keep it out of every AI's way (private detail)."""
    text = idea["text"]
    key = util.canonical(text)
    area, topic = governance.guess_placement(brain, text, chain, partitions)
    if idea["personal"] and st.scopes.kind(who) == "person":
        area, topic = governance.personal_topic(brain, who) or (area, topic)
    idea["topic"] = f"{area}/{topic}"
    idea["topic_label"] = st.index.topic_label(idea["topic"])
    idea["match"] = None
    idea["why"] = ""
    same = canon.get(key)
    if same is not None:
        idea.update(status="known", why="the Brain says this already",
                    match={"id": same.id, "title": same.title, "score": 1.0})
        return
    pending = waiting.get(key)
    if pending is not None:
        idea.update(status="waiting", why="the same suggestion is already waiting",
                    match={"id": pending.id,
                           "title": str(pending.target.get("title") or pending.id),
                           "score": 1.0})
        return
    scored = st.router.score_notes(text, notes)[:3] if notes else []
    if scored and scored[0].score >= KNOWN:
        best = scored[0]
        idea.update(status="known", why="the Brain says much the same",
                    match={"id": best.item.id, "title": best.item.title,
                           "score": round(best.score, 3)})
        return
    for candidate in scored:
        if candidate.score < OVERLAP:
            break
        clash = review.contradiction(text, candidate.item.body)
        if clash:
            idea.update(status="disagree", why=clash,
                        match={"id": candidate.item.id, "title": candidate.item.title,
                               "score": round(candidate.score, 3)})
            return
    detail = private_detail(text)
    if detail:
        idea.update(status="private", why=f"holds {detail}", private=detail,
                    secret=detail == SECRET)
        return
    idea["status"] = "new"
