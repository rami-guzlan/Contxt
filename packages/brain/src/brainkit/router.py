"""Deterministic hybrid routing: from one request to an explainable plan of what to deliver.

The router never opens the packet budget and never renders text. It reads the request's
signals, scores what the caller is allowed to see, and returns a `Route` saying which Focus,
topics, notes, skills, references and system documents belong in the answer, and why.

HOW A REQUEST IS READ, in order of precedence:

    exact address    a note id or alias, `/skill`, or an exact skill name
    portfolio        "orient me", "what is active": the caller's Focus portfolio
    system           questions about this brain itself: engine documentation
    named Focus      a request that names one Focus: status, progress update, or work on it
    standard         topic and note relevance, skill candidates, house-style topics

EVIDENCE is BM25 over light-stemmed terms plus, when available, local embeddings. GOVERNED
CUES from the vault (`routing.json`) refine it: per-topic `requires_any` gates and
`fit_terms`, and declarative `intents` that include or exclude topics for a kind of request.
Nothing here names an organization, a product or a person; those live in the vault.

FOLLOW-UPS read the conversation. A request that leans on what came before ("it", "them",
"and which ...", "too", or a short question the brain finds nothing for on its own) is either
an EDIT of text the session already holds ("make the opening line punchier": only the house
style and what that text was built from) or a CONTINUATION that brings a new need ("bots are
filling it in too"): routed like any request, with the conversation's subject as context
(topic gates read it too), so it reaches notes the earlier packets never touched. Notes the
session already holds are not sent twice.

ADMISSION is not relevance. Every candidate was already filtered by scope, status and
partition before it was scored, so no score can widen what a caller may see.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, replace

from . import tension, util
from .index import MODEL_SCALES
from .scopes import Scopes


try:  # present wherever the meaning model runs (onnxruntime needs it); optional otherwise
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None


@dataclass(frozen=True)
class Policy:
    """Every threshold the router uses, in one place. Overridable in routing.json `policy`."""

    semantic_floor: float = 0.34          # cosine at which semantic evidence starts to count
    semantic_span: float = 0.42           # cosine span mapped onto 0..1
    semantic_weight: float = 0.5          # meaning's share of a note's relevance; words the rest
    # A strong match by meaning stands on its own: a note scores at least this share of its
    # meaning score, even when it shares no word with the request ("monthly recurring
    # revenue" and a note that says "MRR"). The meaning score is already capped by how far
    # the note stands out from the rest of the Brain for this request, so a Brain where
    # everything sounds alike does not flood briefs. 0 turns it off.
    semantic_alone: float = 0.7
    lean_floor: float = 0.46              # below this best relevance, deliver nothing
    # note selection (note-first)
    note_abs_floor: float = 0.42          # a note needs at least this ranking score
    select_relative: float = 0.72         # and this share of the best note's score
    micro_relative: float = 0.80          # one-answer lookups are stricter
    micro_max_notes: int = 6
    per_topic_micro: int = 5              # diversity: at most this many notes per topic
    per_topic_standard: int = 4
    per_topic_deep: int = 5
    related_factor: float = 0.80          # "also relevant" pointers down to this share
    related_count: int = 8
    topic_note_floor: float = 0.42        # a declared domain adds its best note only if this relevant
    # soft signals
    domain_boost: float = 0.05            # topic declared by the routed procedure, an intent, a Focus
    gate_factor: float = 0.65             # topic whose requires_any words are all missing
    gate_named: float = 0.6               # ...unless the request names the note: this share
                                          # of its weighted words, two or more, in the note
    fit_boost: float = 0.03               # per matching fit term, at most two
    fresh_days: int = 14                  # a note whose text is this new...
    fresh_boost: float = 0.05             # ...gets this lift
    rule_boost: float = 0.06              # "can I ...?": the rules that govern the action
    stale_factor: float = 0.75            # past its review: ranked lower, never removed
    disputed_factor: float = 0.85         # its confidence is disputed
    topic_prior: float = 0.15             # times how well the note's whole topic matches
    # Cross-encoder reranking of the best candidates. OFF by default: measured 2026-09-28
    # with Xenova/ms-marco-MiniLM-L-6-v2 on 22 held-out cases, it changed no needed-note
    # outcome and cost about 350 ms a request. Set rerank_weight (0.08) in routing.json
    # `policy` to try it, or another model, against the same evaluation.
    rerank_k: int = 15                    # how many of the best candidates it rereads
    rerank_weight: float = 0.0            # reorder shift per standard deviation of its verdict
    rerank_chars: int = 600               # how much of each note it reads
    # follow-ups, house style, standing answers
    note_floor: float = 0.30
    note_relative: float = 0.48           # follow-ups: floor relative to the best note
    subject_words: int = 60               # a conversation's subject: its last this-many words
    near_floor: float = 0.30              # nothing cleared the bar: still list notes this close
    near_count: int = 5
    orientation_notes: int = 4            # orientation: notes in full, one per area
    orientation_style: int = 3            # ...and core writing rules when they will write
    house_style_floor: float = 0.12
    style_relevance: float = 0.40         # house style order: this much request relevance,
                                          # the rest closeness to the topic line (core rules first)
    house_style_share: float = 0.45       # of the note budget, for the house-style rules
    standing_floor: float = 0.50
    standing_margin: float = 0.03
    standing_coverage: float = 0.5        # share of the request's words a standing answer uses,
                                          # unless no on-demand note comes near
    projects_compete: bool = True         # projects not named still compete on relevance
    # skills
    skill_floor: float = 0.55
    skill_window: float = 0.30            # candidates within this of the best are listed
    credible_window: float = 0.10         # candidates whose loads become domains
    executable_floor: float = 0.85
    decisive_margin: float = 0.15
    max_candidates: int = 3
    focus_distinct_min_len: int = 4
    # sections of filed documents, quoted when they answer the request (sections.py)
    section_floor: float = 0.50           # a section needs this relevance
    section_relative: float = 0.85        # and this share of the best section's
    max_sections: int = 3
    max_sections_per_file: int = 2
    section_tokens: int = 900             # quoted file text per packet, at most
    section_tokens_micro: int = 600       # ...for a one-answer lookup
    section_tokens_deep: int = 1400       # ...for deep work
    project_file_boost: float = 0.08      # sections of the files of the project it names
    # must-holds: constraints that go in whenever their domain is in play (see MUST-HOLDS)
    must_hold_max: int = 8                # shown in a brief; the rest are listed by title
    # The request's best topic puts its area in play at this relevance, the second best at
    # the stricter bar. Set from the tuning requests and decoys in tests/evals/must_holds.json
    # (October 8, 2026): a domain's tuning requests put its topic first at 0.21 to 0.90; one
    # decoy put a domain first (0.58, already reached by its route), one second (0.31).
    must_hold_topic_bar: float = 0.25
    must_hold_second_bar: float = 0.35
    # With an embedding model, a request this close in meaning (on the model's 0..1 scale) to
    # a must-hold's domain passage puts it in play. 0.57 is raw cosine 0.58 on bge-small:
    # half the tuning requests clear it, no decoy and 3% of other must-holds' requests do.
    must_hold_semantic_bar: float = 0.57
    # CALIBRATED BARS (calibration.py): the share of the Brain's unrelated requests a match
    # must beat. They stand in for lean_floor, note_abs_floor and topic_note_floor, each
    # unless routing.json `policy` sets it by hand. Set on the
    # generated tuning Brains (October 16, 2026): at 0.95 by meaning, 99% of real requests
    # kept something and 96% of off-topic ones got nothing.
    calibrated: bool = True
    nothing_share: float = 0.95           # the best note must beat this, or nothing is sent
    note_share: float = 0.95              # a note is sent only when its own match beats this
    related_share: float = 0.90           # ...and listed as also relevant when it beats this
    # THREE TIERS (plan 3.4), with calibrated bars: a note goes whole only within this share
    # of the best note's score; the next ones that clear related_share are pointers, at most
    # related_count. On the generated tuning Brains (October 16, 2026): needed notes sit at
    # rank 1 for 45% of needs, in the top 3 for 74% and the top 8 for 89%, so whole notes
    # within 0.90 of the best (69% precision) and pointers to rank 8 reach what is needed.
    whole_relative: float = 0.90
    # Without an embedding model the evidence is words only, which cannot tell a short real
    # request that hits one rare word from an unrelated one that does the same: on a small
    # Brain most unrelated requests match no word at all, so any one shared word clears a
    # bar. Words-only Brains keep the floors above unless `calibrated_words` is set; its
    # bars are lower (at 0.85, 98% of real requests kept something and 80% of off-topic
    # ones got nothing on the generated tuning Brains, but short real requests on the demo
    # Brains lost their notes).
    calibrated_words: bool = False
    words_nothing_share: float = 0.85
    words_note_share: float = 0.85
    words_related_share: float = 0.75

    @classmethod
    def from_config(cls, data: dict | None):
        values = {}
        names = {f.name for f in fields(cls)}
        for key, value in (data or {}).items():
            if key in names:
                values[key] = type(getattr(cls, key))(value)
        return cls(**values)


# ------------------------------------------------------------------ generic cue vocabulary

QUESTION_START = re.compile(
    r"^\s*(what|why|who|whom|whose|which|when|where|how|does|do|did|is|are|was|were|"
    r"can you tell|can i|can we|could i|may i|should i|should we|will|would|explain|"
    r"tell me|remind me|show me|give me (?:the )?(?:latest |current )?status)\b")
CLASSIFY_VERBS = (
    "create", "build", "write", "draft", "edit", "make", "produce", "design", "update",
    "publish", "generate", "format", "implement", "turn", "develop", "perform", "record",
    "revise", "rewrite", "tighten", "sharpen", "prepare", "compose",
)
KNOWLEDGE_WORDS = (
    "what", "why", "explain", "tell me", "summarize", "status", "which", "find", "research",
    "compare", "know", "information", "show", "list", "retrieve",
)
OPERATIONAL_WORDS = ("restart", "restarts", "relaunch", "reload", "reinstall", "install",
                     "configure", "deploy", "reboot")
ARTIFACT_TERMS = frozenset({
    "post", "pdf", "docx", "deck", "outline", "infographic", "guide", "report", "video",
    "cover", "email", "proposal", "calendar", "brochure", "blurb", "copy", "sentence",
    "sentences", "paragraph", "audit", "plan", "document", "slide", "slides", "presentation",
    "article", "blog", "memo", "spec", "letter", "newsletter", "script", "carousel", "pptx",
})
GENERIC_SKILL_WORDS = frozenset({"builder", "creator", "manager", "maker", "generator", "tool",
                                 "skill", "studio", "helper", "writer", "pdf", "the", "and"})
SHORT_FORM_TERMS = frozenset({"blurb", "sentence", "sentences", "line", "lines", "tagline",
                              "headline", "caption"})
EDIT_START = re.compile(
    r"^\s*(?:please\s+)?(?:now\s+)?(?:make|tighten|sharpen|shorten|expand|rewrite|revise|keep|"
    r"change|fix|tweak|adjust|polish|simplify|rephrase|edit|cut|trim|drop|swap|try|redo|"
    r"soften|punch|lengthen)\b")
ANAPHORA = frozenset({"that", "it", "this", "those", "these", "them"})
# A request that continues the conversation without restating its subject.
CONTINUATION_START = re.compile(
    r"^\s*(?:and|also|plus|then|now|so|ok|okay|but|what about|how about)\b")
CONTINUATION_WORDS = frozenset({"too", "also", "either", "instead"})
# Words that say HOW text should change, not what it is about. An edit made only of these
# (and of words the conversation already used) needs nothing new from the brain.
EDIT_VOCABULARY = frozenset({
    "make", "keep", "change", "fix", "tweak", "adjust", "polish", "simplify", "rephrase",
    "reword", "edit", "cut", "trim", "drop", "swap", "try", "redo", "soften", "punch",
    "lengthen", "tighten", "sharpen", "shorten", "expand", "rewrite", "revise", "add",
    "remove", "line", "lines", "sentence", "sentences", "paragraph", "paragraphs", "opening",
    "opener", "intro", "introduction", "close", "closing", "ending", "end", "hook",
    "headline", "title", "subtitle", "word", "words", "wording", "phrase", "phrasing", "tone",
    "rhythm", "flow", "length", "version", "draft", "copy", "text", "bit", "part", "section",
    "point", "points", "bullet", "bullets", "list", "format", "formatting", "structure",
    "emoji", "emojis", "hashtag", "hashtags", "punctuation", "transition", "transitions",
    "substance", "first", "second", "third", "last", "final", "top", "bottom", "middle",
    "start", "beginning", "one", "two", "three", "more", "less", "little", "slightly", "much",
    "lot", "again", "whole", "entire", "overall", "short", "shorter", "long", "longer",
    "punchy", "punchier", "tight", "tighter", "clear", "clearer", "simple", "simpler",
    "direct", "warm", "warmer", "formal", "casual", "friendly", "friendlier", "bold",
    "bolder", "soft", "softer", "strong", "stronger", "crisp", "crisper", "concise", "sharp",
    "sharper", "natural", "smooth", "smoother", "lively", "engaging", "catchy", "catchier",
    "concrete", "specific", "personal", "conversational", "professional", "confident",
    "positive", "upbeat", "energetic", "readable", "plain", "fluff", "wordy", "awkward",
    "repetitive", "sound", "sounds", "read", "reads", "feel", "feels", "better", "good",
    # parts of a document an edit names ("make the summary warmer")
    "summary", "abstract", "body", "conclusion", "caption", "captions", "slide", "slides",
    "cta", "ctas", "signoff",
})
# Parts of a document named in more than one word. Each counts whole, so "make the executive
# summary warmer" is an edit while "executive program" stays what a request is about.
EDIT_PHRASES = ("executive summary", "call to action", "calls to action", "subject line",
                "subject lines", "sign off", "bullet points", "bullet point")
# Verbs that ask for text to be written or changed; and verbs that make an artifact.
WRITING_VERBS = frozenset({"write", "draft", "rewrite", "revise", "compose", "tighten",
                           "sharpen", "edit", "polish", "shorten", "proofread", "reword",
                           "rephrase", "redraft"})
PRODUCTION_VERBS = WRITING_VERBS | frozenset({
    "create", "build", "make", "produce", "design", "update", "generate", "format", "turn",
    "develop", "prepare", "plan", "outline", "sketch", "brainstorm", "adapt", "redo"})
# "Can I add a script to the site?", "is it okay to mention them?": whether an action is
# allowed, which the rules governing it answer.
ASKS_ALLOWED = re.compile(
    r"^\s*(?:can|may|could|should)\s+(?:i|we)\b|\b(?:is it|is that|would it be)\s+"
    r"(?:ok|okay|fine|allowed|alright|safe|acceptable)\b|\b(?:am i|are we)\s+allowed\b|"
    r"\ballowed to\b")
# A question about how to write rather than what to write about: "what should I avoid
# saying in community posts?", "how do I keep my post from sounding robotic?".
STYLE_QUESTION_WORDS = frozenset({
    "say", "saying", "write", "writing", "word", "words", "wording", "phrase", "phrases",
    "phrasing", "tone", "voice", "sound", "sounds", "sounding", "language", "jargon",
    "cliche", "cliches", "describe"})
# A note that names another note in a sentence like this says the two disagree.
LINK_CONFLICT = re.compile(r"\b(?:contradict\w*|conflict\w*|clash\w*|disagree\w*|"
                           r"inconsistent|differ\w*|instead of)\b")
WANT_FRAME = re.compile(r"\b(?:need|want|would like|'d like)\s+(?:an?|the|some|one|two|three|"
                        r"a few|new|our|my)\b")
FOCUS_UPDATE_PHRASES = (
    "approved the", "accepted the", "is approved", "is reviewing", "for review",
    "record that", "record an update", "progress update", "signed off", "now has",
    "has been approved", "went live", "is now live", "was sent", "have sent", "we sent",
    "just finished", "we finished", "is complete", "is done", "shipped",
)
STATUS_PHRASES = ("where are we", "where does", "what is live", "what's live", "how is",
                  "how's", "latest on", "status of", "update on", "state of")
STATUS_WORDS = frozenset({"status", "latest", "progress", "blocker", "blockers", "current",
                          "standing", "stand", "state", "next", "update", "updates"})
FOCUS_CUE_WORDS = frozenset({"project", "status", "latest", "blocker", "blockers", "progress",
                             "stand", "standing", "current", "approved", "reviewing", "continue",
                             "next", "update", "record", "accepted"})
FOCUS_GENERIC = frozenset({
    "active", "blocked", "closed", "complete", "completed", "current", "delivered", "project",
    "projects", "focus", "focuses", "proposal", "proposals", "program", "programs", "status",
    "state", "work", "working", "latest", "update", "updates", "initiative", "approved",
    "review", "reviewed", "reviewing", "outline", "visual", "visuals", "pass", "plan", "done",
    "next", "section", "draft", "version", "final", "phase",
})
PORTFOLIO_PHRASES = ("up to speed", "orient me", "orientation", "what is active",
                     "what's active", "what am i working on", "what are we working on",
                     "active focus", "focus items", "active focuses", "active projects",
                     "open work", "my focuses", "all focuses", "focus portfolio")
# Someone new, or anyone, asking for the lay of the land rather than one thing in it.
NEWCOMER = re.compile(
    r"\b(?:i'?m new|i am new|just joined|new here|new to (?:the team|this|the company)|"
    r"my first (?:day|week)|lay of the land|(?:quick |a )?tour of|give me a tour|onboard me|"
    r"what (?:do|should) i (?:need to )?know (?:before (?:i start|getting started)|"
    r"about (?:us|this|the company|the team)|"
    r"here)|what (?:do )?you know about (?:us|me|this)|walk me through what you know)\b")
# "Get me up to speed" and "orient me" stay the owner's portfolio of active work.
SYSTEM_PHRASES = (
    "this brain", "brain system", "brain architecture", "context packet", "task packet",
    "startup context", "context retrieval", "packet retrieval", "context router",
    "brain mcp", "mcp server", "mcp connection", "routing gap", "routing precision",
    "retrieval quality", "retrieval architecture", "retrieval flow", "retrieval boundaries",
    "write boundaries", "brain context", "brain engine", "the kernel",
)
SYSTEM_WORDS = frozenset({"routing", "mcp"})
SYSTEM_TERMS = frozenset({"architecture", "retrieval", "routing", "router", "context",
                          "packet", "packets", "mcp", "index", "dashboard", "boundary",
                          "boundaries", "kernel", "vault", "governance", "engine"})
PERMISSION_ACTION = re.compile(
    r"\b(send|publish|post|share|release|put live|go live|launch|submit|email)\b")
FULL_SOURCE = re.compile(
    r"\b(full|complete|entire|whole|original)\b.*\b(guide|source|doc|document|reference|"
    r"spec|playbook|manual|handbook|voice)\b|\b(guide|voice)\b.*\b(source|full|complete|"
    r"entire)\b")
# A filed document marked as no longer current is history, not context: its sections are not
# quoted (its card says what replaced it).
RETIRED_FILE_STATES = frozenset({"superseded", "retired", "withdrawn", "archived"})
# MEANING DECIDES which parts of files are quoted. With the embedding model, a section is
# quoted when what it says is close to what the request asks (`semantic`: its similarity,
# capped by how far it stands out from every other section for this request), whatever words
# the two share. Measured 2026-10-06 on 25 labeled cases over a real brain with an invented
# campaign project: meaning found the right part for 13 of 15 questions asked in a person's
# own words, word rules for 9, and a cross-encoder reader did worse than both at every bar.
# A WORK FILE (filed as `type: file`: a proposal, a brief, notes from a meeting) is quoted at
# a moderate match. A GUIDE kept whole (a reference filed before cards had a type: a brand
# guide, a playbook) mostly says what the notes distilled from it already say, so it needs a
# very strong one, and a writing task gets none unless it names the guide: the house-style
# notes are the guide's rules already (measured on a real brain's benchmark: at 0.80, 29 of 68
# requests got guide text, mostly style templates for writing tasks). A request that names
# the file or its project lowers either bar a little.
SECTION_SEMANTIC = 0.60
GUIDE_SEMANTIC = 0.90
# How far each named retrieval policy moves the calibrated bars (the share of a Brain's
# unrelated requests a match must beat): careful sends less and says "nothing" more often,
# relaxed sends more. Standard is the measured default.
NAMED_POLICIES = {"relaxed": -0.03, "standard": 0.0, "careful": 0.02}
NAMED_RELIEF = 0.10
# A REQUEST NOTHING ELSE BACKS (no note, file card, project or procedure is about it: the
# weather, a recipe) gets a file part only when the request names the file or the part is
# this close. A long conversational file has a part that sounds like almost anything: in a
# real meeting transcript, a passing plan to pick something up tomorrow matched "tell me the
# weather forecast for tomorrow" at 0.69. Measured 2026-10-06: everyday requests reached at most
# 0.73 that way; the one question about a file no note backed scored 0.86 and named its file.
UNBACKED_SEMANTIC = 0.80
# Without the embedding model, words are all there is: the share of the request's
# (idf-weighted) words a section holds, read with its file's title.
SECTION_COVERAGE_ALONE = 0.65
SECTION_COVERAGE_NAMED = 0.35
GUIDE_LEXICAL = 0.80
# Where a joined name in a file title splits ("LenaMeeting": "Lena", "Meeting"). "LinkedIn"
# and "HubSpot" stay whole words too; their parts only add ways to name the file.
JOINED = re.compile(r"(?<=[a-z])(?=[A-Z][a-z])")
# A date or a version in a title ("transcript (2026-09-29)", "proposal v2") names no file.
TITLE_NUMBER = re.compile(r"v?\d+")
# Words a file title shares with many files say nothing about which file a request means.
GENERIC_FILE_WORDS = frozenset({"file", "files", "doc", "docs", "document", "documents",
                                "note", "notes", "draft", "final", "copy", "version",
                                "untitled", "new", "template", "update", "updated"})
DEEP_PHRASES = ("full report", "full proposal", "deep dive", "deep audit", "detailed analysis",
                "complete audit", "implementation plan", "development plan", "end to end",
                "end-to-end", "in depth", "in-depth", "comprehensive")
DEEP_BUILD = re.compile(r"\b(build|create|produce|draft|write)\b.*\b(full|complete|entire)\b"
                        r".*\b(guide|report|proposal|audit|document|deck|plan)\b")


def _phrase(text_norm, phrase) -> bool:
    return util.phrase_in(phrase, text_norm)


def _answers_alone(scored) -> bool:
    """A file part strong enough to stand without any other evidence that the request is about
    the work: its file is named, or it matches very closely (by meaning, or by words when there
    is no embedding model)."""
    detail = scored.detail
    if detail.get("named"):
        return True
    semantic = detail.get("semantic")
    if semantic is not None:
        return semantic >= UNBACKED_SEMANTIC
    return detail.get("coverage", 0.0) >= GUIDE_LEXICAL


def _hint_hits(request_words, request_norm, values) -> int:
    hits = 0
    for value in values or []:
        value = str(value).lower().strip()
        if not value:
            continue
        if " " in value or "-" in value:
            if _phrase(request_norm, value):
                hits += 1
        elif value in request_words:
            hits += 1
    return hits


@dataclass
class Signals:
    request: str
    text: str
    norm: str
    words: list
    wordset: set
    question: bool = False
    imperative: bool = False
    permission: bool = False
    focus_update: bool = False
    status_cue: bool = False
    work_cue: bool = False
    portfolio: bool = False
    system: bool = False
    full_source: bool = False
    short_form: bool = False
    deep: bool = False
    artifacts: set = field(default_factory=set)
    task_type: str = "combined"
    task_reason: str = ""
    scale: str = "standard"
    scale_reason: str = ""
    intents: list = field(default_factory=list)
    include_topics: list = field(default_factory=list)
    exclude_topics: list = field(default_factory=list)
    only_topics: list | None = None
    include_notes: list = field(default_factory=list)
    note_budget: int | None = None
    no_skill: bool = False
    no_house_style: bool = False
    followup: bool = False
    followup_kind: str = ""          # "edit" or "continuation" when followup
    subject: str = ""                # what the conversation is about, for a follow-up
    produces: bool = False           # the request asks for an artifact to be made
    asks_allowed: bool = False       # whether an action is allowed
    style_question: bool = False     # how to write, not what to write about
    artifact_at: int | None = None   # position of the first artifact word
    inherited_composing: bool = False
    orientation: bool = False        # someone new asking what the brain knows

    @property
    def edit(self) -> bool:
        return self.followup and self.followup_kind == "edit"

    @property
    def continuation(self) -> bool:
        return self.followup and self.followup_kind == "continuation"

    @property
    def composing(self) -> bool:
        """Does this request produce (or change) text someone will read?

        A writing verb or a short-form artifact says so, and so does an artifact the request
        asks to have made ("a LinkedIn post about ...", "create a deck"). An artifact word
        alone does not: "we boosted a post, is that good?" and "add a script to the site"
        are about something else. A continuation of a writing task keeps writing."""
        if self.task_type not in ("combined", "workflow") or self.permission:
            return False
        if self.inherited_composing or self.short_form or self.wordset & WRITING_VERBS:
            return True
        return bool(self.artifacts) and self.produces


def _intent_matches(rule: dict, sig: Signals) -> bool:
    """Does one declarative intent rule from routing.json match this request?

    `match` keys, all optional:
        any_phrases / any_terms / regex   at least one of the given alternatives appears
        all_terms                         every listed word appears
        all_of                            a list of word groups; each group needs one hit
        none_phrases / none_terms / none_regex   any hit rejects the rule
        max_terms                         reject longer requests
    `when_not` lists signal flags (for example "permission") that must be false.
    """
    match = rule.get("match") or {}
    words, norm, text = sig.wordset, sig.norm, sig.text
    for flag in rule.get("when_not") or []:
        if getattr(sig, str(flag), False):
            return False
    alternatives = (match.get("any_phrases"), match.get("any_terms"), match.get("regex"))
    if any(alternatives):
        hit = (any(_phrase(norm, p) for p in match.get("any_phrases") or [])
               or bool(words & {t.lower() for t in match.get("any_terms") or []})
               or any(re.search(r, text) for r in match.get("regex") or []))
        if not hit:
            return False
    elif not (match.get("all_terms") or match.get("all_of")):
        return False
    if not {t.lower() for t in match.get("all_terms") or []} <= words:
        return False
    for group in match.get("all_of") or []:
        if not words & {t.lower() for t in group}:
            return False
    if any(_phrase(norm, p) for p in match.get("none_phrases") or []):
        return False
    if words & {t.lower() for t in match.get("none_terms") or []}:
        return False
    if any(re.search(r, text) for r in match.get("none_regex") or []):
        return False
    max_terms = match.get("max_terms")
    return max_terms is None or len(sig.words) <= int(max_terms)


def analyze(request: str, routing, overrides=None) -> Signals:
    """Read the request once. Everything below decides from these signals."""
    # Multiword terms read as one word: "add a call to action" asks for a "cta".
    folded = util.phrase_folder(getattr(routing, "phrases", None))(str(request or ""))
    text = " ".join(folded.lower().split())
    norm = util.normalize(folded)
    words = util.terms(folded)
    wordset = set(words)
    sig = Signals(request=str(request or ""), text=text, norm=norm, words=words,
                  wordset=wordset)
    sig.question = bool(QUESTION_START.match(text))
    sig.imperative = bool(re.match(r"\s*(please\s+)?(" + "|".join(CLASSIFY_VERBS) + r")\b",
                                   text))
    sig.permission = _is_permission(text)
    sig.status_cue = any(p in text for p in STATUS_PHRASES) or bool(wordset & STATUS_WORDS)
    sig.work_cue = bool(wordset & FOCUS_CUE_WORDS)
    artifact_terms = ARTIFACT_TERMS | {t.lower() for t in routing.artifact_terms}
    # "posts" and "emails" are artifacts too: words are matched on their stems and recorded
    # as the vocabulary's own term, so skills that declare "post" still match.
    by_stem = {util.stem(term): term for term in artifact_terms}
    for position, word in enumerate(words):
        term = word if word in artifact_terms else by_stem.get(util.stem(word))
        if term:
            sig.artifacts.add(term)
            if sig.artifact_at is None:
                sig.artifact_at = position
    sig.short_form = len(words) <= 24 and (
        bool(wordset & SHORT_FORM_TERMS)
        or any(_phrase(norm, p) for p in ("two sentences", "one line", "two lines",
                                          "one sentence", "short note", "quick note")))
    sig.produces = _produces(sig)
    sig.focus_update = _reports_progress(sig)
    sig.asks_allowed = bool(ASKS_ALLOWED.search(text))
    sig.style_question = bool((sig.question or "?" in text) and wordset & STYLE_QUESTION_WORDS
                              and sig.artifacts)
    sig.portfolio = _is_portfolio(text, norm, wordset)
    # An onboarding topic or a newcomer introduction must not replace a concrete
    # creation task with a general map of the Brain.
    # The expression is natural language and needs single-letter pronouns and apostrophes;
    # the search-normalized text intentionally removes them.
    sig.orientation = not sig.produces and bool(NEWCOMER.search(text))
    system_phrases = SYSTEM_PHRASES + tuple(routing.system_phrases)
    sig.system = (not sig.portfolio) and (
        any(_phrase(norm, p) for p in system_phrases)
        or bool(wordset & SYSTEM_WORDS)
        or ("brain" in wordset and bool(wordset & SYSTEM_TERMS)))
    sig.full_source = bool(FULL_SOURCE.search(text)) and not DEEP_BUILD.search(text) and bool(
        re.search(r"\b(use|using|apply|applying|per|follow|following|according|against|read|"
                  r"reading|consult|check)\b", text))
    sig.deep = _is_deep(text, norm, words)

    for rule in routing.intents:
        if _intent_matches(rule, sig):
            sig.intents.append(str(rule.get("id") or "intent"))
            effect = rule.get("set") or {}
            for key in ("permission", "focus_update", "portfolio", "system", "full_source",
                        "short_form", "deep"):
                if key in effect:
                    setattr(sig, key, bool(effect[key]))
            sig.include_topics += [t for t in rule.get("include_topics") or []]
            sig.exclude_topics += [t for t in rule.get("exclude_topics") or []]
            if rule.get("only_topics"):
                allowed = [t for t in rule["only_topics"]]
                sig.only_topics = allowed if sig.only_topics is None else [
                    t for t in sig.only_topics if t in allowed]
            sig.include_notes += [n for n in rule.get("include_notes") or []]
            if rule.get("note_budget"):
                sig.note_budget = int(rule["note_budget"])
            if rule.get("no_skill"):
                sig.no_skill = True
            if rule.get("no_house_style"):
                sig.no_house_style = True
            if effect.get("task_type"):
                sig.task_type, sig.task_reason = effect["task_type"], f"intent {rule.get('id')}"
            if effect.get("scale"):
                sig.scale, sig.scale_reason = effect["scale"], f"intent {rule.get('id')}"

    overrides = overrides or {}
    fixed_type = sig.task_reason.startswith("intent ")
    fixed_scale = sig.scale_reason.startswith("intent ")
    if overrides.get("task_type"):
        value = str(overrides["task_type"]).lower()
        sig.task_type = "combined" if value == "both" else value
        sig.task_reason = "explicit override"
    elif not fixed_type:
        sig.task_type, sig.task_reason = _classify(sig)
    if not fixed_scale:
        sig.scale, sig.scale_reason = _scale(sig)
    return sig


def _reports_progress(sig: Signals) -> bool:
    """Progress wording in a question or requested artifact is not a new update.

    An explicit recording instruction still counts, including a polite question such
    as "Could you record that ...?". Matching a quoted approval phrase alone does not.
    """
    if re.search(r"(?:^|[.!?;,]\s*)(?:please\s+)?(?:(?:can|could|would|will)\s+"
                 r"(?:you|we)\s+)?(?:please\s+)?record\s+(?:that|an? update)\b", sig.text):
        return True
    reading = re.match(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?"
                       r"(?:please\s+)?(?:explain|tell|remind|show|give|find|retrieve|"
                       r"list|summarize|describe)\b", sig.text)
    work = re.match(r"^(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?"
                    r"(?:please\s+)?(?:" + "|".join(sorted(PRODUCTION_VERBS)) + r")\b", sig.text)
    # A noun at the start can make _produces true ("the report is complete"). A
    # progress report needs no new artifact merely because it names an existing one.
    if sig.question or "?" in sig.text or reading or work or sig.imperative \
            or WANT_FRAME.search(sig.text):
        return False
    return any(_phrase(sig.norm, phrase) for phrase in FOCUS_UPDATE_PHRASES)


def _focus_overview(sig: Signals, focus) -> bool:
    """Only a general project overview can skip ordinary knowledge retrieval.

    A status cue like "current" also occurs in questions about specific facts. Remove
    only the project's names, not its body, before checking for those extra subjects.
    """
    if not sig.status_cue and not re.match(r"^what(?: is|\'s) left|^what remains", sig.text):
        return False
    names = set(util.terms(" ".join([focus.id, focus.slug, focus.title] + focus.aliases)))
    overview = {"where", "how", "what", "whats", "hows", "are", "is", "we", "it", "with",
                "does", "the", "this", "that", "our", "my", "on", "of", "for", "about",
                "please", "can", "could", "would", "you", "me", "tell", "give", "show",
                "get", "bring", "up", "to", "speed", "a", "an", "and", "in", "project",
                "going", "doing", "overview", "summary", "overall", "steps", "actions",
                "left", "before", "remains"}
    return not (sig.wordset - names - overview - STATUS_WORDS)


def _produces(sig: Signals) -> bool:
    """Does the request ask for one of its artifacts to be made, rather than mention one?

    Yes when a verb that makes something comes before the first artifact word ("can you
    create a carousel cover?"), when the request opens with the artifact ("LinkedIn post
    about ..."), or when it says it needs one ("I need a one-pager on ..."). A question with
    no such verb ("we boosted a post; is that good?") is about something else."""
    first = sig.artifact_at
    if not sig.artifacts or first is None:
        return False
    if set(sig.words[:first]) & PRODUCTION_VERBS:
        return True
    if sig.question or "?" in sig.text:
        return False
    return first <= 3 or bool(WANT_FRAME.search(sig.text))


_ACT = r"(?:send|publish|post|share|release|launch|submit|email|put\b.{0,40}\blive|go live)"
_SOFT = r"(?:just\s+|now\s+|already\s+|go ahead and\s+|safely\s+)?"


def _is_permission(text: str) -> bool:
    """A question about whether an outward action may happen now ("can I publish this?").
    The action must be the verb asked about: "can we put budget behind the post?" asks about
    budget, not about posting, and gets knowledge, not only the approval rules."""
    if not PERMISSION_ACTION.search(text):
        return False
    return bool(
        re.match(r"\s*(?:can|may|should|could)\s+(?:i|we)\s+" + _SOFT + _ACT + r"\b", text)
        or re.match(r"\s*is\s+(?:this|it)\b.*\b(?:ready|approved|safe|ok|okay|fine)\b"
                    r"(?:\s+(?:to|for)\s+" + _ACT + r"\b|\s*\??\s*$)", text)
        or re.match(r"\s*am\s+i\s+(?:allowed|cleared)\s+to\s+" + _ACT + r"\b", text)
        or re.search(r"\b(?:need|needs|require|requires)\b.*\b(?:approval|approve|sign[- ]off)\b",
                     text))


def _is_portfolio(text, norm, wordset) -> bool:
    """Orientation or the list of active work. Needs context, so "list the Focus items
    private to Sam" is a lookup, not the caller's own portfolio."""
    context = wordset & {"brain", "active", "my", "current", "open", "everything", "workspace"}
    for phrase in PORTFOLIO_PHRASES:
        if not _phrase(norm, phrase):
            continue
        if phrase in ("what is active", "what's active", "what am i working on",
                      "what are we working on", "active focus", "active focuses",
                      "active projects", "my focuses", "focus portfolio"):
            return True
        if context - set(util.terms(phrase)):
            return True
    return False


def _is_deep(text, norm, words) -> bool:
    if any(_phrase(norm, p) if " " in p and "-" not in p else p in text for p in DEEP_PHRASES):
        return True
    if DEEP_BUILD.search(text):
        return True
    if re.match(r"\s*(?:please\s+)?(?:audit|perform an? (?:full |deep )?audit)\b", text):
        return True
    return len(words) >= 45


def _classify(sig: Signals) -> tuple[str, str]:
    text = sig.text
    if sig.portfolio:
        return "knowledge", "orientation asks for the Focus portfolio"
    if sig.permission:
        return "workflow", "permission to act externally"
    if sig.focus_update:
        return "workflow", "Focus progress statement"
    workflow = sum(1 for verb in CLASSIFY_VERBS if re.search(rf"\b{verb}\b", text))
    knowledge = sum(1 for word in KNOWLEDGE_WORDS if word in text)
    if sig.short_form and re.search(r"\b(write|describe|explain|give|create)\b", text):
        return "combined", "short artifact needs governed knowledge"
    if re.search(r"\bhow\s+(?:should|do|can)\s+(?:i|we)\s+(?:restart|relaunch|reload|install|"
                 r"run|configure|deploy)", text):
        return "workflow", "operational how-to"
    if sig.question and any(re.search(rf"\b{w}\b", text) for w in OPERATIONAL_WORDS):
        return "workflow", "operational question"
    if sig.question and not sig.imperative:
        return "knowledge", "question"
    if workflow and knowledge:
        return "combined", "action plus knowledge"
    if workflow and sig.artifacts:
        return "combined", "artifact work needs governed knowledge"
    if workflow:
        return "workflow", "action"
    if knowledge:
        return "knowledge", "knowledge words"
    return "combined", "ambiguous defaults to combined"


def _scale(sig: Signals) -> tuple[str, str]:
    words = sig.words
    if sig.focus_update:
        return "micro", "Focus progress update"
    if sig.short_form and len(words) <= 24:
        return "micro", "short-form artifact"
    if sig.permission or sig.task_reason.startswith("operational"):
        return "micro", "operational question"
    if sig.deep:
        return "deep", "explicit extensive work"
    if sig.artifacts or re.search(r"\b(?:rewrite|revise|revising|rewriting)\b", sig.text):
        return "standard", "artifact or multi-source work"
    if sig.composing:
        return "standard", "writing task"
    if len(words) <= 18:
        return "micro", "short request"
    return "standard", "ordinary multi-source work"


# ------------------------------------------------------------------ the route


@dataclass
class Scored:
    item: object
    score: float
    reasons: list = field(default_factory=list)
    detail: dict = field(default_factory=dict)


@dataclass
class MustHold:
    """A must-hold in play for a request: the note, why its domain is in play, and why it is
    stale when it is (a stale must-hold still goes in, flagged)."""
    note: object
    why: str
    stale: str | None = None


@dataclass
class Route:
    request: str
    chain: list
    partitions: list
    signals: Signals
    mode: str = "standard"
    task_type: str = "combined"
    scale: str = "standard"
    procedure: str = "none"                     # none | candidate | executable
    focus: object = None
    focus_mode: str = "no-focus"
    skill: object = None
    candidates: list = field(default_factory=list)     # [Scored(skill)]
    topics: list = field(default_factory=list)         # selected topic keys, in order
    forced_topics: list = field(default_factory=list)
    notes: list = field(default_factory=list)          # [Scored(note)] selected, in order
    style_notes: list = field(default_factory=list)    # [Scored(note)] house-style rules
    related: list = field(default_factory=list)        # [Scored(note)] listed, not sent
    related_pool: list = field(default_factory=list)   # qualified overflow for unused slots
    standing_answer: list = field(default_factory=list)  # [Scored(note)]
    references: list = field(default_factory=list)     # reference paths
    sections: list = field(default_factory=list)       # [Scored(section)] quoted from files
    system_docs: list = field(default_factory=list)    # [Scored(doc)]
    portfolio: list = field(default_factory=list)      # [Focus]
    excluded_topics: list = field(default_factory=list)
    notes_log: list = field(default_factory=list)      # human-readable decisions
    confidence: float = 0.0
    select_threshold: float = 0.0      # the bar the selected notes cleared
    policy: object = None
    previous: dict = field(default_factory=dict)
    subject: str = ""                                 # what the conversation is about now
    draft: str = ""                                   # the request that started its draft
    pointed_files: list = field(default_factory=list)  # files matched, not quoted: listed
    orientation: list = field(default_factory=list)   # the area map, for orientation
    must_holds: list = field(default_factory=list)    # [MustHold] in play, shown in full
    must_overflow: list = field(default_factory=list)  # [MustHold] past the cap: listed
    older: list = field(default_factory=list)         # [(older note, newer note)]: listed
    # Notes filed with another project than the one this request names: out of its scope.
    out_of_project: set = field(default_factory=set)
    focus_reason: str = ""             # why find_focus chose the Focus
    # {note id: the note it conflicts with}: two values for one thing on the same date.
    conflicts: dict = field(default_factory=dict)
    # Every on-demand note scored for the request, best first: what the engine's fallback
    # audit writes down. Routing never reads it.
    ranked: list = field(default_factory=list)
    # Set only by the local retrieval engine (engine.py): {item id: "body" | "pointer"} for
    # what survived its cut, and {note id: the note it is disputed with}.
    engine_fit: dict | None = None
    engine_disputed: dict = field(default_factory=dict)

    def log(self, message):
        self.notes_log.append(message)


class Router:
    def __init__(self, index, config, scopes: Scopes, system_docs=None, reranker=None):
        self.index = index
        self.reranker = reranker
        self.config = config
        self.scopes = scopes
        self.system_docs = list(system_docs or [])
        routing = config.routing
        self.policy = Policy.from_config(routing.policy)
        embedder = getattr(index, "embedder", None)
        scale = MODEL_SCALES.get(getattr(embedder, "model_name", "") or "")
        overrides = routing.policy or {}
        if scale and "semantic_floor" not in overrides and "semantic_span" not in overrides:
            # Each model spreads similarity its own way; its measured scale applies unless
            # the vault sets one.
            self.policy = replace(self.policy, semantic_floor=scale[0], semantic_span=scale[1])
        self.house_style = list(routing.house_style_topics)
        self.permission_topics = list(routing.permission_topics)
        self.system_skill = routing.system_skill
        self._sims: dict[str, dict] = {}
        self._focus_terms_cache: dict[str, set] = {}
        self._project_members: dict[str, set[str]] = {}
        self._hand = set(overrides) & {"lean_floor", "note_abs_floor", "topic_note_floor"}
        self._calibration = None
        self._facts: dict = {}
        self._hybrids: dict = {}
        self._admitted: dict = {}
        self._facts_day = None

    # ------------------------------------------------------------------ calibration
    def calibrated(self, floor: str) -> bool:
        """Does this floor come from the Brain's calibration (not set by hand)?"""
        if not self.policy.calibrated or floor in self._hand:
            return False
        return self.policy.calibrated_words or self.index.semantic_ready()

    @property
    def calibration(self):
        if self._calibration is None:
            from . import calibration
            cards = {c.id for c in self.index.cards.values()}
            notes = [n.id for n in self.index.notes.values()
                     if not n.standing and n.id not in cards]
            domains = [n.id for n in self.index.notes.values() if n.must_hold]
            self._calibration = calibration.for_index(self.index, notes, domains)
        return self._calibration

    def share(self, bar: str) -> float:
        """The bar (nothing, note, related) for this Brain's kind of evidence, moved by the
        Brain's named retrieval policy (brain.json `retrieval_policy`: relaxed, standard or
        careful; design contract 15). Standard is the calibrated bar as measured."""
        words = self.calibration.cos is None
        base = getattr(self.policy, f"{'words_' if words else ''}{bar}_share")
        named = str(self.config.data.get("retrieval_policy") or "standard").strip().lower()
        step = NAMED_POLICIES.get(named, 0.0)
        return min(0.995, max(0.5, base + step))

    def evidence(self, scored) -> float:
        """The share of the Brain's unrelated requests this note's match beats (worked out
        once per scored note: a request asks it of every candidate several times)."""
        found = scored.detail.get("_evidence")
        if found is None:
            found = self.calibration.evidence(scored.detail.get("cos_raw"),
                                              scored.detail.get("bm_raw"))
            scored.detail["_evidence"] = found
        return found

    # ------------------------------------------------------------------ admission
    def admitted_notes(self, chain, partitions):
        """The notes this caller may see: worked out once per caller for this index (it does
        not change while this router lives), and handed out as a fresh list."""
        key = (tuple(chain), tuple(sorted(partitions or ())))
        found = self._admitted.get(key)
        if found is None:
            found = [n for n in self.index.notes.values()
                     if Scopes.admits(n.scope, n.partition, chain, partitions)]
            if len(self._admitted) > 16:
                self._admitted.clear()
            self._admitted[key] = found
        return list(found)

    def admitted_skills(self, chain, partitions):
        return [s for s in self.index.skills.values()
                if Scopes.admits(s.scope, s.partition, chain, partitions)]

    def _project_fact_pointers(self, route: Route, notes) -> list:
        """Make separately filed facts reachable without promoting them to answers.

        Membership is cached for this immutable index. Admission is applied on every
        request, so a previous caller cannot make a private note visible to another.
        """
        focus = route.focus
        members = self.project_members(focus)
        sig = route.signals
        candidates = [n for n in notes if n.id in members
                      and n.id != focus.id and not n.standing and not n.must_hold
                      and n.route_key not in sig.exclude_topics
                      and (sig.only_topics is None or n.route_key in sig.only_topics)]
        ranked = self.score_notes(sig.request, candidates)
        calibrated = self.calibrated("note_abs_floor")
        pointers = [s for s in ranked if (self.evidence(s) > self.share("related")
                    if calibrated else s.score >= self.policy.note_abs_floor)]
        route.log(f"project facts: {min(len(pointers), self.policy.related_count)} pointer(s)")
        return pointers[:self.policy.related_count]

    def project_filed(self, focus) -> set[str]:
        """The notes filed with a project: in its folder or marked with its id. A pin is not
        filing: a Brain-wide note one project pins still belongs to every request."""
        key = f"filed:{focus.id}"
        if key not in self._project_members:
            self._project_members[key] = {
                n.id for n in self.index.notes.values()
                if n.topic in (focus.id, focus.slug)
                or (n.area == "projects" and n.route_key == focus.note.route_key)
                or str(n.meta.get("project_id") or "") == focus.id
            }
        return self._project_members[key]

    def project_members(self, focus) -> set[str]:
        """The notes filed with a project, pinned by it, or naming it. Cached for this
        immutable index."""
        if focus.id not in self._project_members:
            names = [focus.title] + focus.aliases
            pinned = set(focus.pinned_notes)
            self._project_members[focus.id] = self.project_filed(focus) | {
                n.id for n in self.index.notes.values()
                if n.id in pinned or any(_phrase(util.normalize(f"{n.title} {n.summary} {n.body}"), name)
                       for name in names)
            }
        return self._project_members[focus.id]

    def other_projects(self, focus, focuses) -> set[str]:
        """Notes filed with another project and not belonging to this one, the other
        projects' own notes included: a request about one project never receives them. A
        Brain-wide note that only names another project stays in reach."""
        own = self.project_members(focus)
        out = set()
        for other in focuses:
            if other.id != focus.id:
                out |= (self.project_filed(other) | {other.id}) - own
        return out

    def admitted_focuses(self, chain, partitions):
        return [f for f in self.index.focuses.values()
                if Scopes.admits(f.note.scope, f.note.partition, chain, partitions)]

    # ------------------------------------------------------------------ evidence
    def similarity(self, request) -> dict:
        if request not in self._sims:
            if len(self._sims) > 64:
                self._sims.clear()
            self._sims[request] = self.index.similarity(request)
        return self._sims[request]

    def _semantic(self, sims, key):
        value = sims.get(key)
        if value is None:
            return None
        p = self.policy
        return max(0.0, min(1.0, (value - p.semantic_floor) / p.semantic_span))

    def score_notes(self, request, notes, context=None) -> list:
        """Hybrid relevance of each note to the request, highest first.

        `context` is extra text that says what the work is about (a named Focus). A note
        scores the better of its match to the request alone and a slightly discounted match
        to the request read together with that context, so "the next Acme section"
        reaches the brand work the Acme Focus is about.
        """
        if not notes:
            return []
        if context:
            plain = {s.item.id: s for s in self.score_notes(request, notes)}
            widened = self.score_notes(f"{request} {context}", notes)
            out = []
            for scored in widened:
                base = plain[scored.item.id]
                boosted = round(scored.score * 0.9, 4)
                if boosted > base.score:
                    out.append(Scored(scored.item, boosted, ["via Focus context"],
                                      dict(scored.detail, focus_context=True)))
                else:
                    out.append(base)
            out.sort(key=lambda s: (-s.score, s.item.id))
            return out
        scores = self._hybrid(request, [n.id for n in notes], self.index.note_bm25, "note")
        out = [Scored(note, scores[note.id][0], detail=scores[note.id][1]) for note in notes]
        out.sort(key=lambda s: (-s.score, s.item.id))
        return out

    def topic_relevance(self, request, keys) -> dict:
        """How well each topic, read as a whole, matches the request: {route key: 0..1}.

        The same evidence as a note, over the topic's description (its topics.md line, or
        what is filed in it). A request about "the Webflow site" matches the Webflow topic
        even when the one note it needs never says "site"."""
        keys = [k for k in keys if k in self.index.topic_texts]
        scores = self._hybrid(request, keys, self.index.topic_bm25, "topic")
        return {key: value for key, (value, _detail) in scores.items()}

    def _hybrid(self, request, keys, bm25, kind) -> dict:
        """{key: (score, detail)}: half lexical, half semantic when embeddings are on.

        A candidate must be similar in absolute terms AND stand out from the other candidates
        for this request. On a corpus where everything is about the same business, raw
        similarity saturates; the per-request z-score is what separates the one note about the
        membership offer from forty notes that merely sound on-brand.
        """
        if not keys:
            return {}
        memo_key = (request, kind, tuple(sorted(keys)), id(self.policy))
        found = self._hybrids.get(memo_key)
        if found is not None:
            # The same request over the same candidates (routing, topics, must-holds): the
            # same scores. Each caller gets its own details to write on.
            return {k: (v, dict(d)) for k, (v, d) in found.items()}
        raw = bm25.scores(request, restrict=keys)
        coverages = bm25.coverages(request, restrict=keys)
        top = max(raw.values(), default=0.0)
        sims = self.similarity(request)
        cosines = [sims.get(f"{kind}:{k}") for k in keys]
        cosines = [c for c in cosines if c is not None]
        mean = sum(cosines) / len(cosines) if len(cosines) >= 5 else None
        spread = ((sum((c - mean) ** 2 for c in cosines) / len(cosines)) ** 0.5
                  if mean is not None else 0.0)
        out = {}
        p = self.policy
        weight, alone = p.semantic_weight, p.semantic_alone
        floor, span = p.semantic_floor, p.semantic_span
        standing_out = mean is not None and spread > 1e-6
        prefix = f"{kind}:"
        coss = [sims.get(prefix + key) for key in keys]
        if _np is not None and len(keys) > 200 and all(c is not None for c in coss):
            # The same arithmetic as the loop below, a whole Brain at once.
            cov = _np.array([coverages[k] for k in keys], dtype=float)
            bms = _np.array([raw.get(k, 0.0) for k in keys], dtype=float)
            cos = _np.array(coss, dtype=float)
            lexical = 0.6 * cov + 0.4 * (bms / top if top else 0.0)
            semantic = _np.clip((cos - floor) / span, 0.0, 1.0)
            if standing_out:
                standout = _np.clip(((cos - mean) / spread + 0.5) / 3.0, 0.0, 1.0)
                semantic = _np.minimum(semantic, standout)
            hybrid = weight * semantic + (1 - weight) * lexical
            if alone > 0:
                hybrid = _np.maximum(hybrid, alone * semantic)
            hybrid = _np.minimum(hybrid, 1.0)
            for key, h, c, b, s_, raw_cos in zip(keys, hybrid.tolist(), cov.tolist(),
                                                 bms.tolist(), semantic.tolist(), coss,
                                                 strict=True):
                out[key] = (round(h, 4), {"coverage": round(c, 3), "bm25": round(b, 3),
                                          "semantic": round(s_, 3), "bm_raw": b,
                                          "cos_raw": raw_cos})
            if len(self._hybrids) > 32:
                self._hybrids.clear()
            self._hybrids[memo_key] = out
            return {k: (v, dict(d)) for k, (v, d) in out.items()}
        for key in keys:
            coverage = coverages[key]
            bm = raw.get(key, 0.0)
            lexical = 0.6 * coverage + 0.4 * (bm / top if top else 0.0)
            cos = sims.get(prefix + key)
            semantic = None
            if cos is not None:  # _semantic, inline: this runs for every note
                semantic = max(0.0, min(1.0, (cos - floor) / span))
                if standing_out:
                    standout = ((cos - mean) / spread + 0.5) / 3.0
                    semantic = min(semantic, max(0.0, min(1.0, standout)))
            hybrid = lexical if semantic is None else weight * semantic + (1 - weight) * lexical
            if semantic is not None and alone > 0:
                hybrid = max(hybrid, alone * semantic)
            out[key] = (round(min(1.0, hybrid), 4), {
                "coverage": round(coverage, 3), "bm25": round(bm, 3),
                "semantic": None if semantic is None else round(semantic, 3),
                "bm_raw": bm, "cos_raw": cos})
        if len(self._hybrids) > 32:
            self._hybrids.clear()
        self._hybrids[memo_key] = out
        return {k: (v, dict(d)) for k, (v, d) in out.items()}

    def score_skills(self, request, sig: Signals, skills) -> list:
        if not skills:
            return []
        bm25 = self.index.skill_bm25
        names = [s.name for s in skills]
        raw = bm25.scores(request, restrict=names)
        top = max(raw.values(), default=0.0)
        sims = self.similarity(request)
        request_stems = util.stems(util.content_terms(request))
        artifact_terms = ARTIFACT_TERMS | {t.lower() for t in self.config.routing.artifact_terms}
        out = []
        for skill in skills:
            reasons = []
            relative = raw.get(skill.name, 0.0) / top if top else 0.0
            coverage = bm25.coverage(request, skill.name)
            semantic = self._semantic(sims, f"skill:{skill.name}") or 0.0
            score = 0.35 * semantic + 0.1 * relative + 0.1 * coverage
            # Declared phrases are the owner's own words for when a skill applies.
            phrase_bonus, partial = 0.0, 0.0
            for phrase in skill.triggers + skill.aliases + skill.cue_terms:
                phrase_terms = util.terms(phrase)
                if len(phrase_terms) >= 2 and _phrase(sig.norm, phrase):
                    phrase_bonus += 0.8
                    reasons.append(f"phrase '{phrase}'")
                elif len(phrase_terms) == 1 and phrase_terms[0] in sig.wordset:
                    phrase_bonus += 0.25
                    reasons.append(f"cue '{phrase}'")
                else:
                    content_words = util.content_terms(phrase)
                    content = util.stems(content_words)
                    kinds = set(content_words) & artifact_terms
                    if len(content) >= 2 and (not kinds or kinds & sig.artifacts):
                        partial = max(partial, len(content & request_stems) / len(content))
            score += min(1.2, phrase_bonus)
            if partial >= 0.5:
                score += 0.3 * partial
                reasons.append(f"trigger overlap {partial:.2f}")
            # The skill's own name, split from camelCase, kebab or snake case.
            name_words = [w for w in re.split(r"[^a-z0-9]+", re.sub(
                r"([a-z])([A-Z])", r"\1 \2", skill.name).lower())
                if len(w) > 1 and w not in GENERIC_SKILL_WORDS]
            name_stems = util.stems(name_words)
            name_hits = {w for w in name_stems & request_stems if len(w) >= 4}
            name_kinds = set(name_words) & artifact_terms
            consistent = not name_kinds or bool(name_kinds & sig.artifacts)
            if len(name_stems) >= 2 and name_stems <= request_stems:
                score += 0.6
                reasons.append("full name")
            elif name_hits and consistent:
                score += 0.3 * min(2, len(name_hits))
                reasons.append("name word " + ", ".join(sorted(name_hits)))
            if sig.artifacts & {a.lower() for a in skill.artifacts}:
                score += 0.15
                reasons.append("artifact")
            out.append(Scored(skill, round(score, 4), reasons, {
                "semantic": round(semantic, 3), "bm25": round(raw.get(skill.name, 0.0), 3)}))
        out.sort(key=lambda s: (-s.score, s.item.name))
        return out

    # ------------------------------------------------------------------ exact routes
    def _exact_note(self, request, chain, partitions):
        value = request.strip().lstrip("/").strip()
        if not value or re.search(r"\s", value):
            return None
        note = self.index.note(value)
        if note is None:
            lowered = value.lower()
            note = next((n for n in self.index.notes.values() if n.id.lower() == lowered), None)
        if note and Scopes.admits(note.scope, note.partition, chain, partitions):
            return note
        return None

    def _exact_skill(self, request, skills):
        value = request.strip()
        slash = value.startswith("/")
        key = util.normalize(value.lstrip("/"))
        for skill in skills:
            names = [skill.name] + skill.aliases
            if any(util.normalize(n) == key for n in names):
                if slash or len(key.split()) <= 4:
                    return skill
        return None

    @staticmethod
    def _skill_phrase_hit(sig, skills) -> bool:
        for skill in skills:
            for phrase in skill.triggers + skill.aliases + skill.cue_terms:
                if len(util.terms(phrase)) >= 2 and _phrase(sig.norm, phrase):
                    return True
        return False

    # ------------------------------------------------------------------ focus
    def find_focus(self, sig: Signals, focuses, override=None):
        """(focus, reason) for the one Focus this request names, or (None, reason)."""
        if override:
            key = util.normalize(override)
            target = self.config.aliases.get(str(override).strip())
            for focus in focuses:
                if target and focus.id == target:
                    return focus, "explicit Focus override"
            for focus in focuses:
                names = [focus.id, focus.slug, focus.title] + focus.aliases
                if any(util.normalize(n) == key for n in names):
                    return focus, "explicit Focus override"
            return None, f"no admitted Focus named {override!r}"
        term_owner: dict[str, set] = {}
        for focus in focuses:
            for word in self._focus_index_terms(focus):
                term_owner.setdefault(word, set()).add(focus.id)
        named = []
        cue = sig.status_cue or sig.focus_update or sig.work_cue
        for focus in focuses:
            name_terms = {w for w in util.terms(f"{focus.slug} {focus.title}")
                          if w not in FOCUS_GENERIC and w not in util.STOPWORDS}
            alias_hit = any(_phrase(sig.norm, a) for a in focus.aliases)
            overlap = len(name_terms & sig.wordset)
            name_phrase = self._focus_name_phrase(focus)
            reason = None
            if alias_hit:
                reason = "alias"
            elif name_phrase and _phrase(sig.norm, name_phrase):
                reason = f"distinctive name '{name_phrase}'"
            elif name_terms and overlap == len(name_terms) and cue:
                reason = "name"
            elif name_terms and len(name_terms) >= 3 and overlap >= 0.6 * len(name_terms) and cue:
                reason = "most of name"
            else:
                distinct = {w for w in self._focus_index_terms(focus)
                            if len(term_owner.get(w, ())) == 1} & sig.wordset
                if distinct:
                    declared = set(util.terms(" ".join([focus.title] + focus.aliases)))
                    if distinct <= util.ACTION_VERBS and not distinct & declared:
                        # A summary's command is weak identity evidence. The subject
                        # must also qualify as ordinary context, using the same bar.
                        # Query scoring already excludes these command words.
                        scored = self.score_notes(sig.request, [focus.note])[0]
                        fits = (self.evidence(scored) > self.share("note")
                                if self.calibrated("note_abs_floor")
                                else scored.score >= self.policy.note_abs_floor)
                        if not fits:
                            continue
                        reason = f"distinctive description subject, relevance {scored.score:.2f}"
                    else:
                        reason = "distinctive term " + ", ".join(sorted(distinct))
            if reason:
                named.append((focus, reason))
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            strong = [pair for pair in named if not pair[1].startswith("distinctive")]
            if len(strong) == 1:
                return strong[0]
            return None, "ambiguous: " + ", ".join(f.id for f, _r in named)
        return None, "no Focus named"

    def _focus_name_phrase(self, focus):
        """A Focus's name as a phrase ("30 60 90", "bank of china"), when it is distinctive.

        The slug without generic words at either end, at least two words, and rare in the
        brain: used by the project itself and at most a couple of other notes. A rare name in
        the request names the project with no status word needed; a common phrase ("ai
        enablement") still needs one, because the request may be about the subject."""
        key = f"phrase:{focus.id}"
        if key in self._focus_terms_cache:
            return self._focus_terms_cache[key]
        words = [w for w in focus.slug.lower().split("-") if w]
        while words and (words[0] in FOCUS_GENERIC or words[0] in util.STOPWORDS):
            words.pop(0)
        while words and (words[-1] in FOCUS_GENERIC or words[-1] in util.STOPWORDS):
            words.pop()
        phrase = " ".join(words) if len(words) >= 2 else None
        if phrase:
            uses = sum(1 for n in self.index.notes.values() if n.id != focus.id
                       and _phrase(util.normalize(f"{n.title} {n.body}"), phrase))
            if uses > max(2, int(0.02 * len(self.index.notes))):
                phrase = None
        self._focus_terms_cache[key] = phrase
        return phrase

    def _focus_index_terms(self, focus):
        """Names that identify one Focus: the words of its title and aliases, and capitalized
        words in its summary line ("Acme", "Globex", "Quillfeather"), when rare
        across the whole corpus. A common word that happens to be rare here and sits in the
        summary ("workspace", "relaunch") names nothing: a request about relaunching something
        else is not about this project."""
        cached = self._focus_terms_cache.get(focus.id)
        if cached is not None:
            return cached
        summary = str(focus.note.index_line or "")
        names = {m.lower() for m in re.findall(r"[A-Za-z0-9]+", summary) if m[0].isupper()}
        alias_words = set(util.terms(" ".join(focus.aliases + [focus.title])))
        text = summary + " " + " ".join(focus.aliases + [focus.title])
        bm25 = self.index.note_bm25
        limit = max(2, int(0.02 * bm25.n))
        out = set()
        for word in util.terms(text):
            if word not in names and word not in alias_words:
                continue
            if (len(word) < self.policy.focus_distinct_min_len or word in FOCUS_GENERIC
                    or word in util.STOPWORDS or word.isdigit()):
                continue
            stemmed = util.stem(word)
            frequency = sum(1 for counts in bm25.docs.values() if stemmed in counts)
            if frequency <= limit:
                out.add(word)
        self._focus_terms_cache[focus.id] = out
        return out

    # ------------------------------------------------------------------ main entry
    def route(self, request, chain, partitions=(), *, focus_override=None,
              task_type_override=None, previous=None) -> Route:
        """`previous` is the conversation's last packet. Whatever the routing mode, the
        must-holds whose domain the request touches are attached at the end."""
        route = self._route(request, chain, partitions, focus_override=focus_override,
                            task_type_override=task_type_override, previous=previous)
        self._prefer_newer(route)
        self._attach_must_holds(route)
        self._complete_related(route)
        return route

    def _complete_related(self, route: Route) -> None:
        """Use pointer slots for context the packet does not already carry.

        Refill only from the admitted candidates that passed the original related bar.
        Newly reached areas keep their must-holds, including when a rule itself was
        the pointer that reached the area. Reached areas grow, so this loop is bounded
        by the finite candidate pool; neither the note nor pointer threshold changes.
        """
        if not route.related_pool:
            return
        by_id = {}
        for scored in route.related + route.related_pool:
            by_id.setdefault(scored.item.id, scored)
        pool = list(by_id.values())
        limit = max(self.policy.related_count, len(route.related))
        covered = {s.item.id for s in route.notes + route.style_notes + route.standing_answer}
        covered |= {old.id for old, _new in route.older}
        covered |= {self.index.cards[s.item.path].id for s in route.sections
                    if s.item.path in self.index.cards}
        reached = {s.item.route_key for s in route.related}
        rules = {m.note.id for m in route.must_holds + route.must_overflow}
        while True:
            route.related = [s for s in pool if s.item.id not in covered | rules][:limit]
            reached |= {s.item.route_key for s in route.related}
            self._attach_must_holds(route, reached_extra=reached)
            current = {m.note.id for m in route.must_holds + route.must_overflow}
            if current <= rules:
                return
            rules |= current

    # ------------------------------------------------------------------ dated values
    # Two dated notes that give a figure for the same thing (a monthly total, a count, a
    # version) are one value and its history. The brief carries the newest (`dated`: its
    # `as_of`, else when its text last changed), in the place of whichever was picked, and
    # lists the older ones as older values (`route.older`), never as if they were current. A
    # note is dated when it says `as_of` or is a state note.
    # A question about a project ("how much of the seed round is committed so far?") gets the
    # project's state, and the newest dated values close to what it asks (DATED_RELEVANT).
    NO_DATED = ("focus-update", "portfolio", "system", "exact-note")
    DATED_RELEVANT = 0.45
    DATED_TOP = 3

    def _prefer_newer(self, route: Route) -> None:
        if route.mode in self.NO_DATED:
            return
        # Never a note loaded "manual" (the owner's goals): a target is not a newer value.
        pool = [n for n in self.admitted_notes(route.chain, route.partitions)
                if (n.as_of or n.kind == "state") and not self.config.is_focus(n)
                and n.load != "manual" and n.id not in route.out_of_project
                and tension.measures(n.body)]
        if not pool:
            return
        if route.mode == "focus-only":
            have = {s.item.id for s in route.notes}
            for scored in self.score_notes(route.request, pool)[:self.DATED_TOP]:
                if scored.score >= self.DATED_RELEVANT and scored.item.id not in have:
                    route.notes.append(Scored(scored.item, scored.score,
                                              ["a dated value the project question asks for"],
                                              {"dated": True}))
                    route.log(f"{scored.item.id}: dated value for the project question "
                              f"({scored.score:.2f})")
        if len(pool) < 2 or not route.notes:
            return
        dated = {n.id for n in pool}
        kept, older, taken = [], {}, set()
        for scored in route.notes:
            note = scored.item
            group = ([n for n in pool if n.id != note.id
                      and tension.same_measure(tension.measures(note.body),
                                               tension.measures(n.body))]
                     if note.id in dated else [])
            if not group:
                if note.id not in taken:
                    kept.append(scored)
                    taken.add(note.id)
                continue
            newest = max([note] + group, key=lambda n: (n.dated, n.id))
            # Values dated the same day that differ have no defined precedence: a conflict.
            # Both are sent, labelled, and neither is passed off as current (no newest-wins).
            tied = [n for n in [note] + group if n.as_of and n.dated == newest.dated
                    and newest.as_of]
            rivals = [n for n in tied if n.id != newest.id
                      and tension.same_measure(tension.measures(n.body),
                                               tension.measures(newest.body))]
            if rivals:
                for rival in rivals:
                    route.conflicts.setdefault(newest.id, rival.id)
                    route.conflicts.setdefault(rival.id, newest.id)
                    if rival.id not in taken:
                        taken.add(rival.id)
                        kept.append(Scored(rival, scored.score, list(scored.reasons)
                                           + [f"differs from {newest.id} on the same date"],
                                           dict(scored.detail, disputed=True)))
                route.log(f"conflict: {newest.id} and {', '.join(r.id for r in rivals)} "
                          f"give different values as of {newest.dated}")
            tied_ids = {n.id for n in rivals}
            for member in [note] + group:
                if member.id != newest.id and member.id not in tied_ids:
                    older.setdefault(member.id, (member, newest))
            if newest.id in taken:
                continue
            taken.add(newest.id)
            detail = dict(scored.detail, disputed=True) if rivals else dict(scored.detail)
            if newest.id == note.id:
                kept.append(Scored(note, scored.score, list(scored.reasons), detail)
                            if rivals else scored)
            else:
                kept.append(Scored(newest, scored.score,
                                   list(scored.reasons) + [f"newer value than {note.id}"],
                                   detail))
                route.log(f"{newest.id}: newer value than {note.id} ({newest.dated} against "
                          f"{note.dated})")
        route.notes = [s for s in kept if s.item.id not in older]
        route.related = [s for s in route.related
                         if s.item.id not in older and s.item.id not in taken]
        route.older = sorted(older.values(), key=lambda pair: (pair[1].id, pair[0].dated))
        if route.older:
            route.log("older values listed: " + ", ".join(o.id for o, _n in route.older))

    # ------------------------------------------------------------------ must-holds
    # MUST-HOLDS are constraints the owner marked `load: domain`. Whenever their domain is in
    # play they go in, whatever their relevance, the note budget or the per-topic caps, and
    # however stale (flagged, never ranked down). A domain is in play when the request (or, in
    # a continuation, the conversation's subject) uses one of the note's triggers; when the
    # route already reached the domain (a selected note, a declared topic, the Focus, the
    # procedure's loads); or when one of the domain's topics is among the request's best topic
    # matches. The test leans toward including: a needless constraint costs one line, a
    # missing one costs the answer.
    NO_MUST_HOLDS = ("focus-update", "portfolio", "system", "exact-note")

    def _attach_must_holds(self, route: Route, reached_extra=()) -> None:
        if route.mode in self.NO_MUST_HOLDS:
            return
        notes = [n for n in self.admitted_notes(route.chain, route.partitions) if n.must_hold]
        if not notes:
            return
        p = self.policy
        sig = route.signals
        words = util.stems(sig.words)
        norm = sig.norm
        if sig.continuation and route.subject:
            words |= util.stems(util.terms(route.subject))
            norm = f"{util.normalize(route.subject)} {norm}"
        # Qualified pointers count: their domain's rules must be available before
        # opening them. A lean brief's near matches are only search suggestions and
        # have not established that their domains are in play.
        pointers = [] if route.mode == "lean" else route.related
        reached = set(route.topics) | set(route.forced_topics) | {
            s.item.route_key for s in list(route.notes) + list(route.style_notes)
            + list(route.standing_answer) + list(pointers)}
        reached.update(reached_extra)
        if route.focus is not None:
            reached.add(route.focus.note.route_key)
        if route.skill is not None:
            reached |= set(route.skill.load_topics)
        reached_areas = {key.split("/", 1)[0] for key in reached}
        focus_ids = {route.focus.id} if route.focus is not None else set()
        close: dict | None = None      # the request's best topic matches, when needed
        sims: dict | None = None       # its similarity to every domain passage, when needed

        def why_for(note) -> str | None:
            nonlocal close, sims
            targets = note.applies_to
            if "*" in targets:
                return "applies to every task"
            for trigger in note.triggers:
                if " " in trigger or "-" in trigger:
                    if util.phrase_in(trigger, norm):
                        return f"the request mentions {trigger!r}"
                elif util.stem(trigger) in words:
                    return f"the request mentions {trigger!r}"
            for target in targets:
                if target in reached or target in reached_areas or target in focus_ids:
                    return f"this task touches {target}"
            if sims is None:
                sims = self.similarity(sig.request)     # {} without an embedding model
            # Not calibrated against unrelated requests: another part of the same Brain's
            # work beats 99% of them too (must-hold decoys rose from 13% to 39% on a tuning
            # Brain). Stage 3's applies_when and generated triggers take this on.
            meaning = self._semantic(sims, f"domain:{note.id}")
            if meaning is not None and meaning >= p.must_hold_semantic_bar:
                return f"this request is about its domain (meaning {meaning:.2f})"
            if close is None:
                close = self._close_topics(sig.request)
            for target in targets:
                for key, value in close.items():
                    if key == target or key.split("/", 1)[0] == target:
                        return f"this request is about {key} ({value:.2f})"
            return None

        today = util.today_date()
        picks = []
        for note in notes:
            why = why_for(note)
            if why is not None:
                picks.append(MustHold(note, why, note.stale_reason(
                    today, self.config.review_days_for(note))))
        if not picks:
            return
        # Critical ones first, then those the request or the route names outright.
        picks.sort(key=lambda m: (not m.note.critical,
                                  m.why.startswith("this request is about"), m.note.id))
        previous = [m.note.id for m in route.must_holds + route.must_overflow]
        route.must_holds = picks[:p.must_hold_max]
        route.must_overflow = picks[p.must_hold_max:]
        if previous != [m.note.id for m in picks]:
            route.log("must hold: " + "; ".join(f"{m.note.id} ({m.why})" for m in picks))

    def _close_topics(self, request) -> dict:
        """The request's best two topic matches, when they clear their must-hold bars:
        {route key: score}."""
        p = self.policy
        scores = self.topic_relevance(request, list(self.index.topic_texts))
        best = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:2]
        bars = (p.must_hold_topic_bar, p.must_hold_second_bar)
        return {key: value for (key, value), bar in zip(best, bars) if value >= bar}

    def _route(self, request, chain, partitions=(), *, focus_override=None,
               task_type_override=None, previous=None) -> Route:
        sig = analyze(request, self.config.routing, {"task_type": task_type_override})
        previous = previous or {}
        # A note loaded "manual" is opened by its id or found by a search, never routed into
        # a packet (the owner's goals, which steer what is kept, not what a request gets).
        notes = [n for n in self.admitted_notes(chain, partitions) if n.load != "manual"]
        if previous and not (sig.portfolio or sig.system or sig.permission or sig.focus_update
                             or sig.deep or sig.orientation) and len(sig.words) <= 20:
            leans = _refers_back(sig)
            if leans == "short" and self._stands_alone(sig, notes):
                leans = None
            if leans:
                self._read_followup(sig, previous)
        route = Route(request=str(request or ""), chain=list(chain),
                      partitions=list(partitions), signals=sig, task_type=sig.task_type,
                      scale=sig.scale, policy=self.policy)
        route.previous = previous
        route.subject = self._subject(sig, previous)
        route.draft = self._draft(sig, previous)
        skills = self.admitted_skills(chain, partitions)
        focuses = self.admitted_focuses(chain, partitions)

        exact = self._exact_note(route.request, chain, partitions)
        if exact is not None:
            route.mode, route.task_type, route.scale = "exact-note", "knowledge", "micro"
            route.notes = [Scored(exact, 1.0, ["exact note id or alias"])]
            route.topics = [exact.route_key]
            route.log(f"exact note {exact.id}")
            return route
        exact_skill = self._exact_skill(route.request, skills)
        if exact_skill is not None:
            route.mode, route.procedure, route.skill = "exact-skill", "executable", exact_skill
            route.scale = "deep" if route.scale != "micro" else "standard"
            route.log(f"exact skill {exact_skill.name}")
            self._standard(route, notes, skills, focuses, prerequisites_from=[exact_skill])
            return route

        if sig.orientation and not focus_override \
                and self.find_focus(sig, focuses)[0] is None:
            return self._orientation(route, notes, focuses)

        if sig.portfolio:
            route.mode, route.focus_mode = "portfolio", "portfolio"
            route.task_type, route.scale = "knowledge", "micro"
            route.portfolio = sorted(focuses, key=lambda f: str(f.current().get("updated")),
                                     reverse=True)
            route.portfolio.sort(key=lambda f: not f.active)  # stable: active first, newest first
            route.log(f"portfolio of {len(route.portfolio)} Focus item(s)")
            return route

        if sig.system and not focus_override:
            return self._system(route, skills)

        # A request that uses a skill's own declared phrase ("create a brand sheet") is
        # artifact work, whatever its length.
        if route.scale == "micro" and not sig.short_form and route.task_type != "knowledge" \
                and self._skill_phrase_hit(sig, skills):
            route.scale = "standard"
            route.log("skill phrase in request: standard scale")

        focus, reason = self.find_focus(sig, focuses, focus_override)
        route.log(f"focus: {reason}")
        if focus is not None:
            route.focus = focus
            route.focus_reason = reason
            route.out_of_project = self.other_projects(focus, focuses)
            if sig.focus_update:
                route.mode, route.focus_mode = "focus-update", "focus-update"
                route.task_type, route.scale = "workflow", "micro"
                return route
            # A question about where the project stands gets the project alone; a plan or a
            # draft for it ("plan the guest list for next season") needs the notes too.
            from .request_type import classify
            if route.task_type == "knowledge" and (not sig.artifacts or sig.status_cue) \
                    and classify(route) not in ("planning", "writing", "code"):
                route.mode, route.focus_mode = "focus-only", "focus-only"
                route.scale = "micro" if route.scale != "deep" else route.scale
                if not _focus_overview(sig, focus):
                    route.related = self._project_fact_pointers(route, notes)
                if not sig.status_cue:
                    # A question about the project's content ("what budget did we set for
                    # podcasts in the spring launch?") may be answered in one of its files.
                    route.sections = self._choose_sections(
                        route, f"{focus.title} {focus.note.index_line}")
                return route
            route.focus_mode = "focus-aware"
        self._standard(route, notes, skills, focuses)
        self._keep_to_project(route)
        return route

    def _keep_to_project(self, route: Route) -> None:
        """Take the notes of other projects out of what was chosen. They are removed after
        the choice, never before it: leaving them out of the pool would move the relative
        bars and could bring in a weaker note in their place."""
        out = route.out_of_project
        if not out:
            return
        dropped = 0
        for name in ("notes", "related", "related_pool", "style_notes", "standing_answer"):
            kept = [s for s in getattr(route, name) if s.item.id not in out]
            dropped += len(getattr(route, name)) - len(kept)
            setattr(route, name, kept)
        if dropped:
            route.log(f"project scope: {dropped} note(s) of other projects left out")

    # ------------------------------------------------------------------ orientation
    def _orientation(self, route: Route, notes, focuses) -> Route:
        """The lay of the land for someone new: every area with what it covers and the notes
        at its centre, a few notes in full (the most relevant of the central ones, one per
        area), the owner's core writing rules when the person will write, and the active
        projects. Nothing here depends on what the brain is about."""
        sig = route.signals
        p = self.policy
        route.mode, route.task_type, route.scale = "orientation", "knowledge", "standard"
        on_demand = [n for n in notes if not n.standing and not self.config.is_focus(n)]
        by_area: dict[str, list] = {}
        for note in on_demand:
            by_area.setdefault(note.area, []).append(note)
        areas = [a for a in self.config.area_order() if by_area.get(a)]
        areas += sorted(a for a in by_area if a not in areas)
        for area in areas:
            members = sorted(by_area[area], key=lambda n: (-self.index.centrality(n.id), n.id))
            topics: dict[str, int] = {}
            for note in members:
                topics[note.topic] = topics.get(note.topic, 0) + 1
            route.orientation.append({
                "area": area, "label": self.config.area_label(area),
                "description": str((self.config.areas.get(area) or {}).get("description")
                                   or ""),
                "count": len(members),
                "topics": sorted(topics, key=lambda t: (-topics[t], t)),
                "notes": members[:3]})
        # In full: the note at the centre of each area, in the owner's order of areas. A
        # newcomer's words ("what should I know about this company?") say little about any
        # one topic, so relevance only breaks ties; an area the startup kernel already
        # carries (mostly standing notes) is skipped.
        standing: dict[str, int] = {}
        for note in notes:
            if note.standing:
                standing[note.area] = standing.get(note.area, 0) + 1
        relevance = {s.item.id: s.score for s in self.score_notes(sig.request, on_demand)}
        picked = []
        for area in areas:
            members = by_area[area]
            if standing.get(area, 0) > len(members):
                continue
            share = {}
            for note in members:
                share[note.topic] = share.get(note.topic, 0) + 1
            # Central to its topic, and from a topic that carries the area: a note that sits
            # right on a two-note side topic's line does not stand for the whole area.
            best = max(members, key=lambda n: (
                self.index.centrality(n.id) * (share[n.topic] / len(members)) ** 0.5,
                relevance.get(n.id, 0.0), n.id))
            picked.append(Scored(best, relevance.get(best.id, 0.0), ["centre of its area"],
                                 {"rel": round(relevance.get(best.id, 0.0), 4),
                                  "centrality": self.index.centrality(best.id),
                                  "adj": self.index.centrality(best.id)}))
            if len(picked) >= p.orientation_notes:
                break
        route.notes = picked
        if sig.wordset & (WRITING_VERBS | {"writing", "content", "posts", "post", "copy"}):
            admitted = {n.id: n for n in on_demand}
            route.style_notes = [
                Scored(admitted[i], 0.0, ["core writing rule"],
                       {"core": True, "rel": 0.0, "adj": 0.0, "blend": 0.0})
                for i in self.config.routing.house_style_notes[:p.orientation_style]
                if i in admitted]
        route.portfolio = [f for f in sorted(focuses, key=lambda f: str(
            f.current().get("updated")), reverse=True) if f.active]
        route.topics = list(dict.fromkeys(s.item.route_key for s in route.notes))
        route.log(f"orientation: {len(areas)} area(s), {len(picked)} note(s) in full, "
                  f"{len(route.style_notes)} core writing rule(s)")
        return route

    # ------------------------------------------------------------------ follow-ups
    def _read_followup(self, sig: Signals, previous: dict) -> None:
        """An edit of text the session holds, or a continuation with a new need?

        An edit opens with an editing verb and brings nothing new: every content word is
        about form ("the opening line", "punchier") or was already in the conversation. Any
        other request that leans on the conversation continues it, and carries a writing task
        forward unless it is a question ("now add a CTA" keeps writing; "can we boost it with
        paid?" asks something else)."""
        sig.followup = True
        sig.subject = str(previous.get("subject") or previous.get("request") or "").strip()
        # What the conversation already said: its subject, and the request that started the
        # draft it is on (a side question in between does not make the draft's words new).
        before = util.stems(util.terms(sig.subject)) | util.stems(
            util.terms(previous.get("draft") or ""))
        new = util.stems(util.content_terms(_without_edit_phrases(sig.request))) - before \
            - _EDIT_STEMS
        sig.followup_kind = "edit" if EDIT_START.match(sig.text) and not new else "continuation"
        if sig.followup_kind == "continuation" and previous.get("composing") and not (
                sig.question or "?" in sig.text):
            sig.inherited_composing = True

    def _stands_alone(self, sig: Signals, notes) -> bool:
        """A short request with no word pointing back is a question of its own when the brain
        finds something for it alone ("what's our UTM for LinkedIn?"); when it finds nothing,
        the request leans on the conversation ("is there a known workaround?")."""
        on_demand = [n for n in notes if not n.standing and not self.config.is_focus(n)]
        ranked = self.score_notes(sig.request, on_demand)
        return bool(ranked) and ranked[0].score >= self.policy.lean_floor

    @staticmethod
    def _draft(sig: Signals, previous: dict) -> str:
        """The request that started the writing task this conversation is on: a new writing
        request starts one, and anything else keeps the one before."""
        if sig.composing and not sig.followup:
            return sig.request.strip()
        return str(previous.get("draft") or "")

    def _subject(self, sig: Signals, previous: dict) -> str:
        """What the conversation is about after this request: an edit keeps the subject, a
        continuation adds to it (its last `subject_words` words), a new request starts one."""
        if not sig.followup:
            return sig.request.strip()
        if sig.edit:
            return sig.subject
        words = f"{sig.subject} {sig.request}".split()
        return " ".join(words[-self.policy.subject_words:])

    # ------------------------------------------------------------------ system questions
    def _system(self, route: Route, skills) -> Route:
        sig = route.signals
        route.mode = "system"
        docs = self.system_docs
        if docs:
            from .index import BM25
            bm = BM25({d.id: d.search_text for d in docs}, fold=self.index.fold)
            raw = bm.scores(sig.request)
            top = max(raw.values(), default=0.0)
            ranked = sorted(
                (Scored(d, round(0.6 * bm.coverage(sig.request, d.id)
                                 + 0.4 * (raw.get(d.id, 0.0) / top if top else 0.0), 4))
                 for d in docs), key=lambda s: (-s.score, s.item.id))
            count = {"micro": 1, "standard": 2, "deep": 4}.get(route.scale, 2)
            route.system_docs = [s for s in ranked if s.score > 0][:count] or ranked[:1]
        if route.scale == "deep" and self.system_skill:
            skill = next((s for s in skills if s.name == self.system_skill), None)
            if skill is not None:
                route.skill, route.procedure = skill, "executable"
                route.task_type = "combined"
        route.log(f"system question: {len(route.system_docs)} engine document(s)")
        return route

    # ------------------------------------------------------------------ standard routing
    def _standard(self, route: Route, notes, skills, focuses, prerequisites_from=None):
        sig = route.signals
        p = self.policy
        # A project a request does not name still competes on relevance like any note ("a
        # LinkedIn post inviting supervisors to our next webinar" needs the webinar series);
        # the project a request names comes as the Focus instead.
        named = route.focus.id if route.focus is not None else None
        on_demand = [n for n in notes if not n.standing
                     and (not self.config.is_focus(n) or (p.projects_compete and n.id != named))]
        standing = [n for n in notes if n.standing]

        # Skills first: the procedure that fits the task declares what knowledge it needs.
        prerequisites: list[str] = []
        if prerequisites_from:
            for skill in prerequisites_from:
                prerequisites += [t for t in skill.load_topics if t not in prerequisites]
        elif not sig.no_skill and not sig.permission and not sig.full_source \
                and not sig.edit \
                and route.scale != "micro" and route.task_type in ("combined", "workflow"):
            suggestible = [s for s in skills
                           if str(s.meta.get("invocation") or "").lower() != "explicit"]
            ranked = [s for s in self.score_skills(sig.request, sig, suggestible)
                      if s.score >= p.skill_floor]
            if ranked:
                best = ranked[0].score
                route.candidates = [s for s in ranked
                                    if best - s.score <= p.skill_window][:p.max_candidates]
                second = ranked[1].score if len(ranked) > 1 else 0.0
                decisive = best >= p.executable_floor and best - second >= p.decisive_margin
                if route.scale == "deep" and decisive:
                    route.skill, route.procedure = ranked[0].item, "executable"
                    route.candidates = []
                    prerequisites += [t for t in ranked[0].item.load_topics]
                    route.log(f"executable skill {ranked[0].item.name} ({best:.2f})")
                elif route.candidates:
                    route.procedure = "candidate"
                    credible = [s for s in route.candidates
                                if best - s.score <= p.credible_window]
                    prerequisites += _shared_loads([s.item for s in credible])
                    route.log("skill candidates " + ", ".join(
                        f"{s.item.name} {s.score:.2f}" for s in route.candidates))
        if route.focus is not None:
            prerequisites += [t for t in self._focus_topics(route.focus)
                              if t not in prerequisites]

        # WHAT THE WORK IS ABOUT, beyond the request's own words: the named Focus and the
        # routed procedure. A note scores the better of its match to the request alone and
        # a discounted match to the request read with this context.
        contexts = []
        if route.focus is not None:
            contexts.append(f"{route.focus.title} {route.focus.note.index_line}")
        if route.skill is not None:
            contexts.append(route.skill.description[:300])
        if sig.continuation and sig.subject:
            # A continuation is about what the conversation is about: "bots are filling it
            # in too" reaches form spam protection through the contact form asked about.
            contexts.append(sig.subject)
        context = " ".join(contexts) or None

        # Owner-declared shape: exclusions, allowlists and requested source documents.
        excluded = set(sig.exclude_topics)
        only = set(sig.only_topics) if sig.only_topics is not None else None
        if sig.full_source:
            refs = self._requested_references(sig, notes)
            route.references = refs
            if refs:
                pointing = {n.route_key for n in notes if set(n.references) & set(refs)}
                only = pointing if only is None else only & pointing
        previous_topics = list(route.previous.get("topics") or []) if sig.edit else []
        if sig.edit:
            # An edit to text the session already holds ("make the opening line punchier")
            # draws on what that text was built from and on the house style, not on every
            # note that happens to share a word with the edit ("opening", "opens").
            route.log("follow-up: the previous packet's topics and the house style only")
            allowed = set(previous_topics) | set(self.house_style) | {
                n.route_key for n in notes if n.id in set(self.config.routing.house_style_notes)}
            only = allowed if only is None else only & allowed
        domains = [t for t in dict.fromkeys(previous_topics + list(sig.include_topics)
                                            + prerequisites)
                   if t not in excluded and (only is None or t in only)]
        route.forced_topics = domains
        route.excluded_topics = sorted(excluded)

        # EVERY NOTE THE CALLER MAY SEE COMPETES ON RELEVANCE. Where a note is filed never
        # decides whether it can be found; topics only nudge the ranking.
        candidates = [n for n in on_demand if n.route_key not in excluded
                      and (only is None or n.route_key in only)]
        ranked_on_demand = self._rerank(route, sig.request,
                                        self.score_notes(sig.request, candidates, context))
        route.ranked = ranked_on_demand
        ranked_standing = self.score_notes(sig.request, standing)
        forced = domains

        # Permission and simple lookups can be answered by standing context alone.
        best_on_demand = ranked_on_demand[0].score if ranked_on_demand else 0.0
        if sig.permission:
            route.mode = "standing"
            query = sig.request + " approve approval approved publish external sign off " \
                                  "permission draft stage"
            answer = self.score_notes(query, standing)
            if self.permission_topics:
                answer = [s for s in answer if s.item.route_key in self.permission_topics] \
                    or answer
            route.standing_answer = [s for s in answer[:3] if s.score >= p.note_floor]
            route.topics = []
            route.confidence = answer[0].score if answer else 0.0
            route.log("permission: answered by standing rules")
            return
        if (route.task_type == "knowledge" and route.scale == "micro" and ranked_standing
                and not forced and route.focus is None):
            top_standing = ranked_standing[0]
            # Standing context answers a lookup only when it matches the request in words,
            # not only in tone: a rule about how to write to plant managers does not answer
            # "what keeps plant managers up at night?" because both name them.
            worded = (top_standing.detail.get("coverage") or 0.0) >= p.standing_coverage
            if (top_standing.score >= p.standing_floor
                    and top_standing.score >= best_on_demand + p.standing_margin
                    and best_on_demand < p.note_abs_floor + 0.1
                    and (worded or best_on_demand < p.near_floor)):
                route.mode = "standing"
                route.standing_answer = [top_standing]
                route.confidence = top_standing.score
                route.log(f"standing context answers this: {top_standing.item.id}")
                return

        route.confidence = best_on_demand
        # Parts of filed documents that answer the request on their own, quoted in the packet.
        route.sections = self._choose_sections(route, context, excluded, only)
        house, house_ids = set(), set()
        if (sig.composing and not sig.no_house_style) or (
                set(self.house_style) & set(sig.include_topics)):
            house = set(self.house_style) - excluded
            house_ids = set(self.config.routing.house_style_notes)
        topic_rel = self.topic_relevance(sig.request, {n.route_key for n in candidates})
        self._adjust(route, ranked_on_demand, domains, topic_rel)

        def in_house(scored):
            return scored.item.route_key in house or scored.item.id in house_ids

        # House style for a writing task: the owner's core list, the rules every piece of
        # writing needs, goes first in the owner's order (style is about how to write, not
        # what, so relevance to the request is a poor way to rank it); the rest of the
        # house-style topics follows, most relevant to this request first. Style rules stay
        # out of the ranking of what to write about: a strong match on the form ("LinkedIn
        # post") must not raise the bar for the substance.
        order = {note_id: i for i, note_id in enumerate(self.config.routing.house_style_notes)}
        style = sorted((s for s in ranked_on_demand if in_house(s)),
                       key=lambda s: (order.get(s.item.id, len(order)), -s.detail["adj"],
                                      s.item.id))
        pool = sorted((s for s in ranked_on_demand if not in_house(s)),
                      key=lambda s: (-s.detail["adj"], s.item.id))

        # Nothing required and no note clears the lean floor: say so rather than pad. A file
        # part overrides that only when the request names its file or the part answers it
        # closely (see UNBACKED_SEMANTIC).
        if self.calibrated("lean_floor"):
            # Knowledge decides: a filed document's card has its own bars for being quoted.
            cards = {c.id for c in self.index.cards.values()}
            best_evidence = max((self.evidence(s) for s in ranked_on_demand
                                 if s.item.id not in cards), default=0.0)
            weak = best_evidence <= self.share("nothing")
            why_weak = f"best match beats {best_evidence:.0%} of unrelated requests"
        else:
            weak = best_on_demand < p.lean_floor
            why_weak = f"best note {best_on_demand:.2f} < {p.lean_floor}"
        alone = (not domains and route.focus is None and route.skill is None
                 and not route.candidates and not style)
        unbacked = alone and weak
        # Quoting a file part that nothing else backs keeps its own measured bar: the parts
        # that answer alone are kept when the best note is under lean_floor, calibrated or not.
        if alone and best_on_demand < p.lean_floor and route.sections:
            kept = [s for s in route.sections if _answers_alone(s)]
            if len(kept) < len(route.sections):
                route.log("sections: nothing else backs this request; kept "
                          + (", ".join(s.item.id for s in kept) or "none"))
                dropped = [s.item.path for s in route.sections if s not in kept]
                route.pointed_files = list(dict.fromkeys(dropped + route.pointed_files))
            route.sections = kept
        if unbacked and not route.sections:
            route.mode = "lean"
            route.topics = []
            # The search an agent would run next, already done: the closest notes, listed by
            # title so the agent can open one, never sent as if they answered the request.
            route.related = self._point_to_files(
                route, [s for s in ranked_on_demand if s.score >= p.near_floor][:p.near_count],
                ranked_on_demand, p.near_count)
            route.log(f"lean: {why_weak}; {len(route.related)} near match(es) listed")
            return

        selected, related = self._select(route, pool, domains,
                                         house | {s.item.route_key for s in style})
        # A style rule outside the core list whose own match to the request clears the bar
        # the selected notes cleared is specific to this request (the CTA ladder for a call
        # to action): it follows the core list, and placement sends it like a selected note,
        # whatever the core list has used of the style share. Raw relevance, because every
        # style rule gets a writing task's topic lift, which says nothing about the request.
        artifact_terms = ARTIFACT_TERMS | {t.lower() for t in self.config.routing.artifact_terms}
        for scored in style:
            # Without a core list, the house-style topics are the owner's rules as a whole.
            scored.detail["core"] = scored.item.id in order or not order
            # A rule whose title names a kind of artifact ("LinkedIn post architecture") is
            # for that artifact: it does not fill spare share in a proposal.
            formats = set(util.terms(scored.item.title)) & artifact_terms
            scored.detail["format_fits"] = not formats or bool(formats & sig.artifacts)
            scored.detail["specific"] = bool(
                not scored.detail["core"] and route.select_threshold
                and scored.detail["rel"] >= route.select_threshold)
        style.sort(key=lambda s: (not s.detail["core"], not s.detail["specific"]))
        chosen = {s.item.id for s in selected}
        wanted = [i for i in sig.include_notes if i not in chosen]
        for scored in pool:
            if scored.item.id in wanted:
                selected.append(scored)
                route.log(f"{scored.item.id}: named by an intent")
        related = [s for s in related if s.item.id not in set(wanted)]
        # A caveat the owner attached to a topic travels with every note of that topic
        # ("the content strategy is not defined yet" with any content strategy note).
        hints = self.config.routing.hints
        chosen = {s.item.id for s in selected} | {s.item.id for s in style}
        for scored in list(selected) + list(style):
            for caveat in (hints.get(scored.item.route_key) or {}).get("with_notes") or []:
                if caveat in chosen:
                    continue
                match = next((s for s in ranked_on_demand if s.item.id == caveat), None)
                if match is not None:
                    selected.append(match)
                    chosen.add(caveat)
                    route.log(f"{caveat}: caveat for {scored.item.route_key}")
        related = [s for s in related if s.item.id not in chosen]
        selected, related = self._linked(route, selected, related, chosen, ranked_on_demand)
        taken = {s.item.id for s in selected} | {s.item.id for s in style}
        related = self._point_to_files(route, [s for s in related if s.item.id not in taken],
                                       ranked_on_demand, p.related_count, taken)
        route.style_notes = style
        route.notes = selected
        route.related = related
        route.topics = list(dict.fromkeys(
            [s.item.route_key for s in style] + [s.item.route_key for s in selected]))
        if route.skill is not None:
            route.references = list(dict.fromkeys(
                route.references + [r for r in route.skill.load_references
                                    if r in self.index.references]))
        self._settle_sections(route)

    def _point_to_files(self, route, related, ranked, limit, taken=()):
        """`related` with the cards of the files whose parts matched but were not quoted
        (`route.pointed_files`) first, so the AI can open a file the packet does not quote.
        At most `limit`."""
        by_id = {s.item.id: s for s in ranked}
        cards = []
        for path in route.pointed_files:
            card = self.index.cards.get(path)
            scored = by_id.get(card.id) if card is not None else None
            if scored is not None and card.id not in taken:
                cards.append(scored)
        if not cards:
            return related
        route.log("listed instead of quoted: " + ", ".join(s.item.id for s in cards))
        ids = {s.item.id for s in cards}
        return (cards + [s for s in related if s.item.id not in ids])[:limit]

    def _settle_sections(self, route):
        """A file the packet already points at whole (a procedure loads it, the request asks
        for all of it) is not quoted in parts too; a quoted file's card is not sent beside its
        own sections."""
        whole = set(route.references)
        if whole and route.sections:
            route.sections = [s for s in route.sections if s.item.path not in whole]
        quoted = {s.item.path for s in route.sections}
        cards = {self.index.cards[p].id for p in quoted if p in self.index.cards}
        if cards:
            route.notes = [s for s in route.notes if s.item.id not in cards]
            route.related = [s for s in route.related if s.item.id not in cards]
            route.log("quoted instead of their cards: " + ", ".join(sorted(cards)))

    def _title_terms(self) -> tuple[dict, dict, dict]:
        """({file path: its title's content words, in order}, {word: how many file titles
        use it}, {file path: {part of a joined word: the word}}), stemmed, for telling when a
        request names a file. A date or a version is no part of a title's name; a joined name
        ("LenaMeeting transcript") is named by its parts too ("what did Lena say")."""
        cached = getattr(self, "_titles", None)
        if cached is None:
            words, parts = {}, {}
            for path in {s.path for s in self.index.sections.values()}:
                title = self.index.fold(self.index.file_title(path))
                found, joined = [], {}
                for token in re.findall(r"[A-Za-z0-9]+", title):
                    lower = token.lower()
                    if (len(lower) < 2 or lower in util.STOPWORDS
                            or TITLE_NUMBER.fullmatch(lower)):
                        continue
                    word = util.stem(lower)
                    found.append(word)
                    pieces = JOINED.split(token)
                    for piece in pieces if len(pieces) > 1 else ():
                        piece = util.stem(piece.lower())
                        if len(piece) > 2 and piece not in util.STOPWORDS:
                            joined.setdefault(piece, word)
                words[path], parts[path] = found, joined
            counts: dict[str, int] = {}
            for found in words.values():
                for word in set(found):
                    counts[word] = counts.get(word, 0) + 1
            cached = self._titles = (words, counts, parts)
        return cached

    def _names_file(self, request_terms, path) -> bool:
        """Does the request name this file? Half its title's words ("the spring proposal"),
        two of them side by side ("the brand voice guide"), or, for a short title, a word no
        other file's title uses ("the proposal", when there is one)."""
        words, counts, parts = self._title_terms()
        title = words.get(path) or []
        unique = set(title)
        joined = parts.get(path) or {}
        request_terms = set(request_terms) | {joined[t] for t in request_terms if t in joined}
        shared = unique & request_terms
        if not shared:
            return False
        if 2 * len(shared) >= len(unique):
            return True
        if any(a in request_terms and b in request_terms and a != b
               for a, b in zip(title, title[1:])):
            return True
        return len(unique) <= 3 and any(
            counts.get(w) == 1 and len(w) >= 4 and w not in GENERIC_FILE_WORDS for w in shared)

    def admitted_sections(self, chain, partitions, excluded=(), only=None) -> list:
        """The file sections a caller may be given: their file's card is in the caller's
        scope (a file without a card is everyone's, as `get_reference` serves it), not in an
        excluded topic, and not a copy marked superseded."""
        out = []
        for section in self.index.sections.values():
            card = self.index.cards.get(section.path)
            if card is not None:
                if not Scopes.admits(card.scope, card.partition, chain, partitions):
                    continue
                if card.route_key in excluded or (only is not None
                                                  and card.route_key not in only):
                    continue
                if str(card.meta.get("file_status") or "").lower() in RETIRED_FILE_STATES:
                    continue
            elif only is not None:
                continue
            out.append(section)
        return out

    def score_sections(self, request, sections, *, context=None, project=None,
                       composing=False) -> list:
        """How well each section answers the request, best first, each saying in its detail
        whether the request is plainly about it (`plain`; see SECTION_COVERAGE_ALONE and
        GUIDE_SEMANTIC) and why: `named` (the request names its file or project) and `work`
        (a work file, not a guide kept whole). `project` is the route key of the project the
        request names (its id): its files' sections are lifted, as its notes are."""
        if not sections:
            return []
        p = self.policy
        cards = self.index.cards
        keys = [s.id for s in sections]
        bm25 = self.index.section_bm25
        plain_scores = self._hybrid(request, keys, bm25, "section")
        widened = (self._hybrid(f"{request} {context}", keys, bm25, "section")
                   if context else {})
        request_terms = {util.stem(w) for w in util.terms(self.index.fold(request))
                         if w not in util.STOPWORDS}
        ranked = []
        for section in sections:
            score, detail = plain_scores[section.id]
            detail = dict(detail)
            if section.id in widened:
                alt = round(widened[section.id][0] * 0.9, 4)
                if alt > score:
                    score, detail = alt, dict(widened[section.id][1], focus_context=True)
            card = cards.get(section.path)
            owner = self.index.file_project(section.path) if project else None
            in_project = owner is not None and owner.id == project
            coverage = detail.get("coverage", 0.0)
            semantic = detail.get("semantic")
            named = in_project or self._names_file(request_terms, section.path)
            work = card is not None and str(card.meta.get("type") or "") == "file"
            if composing and not named:
                # Writing quotes the material it works on: a file the request names, or one of
                # its project's files. Another file that shares the subject (a deck page on AI
                # leadership for "write a LinkedIn post about AI leadership") is raw material
                # the notes have distilled, and a guide's rules are the house style already.
                plain = False
                if semantic is not None:
                    score = semantic
                # A work file that would have been quoted is listed instead.
                detail["withheld"] = work and (
                    semantic >= SECTION_SEMANTIC if semantic is not None
                    else coverage >= SECTION_COVERAGE_ALONE)
            elif semantic is not None:
                # Meaning decides, and ranks: a close match in other words is a close match.
                score = semantic
                bar = (SECTION_SEMANTIC if work else GUIDE_SEMANTIC) - (
                    NAMED_RELIEF if named else 0.0)
                plain = semantic >= bar
            elif work:
                plain = (coverage >= SECTION_COVERAGE_ALONE
                         or (named and coverage >= SECTION_COVERAGE_NAMED))
            else:
                plain = ((named and coverage >= SECTION_COVERAGE_NAMED)
                         or coverage >= GUIDE_LEXICAL)
            if in_project:
                score += p.project_file_boost
            detail.update(named=named, work=work, plain=plain, project=in_project)
            ranked.append(Scored(section, round(score, 4), detail=detail))
        ranked.sort(key=lambda s: (-s.score, s.item.id))
        return ranked

    def _choose_sections(self, route, context=None, excluded=(), only=None) -> list:
        """Sections of filed documents that answer this request on their own, best first: at
        most `max_sections`, and `max_sections_per_file` from one file.

        A section must clear an absolute bar (`section_floor`) and be plainly what the
        request is about (see SECTION_COVERAGE_ALONE): a writing task that merely shares a
        word or two with a file does not get the file quoted. Sections of the project the
        request names are lifted, as its notes are."""
        sig = route.signals
        p = self.policy
        if sig.edit or not self.index.sections:
            return []
        admitted = self.admitted_sections(route.chain, route.partitions, excluded, only)
        if not admitted:
            return []
        project = route.focus.id if route.focus is not None else None
        ranked = self.score_sections(sig.request, admitted, context=context, project=project,
                                     composing=bool(sig.composing))
        best = ranked[0].score
        bar = max(p.section_floor, best * p.section_relative)
        chosen, per_file = [], {}
        for scored in ranked:
            if scored.score < bar:
                break
            if not scored.detail.get("plain"):
                if scored.detail.get("withheld") and scored.item.path not in route.pointed_files:
                    route.pointed_files.append(scored.item.path)
                continue
            path = scored.item.path
            if per_file.get(path, 0) >= p.max_sections_per_file:
                continue
            per_file[path] = per_file.get(path, 0) + 1
            chosen.append(scored)
            if len(chosen) >= p.max_sections:
                break
        if chosen:
            route.log("sections " + ", ".join(f"{s.item.id} {s.score:.2f}" for s in chosen))
        elif route.pointed_files:
            route.log("sections: a writing task quotes the files it names; listed "
                      + ", ".join(route.pointed_files))
        else:
            route.log(f"sections: none clears {bar:.2f} (best {best:.2f})")
        return chosen

    def _linked(self, route, selected, related, chosen, ranked):
        """Notes a selected note names by id. One it says it contradicts or conflicts with
        travels with it when the request touches it too (both are needed to answer "how
        many learners do we reach?"); any other is listed, not sent. A note loaded "manual"
        (the owner's goals) is neither: naming it does not bring it."""
        admitted = {n.id: n for n in self.admitted_notes(route.chain, route.partitions)
                    if n.load != "manual"}
        relevance = {s.item.id: s.score for s in ranked}
        listed = {s.item.id for s in related}
        out = list(selected)
        for scored in selected:
            for sentence in re.split(r"(?<=[.!?])\s+", scored.item.body):
                for ref in re.findall(r"`([a-z0-9][a-z0-9-]{2,})`", sentence):
                    note = admitted.get(ref)
                    if note is None or ref in chosen or ref == scored.item.id:
                        continue
                    linked = Scored(note, scored.score, [f"named by {scored.item.id}"],
                                    dict(scored.detail, linked_from=scored.item.id))
                    if LINK_CONFLICT.search(sentence.lower())                             and relevance.get(ref, 0.0) >= self.policy.near_floor:
                        out.append(linked)
                        chosen.add(ref)
                        route.log(f"{ref}: in conflict with {scored.item.id}, sent with it")
                    elif ref not in listed:
                        related.insert(0, linked)
                        listed.add(ref)
        return out, [s for s in related if s.item.id not in chosen]

    def _adjust(self, route, ranked, domains, topic_rel=None):
        """Turn raw relevance into a ranking score with the vault's soft signals.

        domain     a topic the task declares (the routed procedure's loads, an intent, the
                   Focus pins, a follow-up's previous topics): a small lift. Centrality to the
                   topic line only orders house style; it never lifts a note over the line
        gate       a topic whose `requires_any` words are all absent from the request
                   is damped, not removed; it can still win on strong evidence, and a note
                   covering `gate_named` of the request's weighted words is not damped
        fit        a topic's `fit_terms` in the request add a little
        topic      how well the note's whole topic matches the request, times `topic_prior`:
                   where a note is filed is evidence, never a gate
        fresh      a note whose text was approved in the last `fresh_days` gets a small
                   lift, so new knowledge is used on the next relevant call (a new title,
                   summary or place is not new knowledge and does not renew it)
        rule       the rules that answer the question get a small lift: the notes that are
                   rules (the vault's constraint kinds) for whether an action is allowed
                   ("can I add a script?"); for how to write ("what should I avoid saying in
                   posts?"), the owner's core writing rules, or the house-style topics when
                   the vault names no core list
        stale      a note past its review (`review_by`, or `review_days` since it was last
                   verified) is multiplied by `stale_factor`: still found, ranked lower,
                   and flagged in the packet until someone verifies it again
        disputed   a note whose confidence is disputed is multiplied by `disputed_factor`
        """
        p = self.policy
        sig = route.signals
        hints = self.config.routing.hints
        today = util.today_date()
        domain_set = set(domains)
        topic_rel = topic_rel or {}
        constraint = self.config.constraint_kinds() or {"rule"}
        # A topic gate asks whether the topic is in play at all, and in a continuation the
        # conversation decides that: "bots are filling it in too" passes the website topic's
        # gate through the contact form asked about before. Fit terms stay the request's own,
        # or every follow-up would lift the previous topics again.
        words, norm = sig.wordset, sig.norm
        if sig.continuation and sig.subject:
            words = words | set(util.terms(sig.subject))
            norm = f"{util.normalize(sig.subject)} {norm}"
        house_topics = set(self.house_style)
        house_notes = set(self.config.routing.house_style_notes)
        for scored in ranked:
            note = scored.item
            topic = note.route_key
            rel = scored.score
            centrality = self.index.centrality(note.id)
            adj = rel + (p.domain_boost if topic in domain_set else 0.0) \
                + p.topic_prior * topic_rel.get(topic, 0.0)
            hint = hints.get(topic) or {}
            # A gate keeps a topic's notes from winning on a loose match. A note that holds
            # most of what the request asks for by name ("the n8n webhook for assessment
            # completions" in the tracking registry) is not a loose match.
            gated = bool(hint.get("requires_any")) and topic not in domain_set and not \
                _hint_hits(words, norm, hint["requires_any"]) and \
                not self._names(sig.request, note.id)
            if gated:
                adj *= p.gate_factor
            fit = _hint_hits(sig.wordset, sig.norm, hint.get("fit_terms"))
            if fit:
                adj += min(p.fit_boost * 2, p.fit_boost * fit)
            fresh, stale, disputed = self._day_facts(note, today)
            if fresh:
                adj += p.fresh_boost
            ruling = (sig.asks_allowed and note.kind in constraint) or (
                sig.style_question and (note.id in house_notes if house_notes
                                        else topic in house_topics))
            if ruling:
                adj += p.rule_boost
            if stale:
                adj *= p.stale_factor
            if disputed:
                adj *= p.disputed_factor
            scored.detail.update({
                "rel": round(rel, 4), "adj": round(adj, 4), "centrality": centrality,
                "blend": round(p.style_relevance * rel + (1 - p.style_relevance) * centrality,
                               4),
                "domain": topic in domain_set,
                "gated": gated, "fresh": fresh, "rule": ruling, "stale": stale,
                "disputed": disputed,
                "topic_rel": round(topic_rel.get(topic, 0.0), 3)})

    def _day_facts(self, note, today) -> tuple:
        """(fresh, stale reason, disputed) of a note today: they change at most once a day,
        and this router lives only as long as the Brain does not change, so they are worked
        out once per note, not on every request for every note."""
        facts = self._facts if self._facts_day == today else None
        if facts is None:
            self._facts, self._facts_day = {}, today
            facts = self._facts
        found = facts.get(note.id)
        if found is None:
            stamp = util.parse_date(note.meta.get("revised") or note.meta.get("approved_at")
                                    or note.meta.get("added"))
            found = (bool(stamp and (today - stamp).days <= self.policy.fresh_days),
                     note.stale_reason(today, self.config.review_days_for(note)),
                     note.confidence == "disputed")
            facts[note.id] = found
        return found

    def _names(self, request, note_id) -> bool:
        """Does the request name this note: at least `gate_named` of its weighted words, and
        two or more of them, are in it? One shared word ("continue the proposal") is not."""
        bm25 = self.index.note_bm25
        return (bm25.coverage(request, note_id) >= self.policy.gate_named
                and bm25.matched(request, note_id) >= 2)

    def _select(self, route, pool, domains, house):
        """Pick the notes specific to this request, most useful first.

        Everything within `select_relative` of the best score and above `note_abs_floor`
        goes in, at most a few per topic so one folder cannot crowd out the rest. A one-answer
        lookup is stricter. Each declared domain the ranking missed gets its best note when
        that note is genuinely relevant (or always, when an intent names the topic). The next
        few notes are returned as `related`: listed by title, not sent.
        """
        p = self.policy
        sig = route.signals
        if not pool:
            return [], []
        # The bar is set by relevance. Freshness lifts a new note into the packet; it does not
        # raise the bar under everything else (a just-edited rule pushing out its neighbours).
        micro_lookup = route.task_type == "knowledge" and route.scale == "micro"
        calibrated = self.calibrated("note_abs_floor")
        eligible = [s for s in pool if not calibrated or (
            self.evidence(s) > self.share("note")
            and (not s.detail.get("gated") or s.detail["adj"] >= p.note_abs_floor))]
        best = max((s.detail["adj"] - (p.fresh_boost if s.detail.get("fresh") else 0.0)
                    for s in pool), default=0.0)
        if calibrated:
            factor = p.whole_relative
        else:
            factor = p.micro_relative if micro_lookup else p.select_relative
        threshold = best * factor if calibrated else max(p.note_abs_floor, best * factor)
        # A rejected top match must not make the whole brief empty when a qualified
        # candidate remains. Recover only the strongest qualifying score; lowering
        # the cutoff for a whole new group adds unnecessary context. Others stay pointers.
        if calibrated and eligible and not any(s.detail["adj"] >= threshold for s in eligible):
            threshold = max(s.detail["adj"] for s in eligible)
        route.select_threshold = threshold
        cap = {"micro": p.per_topic_micro, "deep": p.per_topic_deep}.get(
            route.scale, p.per_topic_standard)
        selected, per_topic = [], {}
        for scored in pool:
            if scored.detail["adj"] < threshold:
                break
            if calibrated and self.evidence(scored) <= self.share("note"):
                continue
            # A topic gate is hand configuration: a gated note still needs the hand-set floor.
            if calibrated and scored.detail.get("gated") and scored.detail["adj"] < p.note_abs_floor:
                continue
            topic = scored.item.route_key
            if per_topic.get(topic, 0) >= cap:
                continue
            selected.append(scored)
            per_topic[topic] = per_topic.get(topic, 0) + 1
        if micro_lookup:
            selected = selected[:p.micro_max_notes]
            per_topic = {}
            for scored in selected:
                per_topic[scored.item.route_key] = per_topic.get(scored.item.route_key, 0) + 1
        named = set(sig.include_topics)
        for domain in domains:
            if domain in house or per_topic.get(domain):
                continue
            members = [s for s in pool if s.item.route_key == domain]
            if not members:
                continue
            if self.calibrated("topic_note_floor"):
                weak = max(self.evidence(s) for s in members) <= self.share("note")
            else:
                weak = max(s.score for s in members) < p.topic_note_floor
            if weak and domain not in named:
                route.log(f"{domain}: declared, but no note is specific to this request")
                continue
            picks = members[:2 if domain in named else 1]
            selected += picks
            per_topic[domain] = len(picks)
            route.log(f"{domain}: best note added for coverage ({picks[0].item.id})")
        chosen = {s.item.id for s in selected}
        # "Also relevant" means relevant: a note under the floor no selection would take is
        # not listed either, however low the bar for this request went.
        # Calibrated, a pointer is any next note that clears the related bar: the tiers
        # put what is not confident enough to send whole here, one get_note away.
        related_bar = (0.0 if calibrated
                       else max(p.note_abs_floor, threshold * p.related_factor))
        related = [s for s in pool if s.item.id not in chosen
                   and s.detail["adj"] >= related_bar
                   and (not calibrated or self.evidence(s) > self.share("related"))
                   ]
        route.related_pool = related
        route.log(f"selected {len(selected)} note(s) at or above {threshold:.2f}; "
                  f"{min(len(related), p.related_count)} related listed")
        return selected, related[:p.related_count]

    def _rerank(self, route, request, ranked) -> list:
        """Let the cross-encoder reread the best candidates and shift their scores.

        It reads the request and each note together, which catches matches the separate
        vectors miss. Its verdicts are compared among the candidates (z-scores) and shift each
        candidate's place by `rerank_weight` per standard deviation. Notes past the first
        `rerank_k` keep their places. Without the model, nothing changes."""
        p = self.policy
        if self.reranker is None or p.rerank_weight <= 0 or len(ranked) < 3:
            return ranked
        top = ranked[:p.rerank_k]
        texts = [f"{s.item.title}. {s.item.summary} {s.item.body}"[:p.rerank_chars]
                 for s in top]
        try:
            raw = self.reranker.score(request, texts)
        except Exception as exc:
            route.log(f"reranker skipped: {exc}")
            return ranked
        if not raw:
            return ranked
        mean = sum(raw) / len(raw)
        spread = (sum((r - mean) ** 2 for r in raw) / len(raw)) ** 0.5
        if spread < 1e-6:
            return ranked
        zs = [max(-2.0, min(2.0, (value - mean) / spread)) for value in raw]
        # The reranker decides the ORDER among close competitors; the scores themselves keep
        # their values. The best score, and with it every relative threshold, is unchanged,
        # and a shift of at most 2 x rerank_weight can only reorder near-ties.
        order = sorted(range(len(top)),
                       key=lambda i: (-(top[i].score + p.rerank_weight * zs[i]),
                                      top[i].item.id))
        slots = sorted((s.score for s in top), reverse=True)
        out = []
        for slot, i in zip(slots, order):
            scored = top[i]
            out.append(Scored(scored.item, slot, scored.reasons,
                              dict(scored.detail, hybrid=scored.score, ce=round(raw[i], 2),
                                   ce_z=round(zs[i], 2))))
        out += ranked[p.rerank_k:]
        moved = sum(1 for a, b in zip(out, top) if a.item.id != b.item.id)
        route.log(f"reranker reread the top {len(top)} candidates; {moved} changed place")
        return out

    def _focus_topics(self, focus) -> list[str]:
        """Topics a named Focus declares: its pinned notes' topics, and its own project folder
        when other notes are filed there (the project's decisions and client guidance)."""
        out = []
        for note_id in focus.pinned_notes:
            note = self.index.note(note_id)
            if note is not None and note.route_key not in out:
                out.append(note.route_key)
        own = focus.note.route_key
        if own not in out and any(n.route_key == own and not self.config.is_focus(n)
                                  for n in self.index.notes.values()):
            out.append(own)
        return out

    def _requested_references(self, sig, notes) -> list[str]:
        """References the request asks to read in full, matched on title and path words."""
        from .index import BM25
        refs = self.index.references
        if not refs:
            return []
        docs = {path: f"{path.replace('/', ' ').replace('-', ' ')} {ref.title}"
                for path, ref in refs.items()}
        # Does the request NAME this document? Words no title uses ("rewrite this
        # paragraph") are ordinary here, not evidence against it.
        bm = BM25(docs, unseen_idf=1.0, fold=self.index.fold)
        scored = sorted(((bm.coverage(sig.request, path), path) for path in docs),
                        reverse=True)
        best = scored[0][0] if scored else 0.0
        if best < 0.3:
            return []
        return [path for score, path in scored if score >= max(0.3, best - 0.05)][:2]


_EDIT_STEMS = util.stems(EDIT_VOCABULARY | ANAPHORA | CONTINUATION_WORDS)
_EDIT_PHRASES = re.compile(r"\b(?:" + "|".join(
    re.escape(p).replace(r"\ ", r"[\s-]+") for p in EDIT_PHRASES) + r")\b", re.IGNORECASE)


def _without_edit_phrases(text: str) -> str:
    """The request with the document parts it names in several words taken out."""
    return _EDIT_PHRASES.sub(" ", str(text or ""))


def _refers_back(sig: Signals) -> str | None:
    """Does the request lean on the conversation for what it is about? "cue" when a word
    points back (an editing verb, "and ...", "it", "too"), "short" when it is a short request
    with almost no subject of its own ("is there a known workaround?"), else None."""
    if EDIT_START.match(sig.text) or CONTINUATION_START.match(sig.text):
        return "cue"
    if sig.wordset & (ANAPHORA | CONTINUATION_WORDS):
        return "cue"
    if len(sig.words) <= 8 and len(util.content_terms(sig.request)) <= 2 \
            and not _names_its_subject(sig.request):
        return "short"
    return None


def _names_its_subject(request: str) -> bool:
    """A short question that names its own subject ("what's the capital of Portugal?",
    "what's our UTM for LinkedIn?") is not elliptical: a capitalized name past the first
    word, or an acronym, is a subject of its own."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9'&-]*", str(request or ""))
    for position, word in enumerate(words):
        if len(word) >= 2 and word.isupper():
            return True
        if position and word[0].isupper() and word.lower() not in ("i", "i'm", "i've", "i'd",
                                                                    "i'll"):
            return True
    return False


def _shared_loads(skills) -> list[str]:
    """Topics loaded by enough of the credible skills to count as a shared prerequisite."""
    if not skills:
        return []
    if len(skills) == 1:
        return list(skills[0].load_topics)
    threshold = max(2, (len(skills) + 1) // 2)
    counts: dict[str, int] = {}
    order: list[str] = []
    for skill in skills:
        for topic in skill.load_topics:
            if topic not in counts:
                order.append(topic)
            counts[topic] = counts.get(topic, 0) + 1
    return [t for t in order if counts[t] >= threshold]




