"""The retrieval engine: a gate, a wide find, a relevance cut, a second pass and a link loop,
then fit (brain-logic plan 5.11).

It is ON only when a verified local model service is ready (`models_client.status`): a
reranker for relevance and a decision model (Kev) for typed questions, both pinned by the lock.
Otherwise retrieval runs exactly as it does without the engine, and the engine only writes down
what exists: each candidate's keyword and meaning scores, the outcome and its reason, marked
"engine: fallback".

    1. GATE (decision model): should this request get anything from the Brain at all? A no is
       one line; the must-holds whose domain is in play still go.
    2. FIND: every note and document part above a loose meaning floor, what the request names,
       the router's own picks and the house style for writing. No count cap: a ceiling only
       protects speed, and the ledger says when a request hits it.
    3. RELEVANCE CUT (reranker): every candidate scored against the instruction ("would this
       help an AI do this task?"); what clears the cut survives. If nothing does, the brief is
       one line.
    4. SECOND PASS (decision model, survivors only): does it add anything a better one does not
       cover; does it contradict one (both then travel, as a disputed pair); is it current;
       which must-hold domains the request touches.
    5. LINK LOOP: notes and document parts the survivors name that were not candidates go
       through 3 and 4; it stops when a round adds nothing above the cut, after three rounds
       at most.
    6. FIT: everything that survived goes in, best first; what does not fit the budget becomes
       a pointer (a title and a line) the AI can open. Nothing relevant is dropped.

Must-holds bypass relevance: the gate and the cut never remove one whose domain is in play.
Every decision's scores go to the ledger with the lock's fingerprint, so "why this note" and
"why not that one" are read back, never recomputed. The cuts live in brain.json (`engine`),
with the date and the eval run they were fitted on; until then they are starting points.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import models_client, util
from .router import MustHold, Scored

# Starting points, until fitted on the labeled set on a machine that runs the models
# (5.11.10): probabilities and scores from 0 to 1.
CUTS = {
    "gate": 0.5,         # P(the Brain holds something for this request): below it, one line
    "relevance": 0.5,    # the reranker's score: below it, out
    "adds": 0.5,         # P(a better survivor already says it): at or above, out
    "contradicts": 0.7,  # P(it contradicts a better survivor): at or above, a disputed pair
    "current": 0.5,      # P(still current): below it, kept and flagged
    "domain": 0.5,       # P(the request touches a must-hold domain): at or above, it attaches
}
FLOOR = 0.15             # the loose meaning floor of the find step
CEILING = 300            # candidates scored at most, a speed guard only
ROUNDS = 3               # link-loop rounds at most
INSTRUCTION = "Judge whether this note would help an AI do this task"
STATE_NOTES = 40         # survivors the second pass shows in its shared state
BATCH = 64               # questions in one decision request
TEXT_CHARS = 1500        # of a candidate's text the reranker reads
SHORT_CHARS = 300        # of a candidate's text the decision model reads
POINTER_WORDS = 14       # the line after a pointer's title
LOGGED = 40              # in fallback, scored notes written down at most
NOTHING = ("Nothing in this Brain applies to this request: answer from general knowledge, and "
           "say the Brain had nothing on it.")
# Routes the engine leaves to code: an exact address, a project's own state, the portfolio,
# questions about the Brain itself, the map, a permission question answered by the rules.
CODE_ROUTES = ("exact-note", "exact-skill", "focus-only", "focus-update", "portfolio",
               "system", "orientation", "standing")
_NAMED = re.compile(r"`([a-z0-9][a-z0-9-]{2,})`")


LAYERS = {"gate": True, "second_pass": True, "loop": True}
SCORERS = ("rerank", "decide")  # what scores relevance: the reranker, or the decision model


@dataclass
class Settings:
    """A Brain's engine settings: brain.json `engine`, over the starting points. `enabled`
    false keeps this Brain on the fallback even with a model service; `layers` and `scorer`
    are how the comparison (5.11.11) runs setups B to E."""
    cuts: dict = field(default_factory=lambda: dict(CUTS))
    floor: float = FLOOR
    ceiling: int = CEILING
    rounds: int = ROUNDS
    instruction: str = INSTRUCTION
    fitted: dict = field(default_factory=dict)  # {"date", "eval_run"} the cuts came from
    enabled: bool = True
    layers: dict = field(default_factory=lambda: dict(LAYERS))
    scorer: str = "rerank"
    ceiling_set: bool = False  # brain.json names a ceiling (else the machine setup's)

    @classmethod
    def of(cls, config) -> Settings:
        data = config.data.get("engine") or {}
        cuts = dict(CUTS)
        for key, value in (data.get("cuts") or {}).items():
            if key in cuts:
                try:
                    cuts[key] = min(1.0, max(0.0, float(value)))
                except (TypeError, ValueError):
                    continue

        def number(key, default, kind=float):
            try:
                return kind(data.get(key, default))
            except (TypeError, ValueError):
                return default

        layers = dict(LAYERS)
        layers.update({k: bool(v) for k, v in (data.get("layers") or {}).items()
                       if k in LAYERS})
        scorer = str(data.get("scorer") or "rerank")
        return cls(cuts=cuts, floor=number("floor", FLOOR),
                   ceiling=max(1, number("ceiling", CEILING, int)),
                   rounds=min(ROUNDS, max(0, number("rounds", ROUNDS, int))),
                   instruction=str(data.get("instruction") or INSTRUCTION),
                   fitted=dict(data.get("fitted") or {}),
                   enabled=data.get("enabled", True) is not False,
                   layers=layers, scorer=scorer if scorer in SCORERS else "rerank",
                   ceiling_set="ceiling" in data)


@dataclass
class Candidate:
    """One note or document part the engine looked at, and what became of it."""
    kind: str                       # note | section
    item: object
    keyword: float | None = None    # the lexical part of its match
    meaning: float | None = None    # its meaning score (None without embeddings)
    hybrid: float = 0.0             # what the find step ranked it by
    found_by: str = ""
    rerank: float | None = None
    kev: dict = field(default_factory=dict)  # question: probability, or option probabilities
    outcome: str = "out"            # body | pointer | listed | held | out
    reason: str = ""
    round: int = 0

    @property
    def id(self) -> str:
        return str(getattr(self.item, "id", ""))

    def row(self) -> dict:
        return {"kind": self.kind, "item": self.id, "keyword": _round(self.keyword),
                "meaning": _round(self.meaning), "rerank": _round(self.rerank),
                "kev": self.kev, "outcome": self.outcome, "reason": self.reason,
                "found_by": self.found_by, "round": self.round}


def _round(value):
    return None if value is None else round(float(value), 4)


@dataclass
class Audit:
    """What the engine did for one brief: what the ledger keeps (5.11.9)."""
    mode: str                       # on | fallback
    lock: str = ""
    reason: str = ""                # why fallback, or why the brief is one line
    gate: dict | None = None        # {"yes": p, "cut": c, "passed": bool}
    cuts: dict = field(default_factory=dict)
    fitted: dict = field(default_factory=dict)
    timings: dict = field(default_factory=dict)  # layer: milliseconds
    ceiling_hit: bool = False
    rounds: int = 0
    domains: dict = field(default_factory=dict)  # must-hold domain: P(the request touches it)
    candidates: list = field(default_factory=list)
    notes: list = field(default_factory=list)    # fallbacks of this machine's setup, in words
    refit: bool = False                          # the cuts were fitted for other models

    def summary(self) -> dict:
        counts: dict = {}
        for c in self.candidates:
            counts[c.outcome] = counts.get(c.outcome, 0) + 1
        return {"mode": self.mode, "lock": self.lock, "reason": self.reason, "gate": self.gate,
                "cuts": self.cuts, "fitted": self.fitted, "timings": self.timings,
                "ceiling_hit": self.ceiling_hit, "rounds": self.rounds,
                "domains": self.domains, "candidates": len(self.candidates),
                "outcomes": counts, "notes": self.notes, "refit": self.refit}

    def rows(self) -> list[dict]:
        return [c.row() for c in self.candidates]

    def settle(self, data: dict) -> None:
        """Each candidate's outcome as the brief shows it: whole, in short, listed, already
        held, or out (with the reason it was out, when the engine did not give one)."""
        bodies = set(data.get("note_ids") or []) - set(data.get("pointer_ids") or [])
        pointers = set(data.get("pointer_ids") or [])
        listed = set(data.get("related_ids") or [])
        held = set(data.get("held_ids") or []) | set(data.get("held_section_ids") or [])
        sections = set(data.get("section_ids") or [])
        for c in self.candidates:
            if c.kind == "note" and c.id in bodies:
                c.outcome = "body"
            elif c.kind == "note" and c.id in pointers:
                c.outcome = "pointer"
            elif c.kind == "section" and c.id in sections:
                c.outcome = "body" if c.outcome != "pointer" else "pointer"
            elif c.id in held:
                c.outcome, c.reason = "held", c.reason or "already in this conversation"
            elif c.kind == "note" and c.id in listed:
                c.outcome = "listed"
                c.reason = c.reason or "listed as also relevant, not sent"
            elif c.outcome in ("body", "pointer") and c.kind == "section":
                continue
            else:
                if c.outcome != "out":
                    c.reason = c.reason or "over budget"
                c.outcome = "out"
                c.reason = c.reason or "below the router's bar"


# ---------------------------------------------------------------------------- fallback

def lexical(detail: dict) -> float | None:
    """The keyword part of a router score: its coverage of the request's words."""
    value = (detail or {}).get("coverage")
    return None if value is None else float(value)


def fallback(route, reason: str, lock: str = "") -> Audit:
    """What exists without the engine, written down; the route is never touched."""
    audit = Audit(mode="fallback", lock=lock, reason=reason)
    seen: set = set()

    def add(scored, found_by):
        item = scored.item
        if item.id in seen:
            return
        seen.add(item.id)
        audit.candidates.append(Candidate(
            kind="note", item=item, keyword=lexical(scored.detail),
            meaning=(scored.detail or {}).get("semantic"), hybrid=float(scored.score),
            found_by=found_by))

    for scored in route.style_notes:
        add(scored, "house style")
    for scored in route.notes:
        add(scored, "the router's pick")
    for scored in route.related:
        add(scored, "a near match")
    for scored in (getattr(route, "ranked", None) or [])[:LOGGED]:
        add(scored, "scored")
    for scored in route.sections:
        audit.candidates.append(Candidate(
            kind="section", item=scored.item, keyword=lexical(scored.detail),
            meaning=(scored.detail or {}).get("semantic"), hybrid=float(scored.score),
            found_by="the router's pick"))
    return audit


# ---------------------------------------------------------------------------- the engine

class Engine:
    """The pipeline for one Brain state, with its two models."""

    def __init__(self, st, settings: Settings, reranker, decider, lock: str,
                 status: models_client.Status | None = None):
        self.st = st
        self.router = st.router
        self.settings = settings
        self.reranker = reranker
        self.decider = decider
        self.lock = lock
        self.notes: list[str] = []  # what the audit says about this run's setup
        found = status or models_client.Status()
        decider_name = (found.roles.get("decide") or {}).get("model") or "the decision model"
        # A decision model runs a Kev step only once it qualified for it here (5.11.15).
        for step in ("gate", "second_pass"):
            if found.qualified and not found.qualified.get(step, True) \
                    and settings.layers.get(step):
                settings.layers[step] = False
                self.notes.append(
                    f"{decider_name} has not qualified for the "
                    f"{'gate' if step == 'gate' else 'second pass'} here: "
                    + ("the reranker's best score against the cut decides instead"
                       if step == "gate" else "it is skipped"))
        if not settings.ceiling_set and found.ceiling:
            settings.ceiling = int(found.ceiling)
        # Cuts fitted for other models no longer hold: the defaults stand in, and a refit is
        # suggested (5.11.16).
        running = {role: (found.roles.get(role) or {}).get("model")
                   for role in ("rerank", "decide")}
        fitted_for = settings.fitted.get("models") or {}
        self.refit = bool(fitted_for) and any(
            fitted_for.get(role) and fitted_for.get(role) != running.get(role)
            for role in running)
        if self.refit:
            settings.cuts = dict(CUTS)
            self.notes.append("the cuts were fitted for other models: the defaults stand in, "
                              "and a refit on this Brain's labels is suggested")

    @classmethod
    def connect(cls, st, *, status: models_client.Status | None = None):
        """The engine when a verified model service is ready, else (None, why not)."""
        settings = Settings.of(st.config)
        if not settings.enabled:
            return None, models_client.Status(reason="the engine is off for this Brain "
                                                     "(brain.json engine.enabled)")
        found = status or models_client.status()
        if not found.ready:
            return None, found
        return cls(st, settings, models_client.Reranker(found),
                   models_client.Decider(found), found.lock, found), found

    # ------------------------------------------------------------------ the pipeline
    def refine(self, route) -> Audit:
        s = self.settings
        audit = Audit(mode="on", lock=self.lock, cuts=dict(s.cuts), fitted=dict(s.fitted),
                      notes=list(self.notes), refit=self.refit)
        if route.mode in CODE_ROUTES:
            audit.reason = f"routed by code ({route.mode})"
            return audit
        started = time.perf_counter()
        gate = True
        if s.layers["gate"] or s.layers["second_pass"]:
            gate = self._gate(route, audit, ask=s.layers["gate"],
                              domains=s.layers["second_pass"])
        audit.timings["gate"] = _ms(started)
        if not gate:
            self._nothing(route, f"the gate: {audit.gate['yes']:.2f} < {s.cuts['gate']}")
            audit.reason = "the gate said no"
            return audit
        started = time.perf_counter()
        candidates = self._find(route, audit)
        audit.timings["find"] = _ms(started)
        started = time.perf_counter()
        survivors = self._cut(route, candidates)
        audit.timings["cut"] = _ms(started)
        if not s.layers["gate"]:
            # Without the decision model's gate, the reranker's best score against the cut
            # decides whether the request gets anything (5.11.15).
            best = max((c.rerank or 0.0 for c in candidates), default=0.0)
            audit.gate = {"by": "reranker", "yes": round(best, 4),
                          "cut": s.cuts["relevance"], "passed": bool(survivors)}
        started = time.perf_counter()
        if s.layers["second_pass"]:
            survivors = self._second_pass(route, survivors, survivors)
        seen = {(c.kind, c.id) for c in candidates}
        for number in range(1, (s.rounds if s.layers["loop"] else 0) + 1):
            fresh = self._linked(route, survivors, seen, number)
            if not fresh:
                break
            audit.rounds = number
            audit.candidates += fresh
            kept = self._cut(route, fresh)
            if s.layers["second_pass"]:
                kept = self._second_pass(route, kept, survivors)
            if not kept:
                break  # a round that adds nothing above the cut ends the loop
            survivors = survivors + kept
        audit.timings["second_pass"] = _ms(started)
        if not survivors and not route.must_holds:
            self._nothing(route, "nothing cleared the relevance cut")
            audit.reason = "nothing cleared the relevance cut"
            return audit
        started = time.perf_counter()
        self._fit(route, survivors)
        audit.timings["fit"] = _ms(started)
        return audit

    # ------------------------------------------------------------------ 1. the gate
    def _gate(self, route, audit: Audit, *, ask: bool = True, domains: bool = True) -> bool:
        """The gate's yes or no and, in the same call, the second pass's question of which
        must-hold domains the request touches (asked early, so their must-holds attach before
        the find). `ask` and `domains` follow the steps this machine runs."""
        s = self.settings
        open_domains = self._domains_open(route) if domains else {}
        questions = {}
        if ask:
            questions["gate"] = models_client.noul(
                "Would anything kept in this Brain help with this request? Answer no when the "
                "request is about something the Brain does not cover: general knowledge, "
                "someone else's work, or code outside the Brain's own projects.")
        for key, name in open_domains.items():
            questions[f"domain.{key}"] = models_client.noul(
                f"Does the request touch {name}?")
        if not questions:
            return True
        answers = self.decider.ask({"request": route.request, "brain": self._map()},
                                   questions)
        for key in open_domains:
            touched = models_client.yes(answers.get(f"domain.{key}"))
            audit.domains[key] = round(touched, 4)
            if touched >= s.cuts["domain"]:
                self._attach_domain(route, key, touched)
        if not ask:
            return True
        p = models_client.yes(answers.get("gate"))
        audit.gate = {"yes": round(p, 4), "cut": s.cuts["gate"], "passed": p >= s.cuts["gate"]}
        return p >= s.cuts["gate"]

    def _map(self) -> list[dict]:
        """A short map of the Brain: its areas with what each is for, and its projects."""
        config = self.st.config
        out = [{"area": str(spec.get("label") or key),
                "about": util.excerpt(spec.get("description") or "", 120)}
               for key, spec in (config.areas or {}).items()]
        out += [{"project": f.title} for f in self.st.index.focuses.values() if f.active][:30]
        return out

    def _domains_open(self, route) -> dict:
        """Must-hold domains whose must-holds are not in play yet: {key: name}."""
        from . import kernel
        in_play = {m.note.id for m in route.must_holds + route.must_overflow}
        out = {}
        for note in kernel.must_hold_notes(self.st.index, route.chain, route.partitions):
            if note.id in in_play:
                continue
            for key, name in kernel._domains(self.st.config, self.st.index, note):
                if key != "*":
                    out.setdefault(key, name)
        return dict(list(out.items())[:24])

    def _attach_domain(self, route, key: str, probability: float) -> None:
        """The decision model read the request as touching a must-hold domain: its must-holds
        attach (they are never removed, only added)."""
        from . import kernel
        in_play = {m.note.id for m in route.must_holds + route.must_overflow}
        for note in kernel.must_hold_notes(self.st.index, route.chain, route.partitions):
            if note.id in in_play:
                continue
            if any(k == key for k, _n in kernel._domains(self.st.config, self.st.index, note)):
                route.must_holds.append(MustHold(
                    note=note, why=f"the request touches {key} ({probability:.2f})"))
                in_play.add(note.id)

    # ------------------------------------------------------------------ 2. find
    def _find(self, route, audit: Audit) -> list[Candidate]:
        s = self.settings
        router = self.router
        named = route.focus.id if route.focus is not None else None
        admitted = router.admitted_notes(route.chain, route.partitions)
        on_demand = [n for n in admitted if not n.standing and n.id != named]
        context = (f"{route.focus.title} {route.focus.note.index_line}"
                   if route.focus is not None else None)
        picks = {sc.item.id: "the router's pick" for sc in route.notes}
        picks.update({sc.item.id: "house style" for sc in route.style_notes})
        picks.update({sc.item.id: "a near match" for sc in route.related})
        found: list[Candidate] = []
        for scored in router.score_notes(route.request, on_demand, context):
            item = scored.item
            why = picks.get(item.id)
            if why is None and router._names(route.request, item.id):
                why = "named in the request"
            if why is None and scored.score >= s.floor:
                why = "above the meaning floor"
            if why is None:
                continue
            found.append(Candidate("note", item, keyword=lexical(scored.detail),
                                   meaning=scored.detail.get("semantic"),
                                   hybrid=float(scored.score), found_by=why))
        sections = router.admitted_sections(route.chain, route.partitions)
        project = route.focus.id if route.focus is not None else None
        for scored in router.score_sections(route.request, sections, context=context,
                                            project=project):
            if scored.score < s.floor:
                continue
            found.append(Candidate("section", scored.item, keyword=lexical(scored.detail),
                                   meaning=scored.detail.get("semantic"),
                                   hybrid=float(scored.score), found_by="above the meaning floor"))
        found.sort(key=lambda c: (c.found_by == "above the meaning floor", -c.hybrid, c.id))
        if len(found) > s.ceiling:
            audit.ceiling_hit = True
            for c in found[s.ceiling:]:
                c.reason = f"past the ceiling of {s.ceiling} candidates"
            audit.candidates = list(found)
            found = found[:s.ceiling]
        else:
            audit.candidates = list(found)
        return found

    # ------------------------------------------------------------------ 3. the relevance cut
    def _cut(self, route, candidates: list[Candidate]) -> list[Candidate]:
        cut = self.settings.cuts["relevance"]
        texts = [self._text(c, TEXT_CHARS) for c in candidates]
        if self.settings.scorer == "decide":
            scores = self._decide_relevance(route, texts)
        else:
            scores = self.reranker.scores(route.request, texts, self.settings.instruction)
        survivors = []
        for c, score in zip(candidates, scores, strict=False):
            c.rerank = float(score)
            if c.rerank >= cut:
                survivors.append(c)
            else:
                c.outcome, c.reason = "out", f"below the relevance cut ({c.rerank:.2f} < {cut})"
        survivors.sort(key=lambda c: (-(c.rerank or 0.0), c.id))
        return survivors

    def _decide_relevance(self, route, texts: list[str]) -> list[float]:
        """Setup E: the decision model scores relevance, one yes/no question per candidate,
        each reading the request and itself."""
        questions = {f"rel.{i}": models_client.noul(
            f"{self.settings.instruction}? The note: {text}") for i, text in enumerate(texts)}
        answers: dict = {}
        names = list(questions)
        for start in range(0, len(names), BATCH):
            part = {k: questions[k] for k in names[start:start + BATCH]}
            answers.update(self.decider.ask({"request": route.request}, part))
        return [models_client.yes(answers.get(f"rel.{i}")) for i in range(len(texts))]

    # ------------------------------------------------------------------ 4. the second pass
    def _second_pass(self, route, fresh: list[Candidate], ranked: list[Candidate]) -> list:
        """Ask the typed questions of `fresh` survivors against the better ones in `ranked`
        (all survivors so far, best first). Returns the fresh ones that stay."""
        if not fresh:
            return []
        s = self.settings
        order = sorted({id(c): c for c in ranked + fresh}.values(),
                       key=lambda c: (-(c.rerank or 0.0), c.id))
        shown = order[:STATE_NOTES]
        keys = {id(c): f"n{i + 1}" for i, c in enumerate(shown)}
        state = {"request": route.request,
                 "notes": [{"key": keys[id(c)], "title": self._title(c),
                            "text": self._text(c, SHORT_CHARS)} for c in shown]}
        questions: dict = {}
        for c in fresh:
            mine = keys.get(id(c))
            name = mine or "the note below"
            better = [b for b in order if (b.rerank or 0.0) > (c.rerank or 0.0)
                      and b is not c and id(b) in keys][:254]
            about = "" if mine else f" The note: {self._text(c, SHORT_CHARS)}"
            if better:
                options = {"none": "None of them: it adds something new"}
                options.update({keys[id(b)]: self._title(b) for b in better})
                questions[f"adds.{c.kind}.{c.id}"] = models_client.choice(
                    f"Which earlier note already says what {name} says?{about}", options)
                options = {"none": "It contradicts none of them"}
                options.update({keys[id(b)]: self._title(b) for b in better})
                questions[f"contradicts.{c.kind}.{c.id}"] = models_client.choice(
                    f"Which earlier note does {name} contradict?{about}", options)
            questions[f"current.{c.kind}.{c.id}"] = models_client.noul(
                f"Is what {name} says still current, not replaced by something newer?{about}")
        answers: dict = {}
        names = list(questions)
        for start in range(0, len(names), BATCH):
            part = {k: questions[k] for k in names[start:start + BATCH]}
            answers.update(self.decider.ask(state, part))
        by_key = {keys[id(c)]: c for c in shown}
        kept = []
        for c in fresh:
            adds = models_client.probabilities(answers.get(f"adds.{c.kind}.{c.id}"))
            against = models_client.probabilities(answers.get(f"contradicts.{c.kind}.{c.id}"))
            current = answers.get(f"current.{c.kind}.{c.id}")
            if adds:
                c.kev["adds"] = {k: round(v, 4) for k, v in adds.items()}
            if against:
                c.kev["contradicts"] = {k: round(v, 4) for k, v in against.items()}
            if current is not None:
                c.kev["current"] = round(models_client.yes(current), 4)
            covered = max(((k, v) for k, v in adds.items() if k != "none"),
                          key=lambda kv: kv[1], default=(None, 0.0))
            clash = max(((k, v) for k, v in against.items() if k != "none"),
                        key=lambda kv: kv[1], default=(None, 0.0))
            if clash[0] and clash[1] >= s.cuts["contradicts"] and clash[0] in by_key:
                other = by_key[clash[0]]
                c.reason = f"disputed with {other.id}: both travel"
                c.kev["disputed_with"] = other.id
                other.kev.setdefault("disputed_with", c.id)
                kept.append(c)
                continue
            if covered[0] and covered[1] >= s.cuts["adds"] and covered[0] in by_key:
                c.outcome = "out"
                c.reason = f"adds nothing beyond {by_key[covered[0]].id}"
                continue
            if current is not None and models_client.yes(current) < s.cuts["current"]:
                c.reason = "may be out of date"
            kept.append(c)
        return kept

    # ------------------------------------------------------------------ 5. the link loop
    def _linked(self, route, survivors: list[Candidate], seen: set, number: int) -> list:
        """Notes and document parts the survivors name that were not candidates yet."""
        router = self.router
        admitted = {n.id: n for n in router.admitted_notes(route.chain, route.partitions)}
        sections = router.admitted_sections(route.chain, route.partitions)
        by_path: dict = {}
        for section in sections:
            by_path.setdefault(section.path, []).append(section)
        fresh: list[Candidate] = []
        for c in survivors:
            if c.kind != "note":
                continue
            body = str(getattr(c.item, "body", "") or "")
            for ref in dict.fromkeys(_NAMED.findall(body)):
                note = admitted.get(ref)
                if note is None or note.standing or ("note", ref) in seen:
                    continue
                seen.add(("note", ref))
                fresh.append(Candidate("note", note, found_by=f"linked from {c.id}",
                                       round=number))
            for path in getattr(c.item, "references", []) or []:
                for section in by_path.get(path, []):
                    if ("section", section.id) in seen:
                        continue
                    seen.add(("section", section.id))
                    fresh.append(Candidate("section", section, found_by=f"linked from {c.id}",
                                           round=number))
        if fresh:
            scored = {s.item.id: s for s in router.score_notes(
                route.request, [c.item for c in fresh if c.kind == "note"])}
            for c in fresh:
                found = scored.get(c.id)
                if found is not None:
                    c.keyword, c.meaning = lexical(found.detail), found.detail.get("semantic")
                    c.hybrid = float(found.score)
        return fresh

    # ------------------------------------------------------------------ 6. fit
    def _fit(self, route, survivors: list[Candidate]) -> None:
        """Everything that survived, best first; the brief builder turns what does not fit
        the budget into pointers (`route.engine_fit`), never drops."""
        notes = [c for c in survivors if c.kind == "note"]
        parts = [c for c in survivors if c.kind == "section"]
        route.notes = [Scored(c.item, round(c.rerank or 0.0, 4), ["the engine"],
                              {"rerank": c.rerank, "engine": True}) for c in notes]
        route.style_notes = []
        route.related = []
        route.sections = [Scored(c.item, round(c.rerank or 0.0, 4), ["the engine"],
                                 {"rerank": c.rerank, "engine": True, "plain": True})
                          for c in parts]
        if route.mode == "lean":
            route.mode = "standard"
        route.engine_fit = {c.id: "body" for c in survivors}
        route.engine_disputed = {c.id: c.kev["disputed_with"] for c in survivors
                                 if c.kev.get("disputed_with")}
        route.log(f"engine: {len(notes)} note(s), {len(parts)} document part(s) above the cut")

    def _nothing(self, route, why: str) -> None:
        route.mode = "nothing"
        route.notes, route.style_notes, route.related, route.sections = [], [], [], []
        route.standing_answer, route.candidates, route.references = [], [], []
        route.skill, route.procedure = None, "none"
        route.engine_fit = {}
        route.log(f"engine: one line ({why})")

    # ------------------------------------------------------------------ texts
    def _title(self, c: Candidate) -> str:
        if c.kind == "section":
            return f"{self.st.index.file_title(c.item.path)}: {c.item.heading}"
        return str(getattr(c.item, "title", "") or c.id)

    def _text(self, c: Candidate, chars: int) -> str:
        if c.kind == "section":
            body = str(getattr(c.item, "text", "") or "")
        else:
            summary = str(getattr(c.item, "summary", "") or "")
            body = f"{summary}\n{getattr(c.item, 'body', '') or ''}"
        return f"[{c.id}] {self._title(c)}\n{util.excerpt(body, chars)}"


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def pointer(note) -> str:
    """A note that did not fit the budget: its title and id and a line, about 20 tokens."""
    name = note.title if note.meta.get("title") else note.id
    line = " ".join(str(note.summary or "").split()[:POINTER_WORDS])
    return f"- {name} (`{note.id}`)" + (f": {line.rstrip(' .')}." if line else "")
