"""The knowledge agent: keeps the Brain accurate, tidy and aimed at the owner's goals with as
little of the owner's time as possible. Nothing it does changes the Brain on its own.

It works three ways:

- SUGGESTIONS, made by code as the Brain changes, with no model: notes past their review,
  notes that look alike, older dated values, quiet projects, questions the Brain could not
  answer, notes no AI used in months, skills nobody asks for. Each offers the action that deals
  with it, or the page where it is decided. They show at the bottom right of every page and as
  cards on Home; one set aside stays away for a few days, or until what it counts changes.
- ACTIONS: one upkeep job (`tidy-repeats`, `check-drift`, `check-alignment`, `freshen-up`,
  `tidy-projects`, `tidy-skills`, `fill-gaps`), run through the model the owner chose. Code
  gathers the candidates and the map of the Brain (the engine's agent.py); the model judges
  them by the action's procedure and answers in JSON; this service turns the answer into
  suggestions that wait in Catch up (a merge, a new text for a note) and questions for the
  owner, each with the buttons that act on it (still true, retire it, mark it disputed, answer
  it). Every candidate the model judged fine is counted, never acted on.
- A CONVERSATION in the side panel: the model answers from the map and what the Brain finds for
  the message, offers actions, and may suggest notes, which the owner keeps with one tap (they
  then wait in Catch up like any suggestion).

The model is asked by the server (Claude Code on this computer by default, or a local model);
this service builds every prompt, reads every answer and keeps the agent's state in the
workspace's settings: the model chosen, whether suggestions show, the questions waiting, what
was set aside, and the last runs.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Any

from workspace_core.clock import iso
from workspace_core.db import schema
from workspace_core.domain import statements
from workspace_core.domain.policy import Principal
from workspace_core.errors import Conflict, NotFound, ValidationFailed
from workspace_core.ids import new_id

from . import agent_loop
from .brain import Brain
from .runtime import Runtime

# The goal each action works toward, among the knowledge agent's four (brainkit/ladder.py).
ACTION_GOALS = {
    "freshen-up": "goal-notes-checked",
    "fill-gaps": "goal-questions-answered",
    "check-alignment": "goal-rules-reach",
}
ACTIONS: dict[str, dict[str, str]] = {
    "tidy-repeats": {
        "label": "Find repeats",
        "blurb": "Notes that say the same thing, merged or narrowed.",
    },
    "check-drift": {
        "label": "Check drift",
        "blurb": "Notes something newer may contradict.",
    },
    "check-alignment": {
        "label": "Check alignment",
        "blurb": "Your goals and projects against what the Brain holds.",
    },
    "freshen-up": {
        "label": "Freshen up",
        "blurb": "Stale notes, and much-used notes nobody checked lately.",
    },
    "tidy-projects": {
        "label": "Check projects",
        "blurb": "Projects gone quiet or without next steps.",
    },
    "tidy-skills": {
        "label": "Check skills",
        "blurb": "Skills unused, hard to ask for, or asked for with the same words.",
    },
    "fill-gaps": {
        "label": "Fill gaps",
        "blurb": "What your AIs asked that the Brain could not answer.",
    },
    "verify-sources": {
        "label": "Verify with sources",
        "blurb": "Your most used, single-source and stale notes, checked against the web.",
    },
}
# What each action's procedure lets the model answer; anything else is skipped.
VERDICTS: dict[str, tuple[str, ...]] = {
    "tidy-repeats": ("merge", "narrow", "different"),
    "check-drift": ("revise", "retire", "dispute", "fine"),
    "check-alignment": ("question", "triggers", "retire", "keep", "fine"),
    "freshen-up": ("ask", "revise", "retire", "lasting"),
    "tidy-projects": ("next-steps", "close", "ask"),
    "tidy-skills": ("triggers", "retire", "fine"),
    "fill-gaps": ("teach", "route", "ignore"),
    "verify-sources": ("confirmed", "challenge", "ask"),
}
FINE = ("different", "fine", "keep", "lasting", "ignore", "confirmed")
MAX_SOURCES = 5
DEFAULT_MODEL = "claude"
MODEL = re.compile(r"^[a-z][a-z0-9-]{0,30}(:[A-Za-z0-9._:/-]{1,100})?$")
KEY = re.compile(r"^[a-z0-9:_|.@/-]{1,300}$")
KEEP_RUNS = 30
KEEP_QUESTIONS = 200
DISMISS_DAYS = 3
MAX_MESSAGE = 4000
MAX_TURNS = 12  # of a conversation carried into the next prompt
CANDIDATES = 10  # for a capable model
BRIEF_CANDIDATES = 5  # for a small local one
UNUSED_DAYS = 90
QUIET_DAYS = 14
IDLE_SKILL_DAYS = 60
NOTE_KINDS = statements.AGENT_KINDS  # one vocabulary (domain/statements.py)

PREAMBLE = """\
You are the knowledge agent of a person's Brain: what every AI they use can know. Code made the \
map and the candidates below from the Brain a moment ago; trust them, and never invent a note, \
a project or a skill that is not in them. Nothing you answer changes the Brain: the person \
decides on every suggestion. Follow the procedure exactly."""
ANSWER = """\
Answer with the one JSON object the procedure describes, and nothing else: no words before or \
after it."""


HOLD_MINUTES = 30  # how long a gathered run waits for a connected AI's answer
HOLD_RUNS = 20  # gathered runs held at once


def _problems(skill: str, gathered: dict[str, Any], answer: str) -> list[str]:
    """What keeps an answer from passing the checks, in plain words; empty when it passes."""
    refs = [str(c["ref"]) for c in gathered.get("candidates") or []]
    found = _json_in(answer)
    findings = found.get("findings") if isinstance(found, dict) else None
    if not isinstance(findings, list):
        return ['The answer is one JSON object with "summary" and a "findings" list.']
    out = []
    for finding in findings:
        if not isinstance(finding, dict):
            out.append("Each finding is an object.")
            continue
        ref = str(finding.get("ref") or "").strip()
        verdict = str(finding.get("verdict") or "").strip().lower()
        if ref not in refs:
            out.append(f"{ref or 'a finding'}: not one of the refs {', '.join(refs)}.")
        elif verdict not in VERDICTS[skill]:
            out.append(f"{ref}: the verdict is one of {', '.join(sorted(VERDICTS[skill]))}.")
    return out


def _json_in(text: str, *, last: bool = False) -> dict[str, Any] | None:
    """The JSON object in a model's answer: a ```json block (the last one when `last`), else
    the outermost braces. None when there is none that reads."""
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", flags=re.S)
    tries = list(reversed(blocks)) if last else blocks
    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start != -1 and end > start:
        tries.append(text[start : end + 1])
    for chunk in tries:
        try:
            found = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(found, dict):
            return found
    return None


def _words(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _text(value: Any, limit: int = 4000) -> str:
    return str(value or "").strip()[:limit]


def _key(*parts: str) -> str:
    return "|".join(p for p in parts if p)[:300]


def _sources(finding: dict[str, Any]) -> list[str]:
    """The web sources a verification finding cites: links only, at most MAX_SOURCES."""
    found = finding.get("sources")
    items = found if isinstance(found, list) else []
    return [
        str(s).strip()[:500]
        for s in items
        if isinstance(s, str) and re.match(r"^https?://\S+$", s.strip())
    ][:MAX_SOURCES]


def _phrases(value: Any) -> list[str]:
    """Words to ask for something, as a model gave them: real phrases only (a small model
    copies the procedure's "..." placeholder), lower case, once each, at most eight."""
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        phrase = _words(item, 80).lower().strip(" .\"'")
        if len(re.findall(r"[a-z]", phrase)) >= 3 and phrase not in out:
            out.append(phrase)
    return out[:8]


def _short(ids: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(ids)).encode()).hexdigest()[:10]


class KnowledgeAgent:
    def __init__(self, rt: Runtime, brain: Brain) -> None:
        self.rt = rt
        self.brain = brain

    # ---------------------------------------------------------------- state

    def _state(self) -> dict[str, Any]:
        with self.rt.read() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
        return dict((row["settings"] or {}).get("knowledge_agent") or {})

    def _update(self, change: Any) -> dict[str, Any]:
        with self.rt.write() as tx:
            row = tx.one(schema.workspaces, self.rt.workspace_id, "workspace")
            settings = dict(row["settings"] or {})
            state = dict(settings.get("knowledge_agent") or {})
            moment = tx.now
            state["dismissed"] = {
                k: v for k, v in (state.get("dismissed") or {}).items() if str(v) > moment
            }
            change(state, tx)
            settings["knowledge_agent"] = state
            tx.update(schema.workspaces, row, {"settings": settings})
        return state

    def overview(self, who: Principal) -> dict[str, Any]:
        """The agent's page: the model chosen, whether suggestions show, the actions, the
        questions waiting, and the last runs (newest first)."""
        who.require("brain.read")
        state = self._state()
        goals = [
            g
            for g in self.rt.brain.ladder().get("agents") or []
            if g.get("kept_by") == "knowledge-agent"
        ]
        kept = {g["id"]: g for g in goals}
        return {
            "model": state.get("model") or DEFAULT_MODEL,
            "suggestions": state.get("suggestions", True) is not False,
            # Its goals first, and for each action the goal it serves ("Why I'm doing this").
            "goals": goals,
            "actions": [
                {
                    "id": k,
                    **v,
                    "serves": (
                        {
                            "id": ACTION_GOALS[k],
                            "title": kept[ACTION_GOALS[k]]["title"],
                            "words": kept[ACTION_GOALS[k]]["words"],
                        }
                        if ACTION_GOALS.get(k) in kept
                        else None
                    ),
                }
                for k, v in ACTIONS.items()
            ],
            "questions": [q for q in state.get("questions") or [] if q.get("status") == "open"],
            "runs": list(reversed(state.get("runs") or [])),
        }

    def configure(
        self, who: Principal, *, model: str | None = None, suggestions: bool | None = None
    ) -> dict[str, Any]:
        """Choose the model the agent works through, and whether its suggestions show."""
        who.require("brain.govern")
        if model is not None:
            model = str(model).strip()
            if not MODEL.match(model):
                raise ValidationFailed("Choose one of the models listed.", field="model")

        def change(state: dict[str, Any], _tx: Any) -> None:
            if model is not None:
                state["model"] = model
            if suggestions is not None:
                state["suggestions"] = bool(suggestions)

        self._update(change)
        return self.overview(who)

    def model(self) -> str:
        return str(self._state().get("model") or DEFAULT_MODEL)

    def chosen_model(self) -> str | None:
        """The model the owner chose, or None: then the app picks (a local model when one is
        here, brain-logic plan 17)."""
        found = self._state().get("model")
        return str(found) if found else None

    # ---------------------------------------------------------------- suggestions, no model

    def suggestions(self, who: Principal, *, every: bool = False) -> list[dict[str, Any]]:
        """What the agent would bring up now, made by code from the Brain as it is, the most
        pressing first: {"key", "kind", "title", "detail", "count", "action", "link"}. Set
        aside ones stay out unless `every`."""
        who.require("brain.read")
        state = self._state()
        if not every and state.get("suggestions", True) is False:
            return []
        out: list[dict[str, Any]] = []
        attention = self.brain.attention(who)

        def add(kind: str, ids: list[str], title: str, detail: str, **where: Any) -> None:
            if ids:
                out.append(
                    {
                        "key": f"{kind}:{_short(ids)}",
                        "kind": kind,
                        "title": title,
                        "detail": detail,
                        "count": len(ids),
                        "action": where.get("action"),
                        "link": where.get("link"),
                    }
                )

        def n(count: int, one: str, many: str) -> str:
            return f"{count} {one if count == 1 else many}"

        clashes = [str(c.get("proposal_id")) for c in attention.get("clashes") or []]
        add(
            "clashes",
            clashes,
            f"{n(len(clashes), 'suggestion may', 'suggestions may')} disagree with your notes",
            "They wait in Catch up, side by side with what they may contradict.",
            link="/catch-up",
        )
        went_in = [str(w.get("key")) for w in attention.get("went_in") or []]
        add(
            "went-in",
            went_in,
            f"{n(len(went_in), 'note', 'notes')} went in on their own and may disagree",
            "Each can be taken back in one tap.",
            link="/catch-up",
        )
        stale = [str(r.get("id")) for r in attention.get("recheck") or []]
        add(
            "stale",
            stale,
            f"{n(len(stale), 'note is', 'notes are')} past {'its' if len(stale) == 1 else 'their'}"
            " review",
            "The agent can sort what is over, what changed and what only you can confirm.",
            action="freshen-up",
        )
        twins = [f"{t.get('a')}+{t.get('b')}" for t in attention.get("twins") or []]
        add(
            "repeats",
            twins,
            f"{n(len(twins), 'pair of notes looks', 'pairs of notes look')} alike",
            "The agent can merge the ones that say the same thing.",
            action="tidy-repeats",
        )
        dated = [str(d.get("key")) for d in attention.get("dated") or []]
        add(
            "drift",
            dated,
            f"{n(len(dated), 'older value is', 'older values are')} still live",
            "A newer note gives another value: the agent can retire or update the older.",
            action="check-drift",
        )
        gaps = [str(g.get("key") or g.get("request")) for g in self.brain.gaps(who, days=7)]
        add(
            "gaps",
            gaps,
            f"Your AIs asked {n(len(gaps), 'thing', 'things')} the Brain could not answer",
            "This week. The agent can turn them into questions for you.",
            action="fill-gaps",
        )
        moment = self.rt.clock.now()
        quiet_day = (moment - timedelta(days=QUIET_DAYS)).date().isoformat()
        quiet = [
            p.id
            for p in self.brain.projects(who)
            if p.active
            and p.status.lower() not in ("paused", "on hold", "waiting", "parked")
            and str(p.updated or "")[:10] < quiet_day
        ]
        add(
            "projects",
            quiet,
            f"{n(len(quiet), 'project', 'projects')} went quiet",
            f"No update in {QUIET_DAYS} days.",
            action="tidy-projects",
        )
        unused_day = (moment - timedelta(days=UNUSED_DAYS)).date().isoformat()
        idle_day = (moment - timedelta(days=IDLE_SKILL_DAYS)).date().isoformat()
        unused, idle_skills = [], []
        for row in self.brain.inventory(who):
            last = str((row.get("uses") or {}).get("last") or "")
            if row.get("type") == "note" and row.get("live") and row.get("kind") != "focus":
                if row.get("load") in ("standing", "domain", "manual"):
                    continue
                if str(row.get("added") or "9999") < unused_day and (not last or last < unused_day):
                    unused.append(str(row["id"]))
            elif row.get("type") == "skill" and (not last or last < idle_day):
                idle_skills.append(str(row["id"]))
        add(
            "unused",
            unused,
            f"{n(len(unused), 'note', 'notes')} no AI used in {UNUSED_DAYS} days",
            "The agent can check them against your goals.",
            action="check-alignment",
        )
        if len(idle_skills) >= 3:
            add(
                "skills",
                idle_skills,
                f"{len(idle_skills)} skills no AI used in {IDLE_SKILL_DAYS} days",
                "Often they need better words to be asked for.",
                action="tidy-skills",
            )
        open_questions = [
            str(q["key"]) for q in state.get("questions") or [] if q.get("status") == "open"
        ]
        add(
            "questions",
            open_questions,
            f"The agent has {n(len(open_questions), 'question', 'questions')} for you",
            "Most take a tap: still true, retire it, or a sentence to answer.",
            link="/brain/agent",
        )
        if every:
            return out
        hidden = {
            k for k, until in (state.get("dismissed") or {}).items() if str(until) > iso(moment)
        }
        return [s for s in out if s["key"] not in hidden]

    def dismiss(self, who: Principal, key: str, *, days: int = DISMISS_DAYS) -> None:
        """Set a suggestion aside for a few days; it comes back sooner if what it counts
        changes (its key changes with it)."""
        who.require("brain.read")
        key = str(key or "").strip()
        if not KEY.match(key):
            raise ValidationFailed("Name the suggestion.", field="key")
        days = max(1, min(int(days), 30))

        def change(state: dict[str, Any], tx: Any) -> None:
            until = iso(tx.moment + timedelta(days=days))
            state.setdefault("dismissed", {})[key] = until

        self._update(change)

    # ---------------------------------------------------------------- an action

    def action_prompt(
        self, who: Principal, action: str, *, brief: bool = False
    ) -> tuple[str, dict[str, Any]]:
        """The prompt for one action, and what it gathered (its candidates, by reference). No
        candidates: the prompt is empty and nothing need be asked."""
        who.require("brain.read")
        if action not in ACTIONS:
            raise ValidationFailed(f"An action is one of {', '.join(ACTIONS)}.", field="action")
        gathered = self.rt.brain.agent_gather(
            action, limit=BRIEF_CANDIDATES if brief else CANDIDATES
        )
        if not gathered.get("candidates"):
            return "", gathered
        procedure = self.rt.brain.agent_skill(action)
        outline = self.rt.brain.agent_outline(brief=brief).get("text") or ""
        menu = self.rt.brain.agent_menu()
        # The core prompt (BL 17.2), then the job's procedure; the person's rules and the
        # must-holds in play with every job.
        parts = [agent_loop.core(menu) if menu else PREAMBLE]
        parts.append("# The procedure\n\n" + procedure.strip())
        kernel = (self.rt.brain.kernel(tools=False) or {}).get("text") or ""
        if kernel.strip():
            parts.append("# The person's startup context (their rules)\n\n" + kernel.strip())
        parts.append(outline.strip())
        digest = self.rt.brain.changes_digest()
        if digest:
            parts.append("# What changed lately\n\n" + digest)
        parts.append(
            "# The candidates\n\n"
            + "\n\n".join(f"## {c['ref']}\n\n{c['text']}" for c in gathered["candidates"])
        )
        parts.append(ANSWER)
        return "\n\n".join(parts) + "\n", gathered

    # ---------------------------------------------------------------- run by a connected AI

    def gather(self, who: Principal, skill: str, *, brief: bool = False) -> dict[str, Any]:
        """knowledge_gather (Release 1 plan, M08): a connected AI runs one skill itself. Code
        gathers the same candidates a run the app starts would; the run is held for
        HOLD_MINUTES for its answer (knowledge_submit), which passes the same checks and the
        same governance."""
        who.require("brain.propose")
        prompt, gathered = self.action_prompt(who, skill, brief=brief)
        if not gathered.get("candidates"):
            return {
                "run_id": None,
                "skill": skill,
                "candidates": [],
                "summary": "Nothing to check right now.",
            }
        now = self.rt.clock.now()
        run_id = new_id("krun", now)
        expires = iso(now + timedelta(minutes=HOLD_MINUTES))

        def change(state: dict[str, Any], _tx: Any) -> None:
            held = {
                k: v
                for k, v in (state.get("gathered") or {}).items()
                if str(v.get("expires") or "") > iso(now)
            }
            held[run_id] = {
                "skill": skill,
                "gathered": gathered,
                "expires": expires,
                "retried": False,
                "by": who.actor_id,
            }
            state["gathered"] = dict(list(held.items())[-HOLD_RUNS:])

        self._update(change)
        return {
            "run_id": run_id,
            "skill": skill,
            "procedure": prompt,
            "candidates": [
                {"ref": c["ref"], "kind": c.get("kind"), "title": c.get("title")}
                for c in gathered["candidates"]
            ],
            "verdicts": sorted(VERDICTS[skill]),
            "answer_format": ANSWER,
            "expires": expires,
        }

    def submit(self, who: Principal, run_id: str, answer: str) -> dict[str, Any]:
        """knowledge_submit: check a connected AI's answer to a gathered run. Problems go back
        once, listed (`retry`); a second answer that still does not pass keeps what it can,
        and the run is handed back to the person (`handed_back`)."""
        who.require("brain.propose")
        held = (self._state().get("gathered") or {}).get(str(run_id or ""))
        if held is None or held.get("by") != who.actor_id:
            raise NotFound(f"No gathered run {run_id}: gather again.", id=run_id)
        if str(held.get("expires") or "") <= iso(self.rt.clock.now()):
            self._forget_run(run_id)
            raise Conflict("That gathered run expired: gather again.")
        problems = _problems(held["skill"], held["gathered"], answer)
        if problems and not held.get("retried"):

            def mark(state: dict[str, Any], _tx: Any) -> None:
                state["gathered"][run_id]["retried"] = True

            self._update(mark)
            return {"retry": {"problems": problems}}
        self._forget_run(run_id)
        record = self.apply_action(
            who, held["skill"], held["gathered"], answer, model="connected AI"
        )
        if problems:
            record["handed_back"] = True
            record["notes"].append(
                "The answer still did not pass after one retry: what could not be read waits "
                "for you."
            )
        return record

    def _forget_run(self, run_id: str) -> None:
        def change(state: dict[str, Any], _tx: Any) -> None:
            (state.get("gathered") or {}).pop(run_id, None)

        self._update(change)

    def apply_action(
        self,
        who: Principal,
        action: str,
        gathered: dict[str, Any],
        answer: str,
        *,
        model: str,
        seconds: float | None = None,
    ) -> dict[str, Any]:
        """Turn a model's answer into suggestions and questions, and keep the run's record:
        {"id", "action", "model", "at", "summary", "checked", "proposed", "questions",
        "fine", "skipped", "proposals", "notes"}."""
        who.require("brain.propose")
        candidates = {c["ref"]: c for c in gathered.get("candidates") or []}
        found = _json_in(answer) if candidates else {}
        findings = (found or {}).get("findings") if isinstance(found, dict) else None
        record: dict[str, Any] = {
            "id": new_id("arun", self.rt.clock.now()),
            "action": action,
            "label": ACTIONS[action]["label"],
            "model": model,
            "at": iso(self.rt.clock.now()),
            "summary": _words((found or {}).get("summary"), 300),
            "checked": len(candidates),
            "found": int(gathered.get("found") or len(candidates)),
            "proposed": 0,
            "questions": 0,
            "fine": 0,
            "skipped": 0,
            "proposals": [],
            "notes": [],
        }
        if seconds is not None:
            record["seconds"] = round(float(seconds), 1)
        if candidates and not isinstance(findings, list):
            record["skipped"] = len(candidates)
            record["notes"].append("The model's answer could not be read, so nothing was kept.")
            self._remember(record, [])
            return record
        questions: list[dict[str, Any]] = []
        for finding in findings or []:
            if not isinstance(finding, dict):
                record["skipped"] += 1
                continue
            candidate = candidates.get(str(finding.get("ref") or "").strip())
            verdict = str(finding.get("verdict") or "").strip().lower()
            if candidate is None or verdict not in VERDICTS[action]:
                record["skipped"] += 1
                continue
            if action == "verify-sources" and not _sources(finding):
                # A finding without a source is never kept (BL 9's gate).
                record["skipped"] += 1
                continue
            if verdict in FINE:
                record["fine"] += 1
                continue
            try:
                made = self._finding(who, action, candidate, verdict, finding)
            except (ValidationFailed, NotFound, Conflict) as exc:
                record["skipped"] += 1
                record["notes"].append(f"{candidate['title']}: {exc}")
                continue
            if made is None:
                record["skipped"] += 1
            elif made.get("proposal_id"):
                record["proposed"] += 1
                record["proposals"].append(made["proposal_id"])
            else:
                questions.append(made)
                record["questions"] += 1
        if not candidates:
            record["summary"] = "Nothing to check right now."
        elif not record["summary"]:
            record["summary"] = self._summary(record)
        self._remember(record, questions)
        return record

    @staticmethod
    def _summary(record: dict[str, Any]) -> str:
        bits = [f"checked {record['checked']}"]
        if record["proposed"]:
            bits.append(f"{record['proposed']} suggested for Catch up")
        if record["questions"]:
            bits.append(f"{record['questions']} for you to answer")
        if record["fine"]:
            bits.append(f"{record['fine']} fine")
        return ", ".join(bits).capitalize() + "."

    def _which(self, candidate: dict[str, Any], finding: dict[str, Any], field: str) -> str:
        """The note (or skill) a finding means: "A"/"B" in a pair, an id among the
        candidate's, else the candidate's only one."""
        ids = [str(i) for i in candidate.get("ids") or []]
        named = str(finding.get(field) or "").strip()
        if named.upper() in ("A", "B") and len(ids) >= 2:
            return ids[0 if named.upper() == "A" else 1]
        if named in ids:
            return named
        if len(ids) == 1:
            return ids[0]
        raise ValidationFailed(f"It did not say which of {', '.join(ids)}.", field=field)

    def _finding(
        self,
        who: Principal,
        action: str,
        candidate: dict[str, Any],
        verdict: str,
        finding: dict[str, Any],
    ) -> dict[str, Any] | None:
        """One finding as a suggestion in Catch up ({"proposal_id"}) or a question for the
        person (the question itself); None when it says nothing usable."""
        why = _words(finding.get("why"), 400)
        evidence = f"The knowledge agent ({ACTIONS[action]['label'].lower()}): {why or verdict}"
        origin = f"agent:{action}"
        ids = [str(i) for i in candidate.get("ids") or []]
        kind = candidate.get("kind")
        if action == "verify-sources":
            sources = _sources(finding)
            cited = "Sources: " + "; ".join(sources)
            target = self._which(candidate, finding, "which")
            if verdict == "challenge":
                claim = _text(finding.get("text"), 1000)
                if not claim:
                    return None
                made = self.brain.challenge(
                    who,
                    note_id=target,
                    claim=claim,
                    evidence=f"{why} {cited}".strip(),
                    source=sources[0],
                )
                return {"proposal_id": made.proposal_id} if made.proposal_id else None
            ask = _text(finding.get("text"), 300) or "Is this still true?"
            return {
                "action": action,
                "verdict": verdict,
                "why": f"{why} {cited}".strip(),
                "text": _text(finding.get("text"), 1000),
                "ask": ask,
                "sources": sources,
                "target": {"type": "note", "id": target, "title": candidate["title"]},
                "key": _key(action, verdict, "note", target, ask[:60]),
            }
        if verdict == "merge":
            keep = self._which(candidate, finding, "keep")
            text = _text(finding.get("text"))
            if not text:
                return None
            made = self.brain.propose(
                who,
                title=_words(finding.get("title"), 200) or candidate["title"].split(" / ")[0],
                statement=text,
                evidence=evidence,
                revises=keep,
                replaces=[i for i in ids if i != keep],
                origin=origin,
            )
            return {"proposal_id": made.proposal_id} if made.proposal_id else None
        if verdict in ("narrow", "revise") and kind in ("pair", "note"):
            target = self._which(candidate, finding, "which")
            text = _text(finding.get("text"))
            if not text:
                return None
            made = self.brain.propose(
                who,
                title=candidate["title"].split(" / ")[0][:200],
                statement=text,
                evidence=evidence,
                revises=target,
                origin=origin,
            )
            return {"proposal_id": made.proposal_id} if made.proposal_id else None
        question: dict[str, Any] = {
            "action": action,
            "verdict": verdict,
            "why": why,
            "text": _text(finding.get("text"), 1000),
        }
        if kind in ("pair", "note"):
            target = self._which(candidate, finding, "which")
            question["target"] = {"type": "note", "id": target, "title": candidate["title"]}
            if verdict == "retire":
                question["ask"] = "Retire this note?"
            elif verdict == "dispute":
                question["ask"] = "Mark this note disputed until you settle it?"
            elif verdict == "triggers":
                question["triggers"] = _phrases(finding.get("triggers"))
                if not question["triggers"]:
                    return None
                question["ask"] = "Give this must-hold the words that bring it up?"
            else:
                question["ask"] = question["text"] or "Is this still true?"
        elif kind == "project":
            question["target"] = {"type": "project", "id": ids[0], "title": candidate["title"]}
            question["ask"] = {
                "close": "Is this project done?",
                "next-steps": "Record these next steps?",
            }.get(verdict) or (question["text"] or "Where does this project stand?")
        elif kind in ("skill",) or (action == "tidy-skills" and kind == "pair"):
            name = self._which(candidate, finding, "which")
            question["target"] = {"type": "skill", "id": name, "title": f"/{name}"}
            question["triggers"] = _phrases(finding.get("triggers"))
            if verdict == "triggers" and not question["triggers"]:
                return None
            question["ask"] = (
                "Retire this skill?" if verdict == "retire" else "Ask for it with these words?"
            )
        elif kind == "gap":
            if verdict == "route":
                note = str(finding.get("id") or "").strip()
                if not note:
                    return None
                question["target"] = {"type": "note", "id": note, "title": note}
                question["ask"] = "Add these words so it is found next time?"
            else:
                question["target"] = {"type": "gap", "id": ids[0], "title": candidate["title"]}
                question["ask"] = question["text"] or candidate["title"]
        elif kind == "goals":
            if not question["text"]:
                return None
            question["target"] = {"type": "goals", "id": ids[0], "title": "Your goals"}
            question["ask"] = question["text"]
        else:
            return None
        target = question["target"]
        question["key"] = _key(action, verdict, target["type"], target["id"], question["ask"][:60])
        return question

    def _remember(self, record: dict[str, Any], questions: list[dict[str, Any]]) -> None:
        def change(state: dict[str, Any], tx: Any) -> None:
            kept = [q for q in state.get("questions") or [] if q.get("key")]
            known = {q["key"]: q for q in kept}
            for question in questions:
                question.update(status="open", at=tx.now, run=record["id"])
                if question["key"] in known and known[question["key"]].get("status") == "open":
                    known[question["key"]].update(question)
                elif question["key"] not in known:
                    kept.append(question)
                    known[question["key"]] = question
                else:  # answered or set aside before: asked again, open again
                    known[question["key"]].update(question)
            state["questions"] = kept[-KEEP_QUESTIONS:]
            runs = list(state.get("runs") or [])
            runs.append(record)
            state["runs"] = runs[-KEEP_RUNS:]

        self._update(change)

    # ---------------------------------------------------------------- questions

    def answer(
        self, who: Principal, key: str, do: str, *, text: str | None = None
    ) -> dict[str, Any]:
        """Act on one of the agent's questions: `verify` (still true), `retire`, `dispute`,
        `answer` (a sentence the Brain should know, as a suggestion), `done` or `dismiss`."""
        who.require("brain.govern")
        key = str(key or "").strip()
        question = next(
            (
                q
                for q in self._state().get("questions") or []
                if q.get("key") == key and q.get("status") == "open"
            ),
            None,
        )
        if question is None:
            raise NotFound("That question is no longer waiting.", key=key)
        target = question.get("target") or {}
        reason = f"The knowledge agent asked: {question.get('ask') or ''}"[:480]
        outcome: dict[str, Any] = {"key": key, "do": do}
        if do in ("verify", "retire", "dispute"):
            if target.get("type") != "note":
                raise ValidationFailed("Only a note can be confirmed, retired or disputed.")
            decision: dict[str, Any] = {
                "verify": {"action": "verify", "entry_id": target["id"]},
                "retire": {"action": "archive", "entry_id": target["id"], "reason": reason},
                "dispute": {
                    "action": "mark",
                    "entry_id": target["id"],
                    "state": "disputed",
                    "reason": reason,
                },
            }[do]
            result = self.brain.decide_many(
                who, [decision], source={"agent": question.get("action") or ""}
            )
            failed = [r for r in result.get("results") or [] if not r.get("ok")]
            if failed:
                raise Conflict(str(failed[0].get("message") or "The Brain refused it."))
            outcome["checkpoint"] = (result.get("checkpoint") or {}).get("id")
        elif do == "answer":
            said = _text(text, 2000)
            if not said:
                raise ValidationFailed("Say the answer in a sentence or two.", field="text")
            made = self.brain.propose(
                who,
                title=_words(said.split(". ")[0], 120),
                statement=said,
                evidence=reason,
                origin=f"agent:{question.get('action') or 'question'}",
            )
            outcome["proposal_id"] = made.proposal_id
        elif do not in ("done", "dismiss"):
            raise ValidationFailed(
                "Do one of verify, retire, dispute, answer, done or dismiss.", field="do"
            )

        def change(state: dict[str, Any], tx: Any) -> None:
            for q in state.get("questions") or []:
                if q.get("key") == key:
                    q["status"] = "dismissed" if do == "dismiss" else "done"
                    q["closed_at"] = tx.now

        self._update(change)
        # Its memory (BL 17.6): the suggestion, the person's decision and why, by topic.
        self.rt.brain.record_episode(
            action=str(question.get("action") or ""),
            area=str(target.get("type") or ""),
            topic=str(target.get("title") or target.get("id") or ""),
            text=str(question.get("ask") or question.get("text") or ""),
            decision="declined" if do in ("dismiss", "verify") else "kept",
            reason=_words(text, 300) if do == "answer" else "",
            ref=str(target.get("id") or ""),
        )
        return outcome

    # ---------------------------------------------------------------- a conversation

    def chat_prompt(
        self,
        who: Principal,
        message: str,
        history: list[dict[str, Any]] | None = None,
        *,
        brief: bool = False,
    ) -> str:
        """The prompt for one turn of the side panel's conversation."""
        who.require("brain.read")
        message = _text(message, MAX_MESSAGE)
        if not message:
            raise ValidationFailed("Say something to the agent.", field="message")
        procedure = self.rt.brain.agent_skill("knowledge-agent")
        outline = self.rt.brain.agent_outline(brief=brief).get("text") or ""
        parts = [procedure.strip()]
        if not brief:
            kernel = (self.rt.brain.kernel(tools=False) or {}).get("text") or ""
            if kernel.strip():
                parts.append("# The person's startup context (their rules)\n\n" + kernel.strip())
        parts.append(outline.strip())
        try:
            found = self.brain.preview(who, message, tools=False)
        except ValidationFailed:
            found = {}
        if str(found.get("text") or "").strip():
            parts.append("# What the Brain found for the message\n\n" + found["text"].strip())
        turns = [t for t in history or [] if isinstance(t, dict)][-MAX_TURNS:]
        if turns:
            lines = []
            for turn in turns:
                who_said = "The person" if turn.get("role") == "user" else "You"
                lines.append(f"{who_said}: {_text(turn.get('text'), 2000)}")
            parts.append("# The conversation so far\n\n" + "\n\n".join(lines))
        parts.append(f"# The person's new message\n\n{message}")
        return "\n\n".join(parts) + "\n"

    def read_chat(self, answer: str) -> dict[str, Any]:
        """A chat answer as the panel shows it: {"reply", "run", "notes"}: the words, the
        actions to offer and the notes to suggest."""
        found = _json_in(answer, last=True) or {}
        reply = re.sub(r"```(?:json)?\s*\{.*?\}\s*```", "", answer or "", flags=re.S).strip()
        if not reply and not found:
            reply = (answer or "").strip()
        run = [a for a in found.get("run") or [] if isinstance(a, str) and a in ACTIONS][:4]
        notes = []
        for item in found.get("notes") or []:
            if not isinstance(item, dict):
                continue
            text = _text(item.get("text"), 1000)
            if not text:
                continue
            kind = str(item.get("kind") or "fact").strip().lower()
            notes.append(
                {
                    "title": _words(item.get("title"), 120) or _words(text, 80),
                    "text": text,
                    "kind": kind if kind in NOTE_KINDS else "fact",
                }
            )
        return {"reply": reply, "run": run, "notes": notes[:5]}

    def keep_note(
        self, who: Principal, *, title: str, text: str, kind: str = "fact", said: str = ""
    ) -> dict[str, Any]:
        """A note the agent suggested in the conversation, kept by the person: it waits in
        Catch up like any suggestion."""
        who.require("brain.propose")
        kind = kind if kind in NOTE_KINDS else "fact"
        made = self.brain.propose(
            who,
            title=_words(title, 200) or _words(text, 80),
            statement=_text(text, 2000),
            kind=kind,
            evidence=(
                f"Suggested by the knowledge agent when the person said: “{_words(said, 300)}”"
                if said.strip()
                else "Suggested by the knowledge agent in a conversation with the person."
            ),
            origin="agent:chat",
        )
        return {"status": made.status, "proposal_id": made.proposal_id, "message": made.message}
