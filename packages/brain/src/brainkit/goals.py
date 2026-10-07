"""The brain's goals: what its owner wants it to help with, in their own words.

The owner answers a short interview (the first run asks it; the answers change any time). One
note keeps them, `you-goals`, in the owner's own scope and marked confidential: every answer
under its question, with the interview as its evidence.

WHAT THE GOALS STEER. What gets pulled into the brain, not what an AI receives for a request.
When something is brought in (a transcript, a file, a note) and summarized, and context is
pulled out of it, the work weighs every piece against these answers and the active projects.
Routing stays as it is, so answers stay predictable: the note is on demand like any other,
and no part of it rides in every conversation.

Writing them is the owner's own act: the note changes as one undo point, whatever the
governance preset (the owner is the approver, and these are their words). Nothing from the
interview waits for review.
"""
from __future__ import annotations

import re

from . import governance, util

GOALS_ID = "you-goals"
TITLE = "Your goals for this Brain"
MAX_ANSWER = 6000
MAX_PURPOSE = 600
# Each question: why it is asked (one line), and an example answer by the kind of brain it is
# (brain.json `starter`; `default` for any other).
QUESTIONS = [
    {"id": "purpose", "required": True,
     "question": "What do you want this Brain to help you do?",
     "why": "Everything you bring in is sifted against this.",
     "examples": {
         "default": "Keep my work straight across every AI I use, without explaining it twice.",
         "personal": "Run our household without dropping things: meals, school, money.",
         "programmer": "Make every coding assistant follow how I build, so I stop repeating it.",
         "entrepreneur": "Run my two businesses without dropping things.",
         "knowledge-company": "Keep our marketing consistent and on message, whoever writes it.",
     }},
    {"id": "work",
     "question": "What do you work on, and for whom?",
     "why": "So it can tell your work from everything else.",
     "examples": {
         "default": "I lead marketing at a 40-person software company, for our sales team.",
         "personal": "Our family of four: two kids at school, both of us working.",
         "programmer": "Backend services in Python for a payments team.",
         "entrepreneur": "A subscription box company I run, and an angel portfolio.",
         "knowledge-company": "Marketing for a training company that serves manufacturers.",
     }},
    {"id": "slips",
     "question": "Where do things slip today? What do you forget, redo, or explain over and "
                 "over?",
     "why": "That is what it should catch first.",
     "examples": {
         "default": "Follow-ups after meetings, and explaining our positioning to every new "
                    "draft.",
         "personal": "Who picks up whom, and which bills are due.",
         "programmer": "Our test and release conventions, every new session.",
         "entrepreneur": "Investor updates, and promises I make in calls.",
         "knowledge-company": "Which numbers we may quote, and who approves what.",
     }},
    {"id": "how",
     "question": "What should every AI always know about how you like work done?",
     "why": "Told once, used by every AI you connect.",
     "examples": {
         "default": "Plain writing, short sentences, the answer first.",
         "personal": "Short lists, nothing fancy, weekends kept free.",
         "programmer": "Small commits, tests first, no new dependencies without asking.",
         "entrepreneur": "Numbers first, then the decision you need from me.",
         "knowledge-company": "Our brand voice: plain, specific, no hype.",
     }},
    {"id": "never",
     "question": "What should an AI never do for you without asking?",
     "why": "Your lines, written down once.",
     "examples": {
         "default": "Send or publish anything, or spend money.",
         "personal": "Book, buy or share anything about the kids.",
         "programmer": "Push, delete branches, or change the database.",
         "entrepreneur": "Email investors, or commit to a date.",
         "knowledge-company": "Publish anything external before approval.",
     }},
    {"id": "leave_out",
     "question": "When it reads your meetings and files, what should it leave out?",
     "why": "What it skips matters as much as what it keeps.",
     "examples": {
         "default": "Small talk, other teams' projects, anything about my family that comes "
                    "up in work meetings.",
         "personal": "Gossip, and anything medical unless I say so.",
         "programmer": "Stack traces and one-off debugging.",
         "entrepreneur": "Small talk, and anything said off the record.",
         "knowledge-company": "Other departments' plans, and client names in public work.",
     }},
    {"id": "in_motion",
     "question": "What is in motion right now?",
     "why": "One per line: each can start a project.",
     "examples": {
         "default": "Website relaunch\nQ4 campaign",
         "personal": "Kitchen renovation\nSummer trip",
         "programmer": "Payments API v2\nMigrating to Postgres 17",
         "entrepreneur": "Seed round\nLoopline launch",
         "knowledge-company": "Q4 webinar series\nWebsite refresh",
     }},
    {"id": "working",
     "question": "A month from now, how will you know it is working?",
     "why": "So you can check that it helps.",
     "examples": {
         "default": "I stop re-explaining things, and drafts need fewer fixes.",
         "personal": "No missed pickups, and the weekly plan takes ten minutes.",
         "programmer": "New sessions follow our conventions without a reminder.",
         "entrepreneur": "Investor updates take an hour, not a day.",
         "knowledge-company": "Drafts come back on message the first time.",
     }},
]
BY_ID = {q["id"]: q for q in QUESTIONS}
# Where the note is filed: the owner's own area when the brain has one.
HOMES = (("me", "goals"), ("you", "goals"), ("assistant", "goals"))


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def _clean(text) -> str:
    """An answer as written: line breaks kept, trailing space and runs of blank lines gone."""
    lines = [line.rstrip() for line in str(text or "").replace("\r\n", "\n").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def questions(starter: str = "") -> list[dict]:
    """The questions, each with the example for this kind of brain."""
    return [{"id": q["id"], "question": q["question"], "why": q["why"],
             "required": bool(q.get("required")),
             "example": q["examples"].get(starter) or q["examples"]["default"]}
            for q in QUESTIONS]


def compose(answers: dict) -> str:
    """Every answer under its question, as Markdown: the purpose first."""
    parts = ["# What this Brain is for", "", str(answers.get("purpose") or "").strip(), ""]
    for question in QUESTIONS[1:]:
        answer = str(answers.get(question["id"]) or "").strip()
        if answer:
            parts += [f"## {question['question']}", "", answer, ""]
    return "\n".join(parts).strip() + "\n"


def parse(body: str) -> dict:
    """{question id: answer} from a goals note `compose` wrote (headings are the questions)."""
    out: dict[str, str] = {}
    by_text = {q["question"].lower(): q["id"] for q in QUESTIONS}
    current = "purpose"
    lines: list[str] = []
    for line in str(body or "").splitlines():
        heading = re.match(r"^(#{1,2})\s+(.+?)\s*$", line)
        if heading:
            if lines:
                out[current] = "\n".join(lines).strip()
            text = heading.group(2).strip()
            current = "purpose" if heading.group(1) == "#" else by_text.get(text.lower(), "")
            lines = []
            continue
        lines.append(line)
    if lines:
        out[current] = "\n".join(lines).strip()
    return {k: v for k, v in out.items() if k and v}


def read(brain) -> dict:
    """The questions (with this brain's examples), and the owner's answers when it has them."""
    st = brain.state()
    note = st.index.note(GOALS_ID)
    starter = str(st.config.data.get("starter") or "")
    answers = parse(note.body) if note is not None else {}
    return {"questions": questions(starter), "answers": answers,
            "exists": note is not None and bool(answers.get("purpose")),
            "id": GOALS_ID, "starter": starter or None,
            "updated": (str(note.meta.get("revised") or note.meta.get("approved_at")
                            or note.added or "") or None) if note is not None else None,
            "purpose": answers.get("purpose", ""),
            "projects": [line.strip(" -*\t") for line in
                         str(answers.get("in_motion") or "").splitlines() if line.strip(" -*\t")],
            "text": note.body.strip() if note is not None else ""}


def _home(brain, who, purpose) -> tuple[str, str]:
    st = brain.state()
    for area, topic in HOMES:
        if area in st.config.areas:
            return area, topic
    chain = st.scopes.chain(who) or [who]
    return governance.personal_topic(brain, who) or governance.guess_placement(
        brain, purpose, chain)


def write(brain, answers, *, actor=None):
    """Set the brain's goals from the owner's answers: the note, one undo point."""
    from . import checkpoints
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    if not isinstance(answers, dict):
        return _result("Answers map a question to its answer.", {"status": "invalid"}, True)
    unknown = sorted(str(k) for k in answers if k not in BY_ID)
    if unknown:
        return _result(f"{', '.join(unknown)} is not one of the questions.",
                       {"status": "invalid"}, True)
    clean = {k: _clean(v) for k, v in answers.items() if _clean(v)}
    if not clean.get("purpose"):
        return _result("Say in a sentence or two what this Brain should help you do.",
                       {"status": "invalid", "field": "purpose"}, True)
    too_long = [k for k, v in clean.items()
                if len(v) > (MAX_PURPOSE if k == "purpose" else MAX_ANSWER)]
    if too_long:
        return _result(f"Keep the first answer under {MAX_PURPOSE} characters and each other "
                       f"under {MAX_ANSWER:,}.", {"status": "invalid", "field": too_long[0]},
                       True)
    text = compose(clean)
    summary = util.excerpt(clean["purpose"], 200)
    current = brain.state().index.note(GOALS_ID)
    if current is not None and util.canonical(current.body) == util.canonical(text):
        return _result("Your goals already say that.", dict(read(brain), status="unchanged"))
    day = util.today()
    with checkpoints.batch(brain, actor=who, label="Your goals for this Brain") as batch:
        with brain.deferring() as deferred:
            deferred.message = "Your goals for this Brain"
            if current is not None:
                done = governance.edit(brain, GOALS_ID, text, title=TITLE, summary=summary,
                                       reason="The owner changed their goals.", actor=who)
            else:
                area, topic = _home(brain, who, clean["purpose"])
                made = governance.propose_note(
                    brain, area=area, topic=topic, text=text, scope=who, load="on-demand",
                    principal=who, title=TITLE, summary=summary, note_kind="identity",
                    note_id=GOALS_ID, evidence=f"The owner's answers in the goals interview, "
                                               f"{day}.",
                    source=f"written by {who} in the goals interview",
                    reason="the owner's goals for the Brain", force_pending=True,
                    extra={"classification": "confidential"})
                if made.is_error:
                    return made
                done = governance.approve(brain, made.data["proposal_id"], actor=who)
            if done.is_error:
                return done
            batch.decisions.append({"action": "edited" if current is not None else "approved",
                                    "note": GOALS_ID, "title": TITLE})
    return _result("Your goals are saved.",
                   dict(read(brain), status="saved", checkpoint=batch.checkpoint))
