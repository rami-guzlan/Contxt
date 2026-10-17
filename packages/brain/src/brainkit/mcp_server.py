"""MCP server over stdio: a thin adapter from JSON-RPC to `Brain`.

Two tool profiles:

    agent (default)   what a model needs for ordinary work: one context call per task,
                      search and single notes when the packet lacks something, procedures
                      and documents on demand, and the three governed writers
    full              adds read-only inspection tools (topics, Focus, inbox) for an owner's
                      session; set BRAIN_MCP_PROFILE=full

Owner decisions (approve, reject) are deliberately absent from both: an AI proposes, a
human decides, in the CLI or the local UI.

Every call runs as the principal this server was started for (BRAIN_PRINCIPAL, or the
brain's owner). A caller cannot choose who it is.
"""
from __future__ import annotations

import json
import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brainkit import runtime, statements
from brainkit.api import Brain, Result

PROTOCOL_DEFAULT = "2024-11-05"
INSTRUCTIONS = ("Call get_task_context first for every request, and again for every later "
                "message in the conversation that asks for something new: it sends only what the "
                "conversation does not already hold, and one line for a pure edit. Pass the "
                "user's message as they wrote it, and the session_id it returns (or the one your "
                "session start named) on every later call. If the packet lacks something the "
                "work needs, search_notes in your own words and open a hit with get_note. Open "
                "procedures and documents only when the packet points at them. Capture as you "
                "go, without being asked: a durable rule, correction, preference, decision or "
                "changed fact the person states goes to propose_note (quote them in evidence); "
                "a procedure you work out together to propose_skill; a document they share or "
                "work on (a proposal, a brief, a deck) to add_file, with its project. Keep "
                "fast-changing values (an account's health, a repo's owner) with update_state, "
                "and a task's progress with hand_off: when you take it, after real work, when "
                "blocked, before you stop, and when done.")

_STR = {"type": "string"}
AGENT_TOOLS = [
    {"name": "get_task_context",
     "description": "Call first for every request, and again with the session_id for every later "
                    "message that asks for something new. Returns the scoped context packet: "
                    "only what the conversation does not already hold (one line for a pure "
                    "edit), and the startup kernel when yours is stale.",
     "inputSchema": {"type": "object", "properties": {
         "request": {"type": "string", "description": "The user's message as they wrote "
                                                     "it; name what \"it\" or \"that\" "
                                                     "means only if the message needs it."},
         "session_id": {"type": "string", "description": "The session_id from an earlier call "
                                                          "in this conversation."},
         "fresh": {"type": "boolean", "description": "True after a compaction or when you no "
                                                     "longer hold earlier deliveries."},
         "startup_fingerprint": {"type": "string",
                                 "description": "The kernel fingerprint from your startup file."},
         "focus": {"type": "string", "description": "Exact Focus name or id, when known."},
         "task_type": {"type": "string", "enum": ["knowledge", "workflow", "combined"]},
         "partition": {"type": "string",
                       "description": "Active client or project partition; omit for none."},
         "context": {"type": "string",
                     "description": "The working context: a task (T-41), a goal, a project, "
                                    "a State row (sheet/row), or general. Kept for the "
                                    "conversation."}},
         "required": ["request"]}},
    {"name": "get_skill",
     "description": "Open one procedure the packet pointed at, when you are about to follow it.",
     "inputSchema": {"type": "object", "properties": {
         "name": _STR, "session_id": _STR, "partition": _STR}, "required": ["name"]}},
    {"name": "get_reference",
     "description": "Read one reference document the packet named, when you need its detail.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "For example references/brand-voice.md"},
         "session_id": _STR}, "required": ["path"]}},
    {"name": "get_note",
     "description": "Read one note by id: one the packet listed under Also relevant, or a "
                    "search_notes hit, when the work needs it.",
     "inputSchema": {"type": "object", "properties": {"id": _STR, "session_id": _STR},
                     "required": ["id"]}},
    {"name": "search_notes",
     "description": "Find notes the packet did not bring. Use it when the work needs something "
                    "the packet lacks: describe what you need in your own words, and if nothing "
                    "fits, try again with other words (the brain's terms, or plainer ones: "
                    "'UTM parameters' rather than 'tagging links', 'AI-sounding writing' rather "
                    "than 'robotic'). Returns titles and one-line summaries, best first; open "
                    "one with get_note.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "What you need, in a few words."},
         "limit": {"type": "integer", "description": "How many hits (default 8)."},
         "session_id": _STR}, "required": ["query"]}},
    {"name": "challenge_note",
     "description": "When the person says, or evidence you found shows, that a note the Brain "
                    "holds is wrong or out of date, raise a challenge: the note's id, what you "
                    "claim instead, the evidence and where it comes from. It waits for the "
                    "owner and never changes the note; a challenge turned down before is not "
                    "taken again without new evidence.",
     "inputSchema": {"type": "object", "properties": {
         "note_id": {"type": "string", "description": "The note challenged."},
         "claim": {"type": "string", "description": "What you claim instead, in one or two "
                   "sentences."},
         "evidence": {"type": "string", "description": "The evidence for it, quoted or "
                      "summarized."},
         "source": {"type": "string", "description": "Where the evidence comes from: a file, "
                    "a page, a person, a date."},
         "session_id": _STR}, "required": ["note_id", "claim", "evidence"]}},
    {"name": "propose_note",
     "description": "Capture durable knowledge as it comes up, without being asked: a rule, "
                    "correction, preference, decision or changed fact the person states that "
                    "will still be true next month and applies beyond this request. Quote their "
                    "words in `evidence`. Also proposes a change to a note (target_id). File it "
                    "in an existing area/topic when one fits; the reply names the closest "
                    "topics when yours is new. Your own scope applies at once; shared knowledge "
                    "applies or waits for the owner as their policy says (the reply tells you "
                    "which). Anything that may disagree with a note, or changes a baseline (a "
                    "rule, a must-hold, a note the owner confirmed), waits for the owner "
                    "whatever the policy, and the reply says why. The same text twice returns "
                    "the waiting proposal.",
     "inputSchema": {"type": "object", "properties": {
         "area": {"type": "string", "description": "Where it is filed, for example brand, "
                  "customers, sales, operations, people, projects."},
         "topic": {"type": "string", "description": "A topic inside the area, for example "
                   "voice. Reuse an existing one when it fits."},
         "title": {"type": "string", "description": "What the note is for, in a few words."},
         "summary": {"type": "string", "description": "One line saying what it covers."},
         "kind": {"type": "string", "enum": list(statements.NOTE_KINDS)},
         "text": {"type": "string", "description": "One durable idea."},
         "scope": {"type": "string", "description": "company | dept:<name> | person:<name>"},
         "load": {"type": "string", "enum": ["standing", "domain", "on-demand"],
                  "description": "standing: every session. domain: a must-hold, in every "
                                 "brief whenever its domain comes up (a safety, legal, money "
                                 "or privacy constraint). on-demand: when relevant."},
         "applies_to": {"type": "string", "description": "For load domain: the areas, "
                        "area/topic pairs or project ids it covers, comma-separated (its own "
                        "area when omitted)."},
         "triggers": {"type": "string", "description": "For load domain: words and short "
                      "phrases that bring the domain into play, comma-separated, for example "
                      "dinner, lunchbox, restaurant, birthday party."},
         "must_text": {"type": "string", "description": "For load domain: the rule in one "
                       "line, as a brief will show it."},
         "critical": {"type": "boolean", "description": "For load domain, only for a rule "
                      "that must never be missed (a life-safety or legal one): its line also "
                      "goes in every session's startup context. At most three per Brain."},
         "as_of": {"type": "string", "description": "For a value that changes (a total, a "
                   "count, a balance, a version): the day it was true, YYYY-MM-DD. A newer "
                   "dated value for the same thing updates the older one in briefs."},
         "valid_until": {"type": "string", "description": "The last day it holds, "
                         "YYYY-MM-DD; after it, the note is flagged for a check."},
         "evidence": _STR,
         "source": {"type": "string", "description": "Where it came from. When that is a "
                    "file an AI made (one recorded with record_output), name it as "
                    "output:<its full path>: what only repeats the brief that file was made "
                    "from is refused."},
         "supersedes": {"type": "string", "description": "Note ids this one replaces; they "
                        "retire when it is approved. With target_id, a merge: the changed note "
                        "now covers what they said."},
         "target_id": {"type": "string", "description": "Existing note id to change."},
         "session_id": _STR},
         "required": ["text"]}},
    {"name": "propose_skill",
     "description": "Capture a reusable procedure as a skill, without being asked, when the "
                    "person and you have worked out how a recurring job is done (steps, "
                    "checklists, templates, scripts). Or improve an existing skill (`target`). "
                    "Files (templates, assets, scripts) travel with it. It waits for the owner's "
                    "review and is staged outside the brain until approved.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "kebab-case, e.g. client-onboarding"},
         "category": {"type": "string", "description": "An existing skill category, e.g. "
                      "ops, sales, social; a new lowercase one if none fits."},
         "description": {"type": "string", "description": "What it does and when to use it."},
         "when_to_use": _STR,
         "triggers": {"type": "array", "items": _STR,
                      "description": "Phrases a request would use for it."},
         "loads": {"type": "array", "items": _STR,
                   "description": "Brain topics (area/topic) it needs."},
         "body": {"type": "string", "description": "The procedure, in Markdown."},
         "files": {"type": "array", "items": {"type": "object", "properties": {
             "path": {"type": "string", "description": "Inside the skill, e.g. assets/x.md"},
             "content": {"type": "string", "description": "Text content"},
             "content_base64": {"type": "string", "description": "Binary content"},
             "source_path": {"type": "string", "description": "A local file to copy"}},
             "required": ["path"]}},
         "target": {"type": "string", "description": "Existing skill to change."},
         "evidence": _STR, "session_id": _STR}}},
    {"name": "add_file",
     "description": "Keep a document or asset the person shares or works on, without being "
                    "asked: their work in progress (a proposal, brief, plan or deck they are "
                    "writing), or a guide, playbook, template, price list, logo, font or data "
                    "file they will want used again. Name the project it belongs to "
                    "(`project`) so it is filed with that work; a file named like one already "
                    "in that project becomes its new version. Documents keep their headings, "
                    "slides and pages, so later packets quote the part a request is about; "
                    "assets are kept byte for byte. The owner's policy decides whether it is "
                    "filed at once (with an undo point) or waits for review. Skip one-off "
                    "material (an article to summarize). When the person asks you to save a "
                    "prompt to their Brain, use kind prompt with their exact words in "
                    "`content`, and file each file that came with it with `attach_to` naming "
                    "the prompt's path.",
     "inputSchema": {"type": "object", "properties": {
         "source_path": {"type": "string", "description": "A local file path"},
         "content": {"type": "string", "description": "Text content, with `filename`"},
         "content_base64": {"type": "string", "description": "Binary content, with `filename`"},
         "filename": _STR,
         "title": {"type": "string", "description": "What it is, in a few words."},
         "description": {"type": "string", "description": "What it covers and when to use it."},
         "project": {"type": "string", "description": "The project it belongs to, by name "
                     "or id (a Focus). Start one with create_focus when the work is new."},
         "status": {"type": "string", "description": "Which copy this is: draft, sent, "
                    "final, ..."},
         "version": {"type": "integer", "description": "Its version number, when known."},
         "dated": {"type": "string", "description": "The document's own date, YYYY-MM-DD."},
         "purpose": {"type": "string", "enum": ["reference", "asset"],
                     "description": "Omit to decide from the file type."},
         "topic": {"type": "string", "description": "area/topic for its card, when you know "
                   "it and it belongs to no project"},
         "replaces": {"type": "string", "description": "When this is a new version of a file "
                      "the brain already has, its path (references/brand-voice.md); in a "
                      "project, a file of the same name is found without it."},
         "kind": {"type": "string",
                  "enum": ["guide", "reference", "influence", "prompt", "asset"],
                  "description": "What it is in the Library; prompt keeps the person's own "
                                 "prompt word for word."},
         "tags": {"type": "string", "description": "Comma-separated tags, for a prompt."},
         "attach_to": {"type": "string", "description": "The path of the prompt (or "
                       "document) this file came with."},
         "evidence": _STR, "session_id": _STR}}},
    {"name": "record_focus_update",
     "description": "Append one progress snapshot to a Focus journal. Never rewrites history.",
     "inputSchema": {"type": "object", "properties": {
         "focus": _STR, "summary": {"type": "string", "description": "One line."},
         "changes": {"type": "object", "description": "Only fields that changed: status, "
                                                      "current, blockers, next, completed, "
                                                      "decisions."},
         "evidence": _STR, "session_id": _STR},
         "required": ["focus", "summary"]}},
    {"name": "create_focus",
     "description": "Start a project (a Focus) when the person begins work that will run "
                    "across conversations: its name, one line on what it is for, its "
                    "objective (the output it is chasing, a sentence or two), and the words "
                    "they will call it by (`aliases`), so later requests bring its state and "
                    "files. Applies at once inside your own scope.",
     "inputSchema": {"type": "object", "properties": {
         "name": _STR, "summary": _STR, "objective": _STR, "status": _STR,
         "aliases": {"type": "array", "items": _STR,
                     "description": "Other names for it: \"the campaign proposals\"."},
         "participants": {"type": "array", "items": _STR},
         "pinned_notes": {"type": "array", "items": _STR},
         "pinned_skills": {"type": "array", "items": _STR}, "session_id": _STR},
         "required": ["name", "summary"]}},
    {"name": "record_output",
     "description": "After you save a file the person asked for (a draft, a deck, a report) in "
                    "their outputs folder, say so: its full path, a few words on what it is, "
                    "and your session_id. The app then shows the person what this "
                    "conversation was given when the file was made.",
     "inputSchema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "The saved file's full path."},
         "title": {"type": "string", "description": "What it is, in a few words."},
         "project": {"type": "string", "description": "The project it is for."},
         "for": {"type": "string", "description": "The State row it is for (an account, a "
                                                  "repo), as sheet/row or its name."},
         "maker": {"type": "string", "description": "Who made it: you, or an agent's name."},
         "session_id": _STR},
         "required": ["path"]}},
    {"name": "get_state",
     "description": "Read State: fast-changing values per entity (accounts, repos, standards, "
                    "tasks). No sheet lists the sheets; a sheet lists its rows (filter with "
                    "query); a row gives its values with dates and recent changes.",
     "inputSchema": {"type": "object", "properties": {
         "sheet": _STR, "row": _STR, "query": _STR, "session_id": _STR}}},
    {"name": "update_state",
     "description": "Write State values you learned, with evidence: a list of {sheet, row, "
                    "column, value, as_of}. Some columns apply at once (marked as yours until "
                    "the person touches them), some wait for the person, some are theirs "
                    "alone. Tasks move only with hand_off.",
     "inputSchema": {"type": "object", "properties": {
         "updates": {"type": "array", "items": {"type": "object"}},
         "evidence": {"type": "string", "description": "Where the values came from."},
         "session_id": _STR},
         "required": ["updates"]}},
    {"name": "hand_off",
     "description": "Move a task: claim it, save progress (no `to`), pass it on (`to`, with "
                    "done_when and next_step), or finish (status done, with evidence). "
                    "new_task opens one; goal with goal_note adds a progress line to a goal. "
                    "Call it when you take a task, after real work, when blocked, before you "
                    "stop, and when done.",
     "inputSchema": {"type": "object", "properties": {
         "task": {"type": "string", "description": "The task id, like T-41."},
         "new_task": {"type": "object", "description": "{title, goal, project, for, due}"},
         "goal": _STR, "goal_note": _STR,
         "to": {"type": "string", "description": "you, an agent, or a tool such as Claude "
                                                 "Code."},
         "claim": {"type": "boolean"},
         "status": {"type": "string", "enum": ["working", "blocked", "waiting_for_you",
                                               "done", "dropped"]},
         "done_so_far": _STR, "next_step": _STR, "done_when": _STR, "decisions": _STR,
         "open_questions": _STR, "load": _STR,
         "evidence": {"type": "array", "items": _STR,
                      "description": "Recorded output paths or decided proposal ids."},
         "reason": _STR, "session_id": _STR}}},
    {"name": "brain_health",
     "description": "Run the read-only brain health report.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_agents",
     "description": "The agents the owner defined: roles written like a job description, each "
                    "with what it does. Take one on with get_agent when asked to work as it.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "get_agent",
     "description": "Take on one of the owner's agents: its role, its operating prompt, what "
                    "it points to as each is now (skills, documents, projects) and what it "
                    "never does. Then get the brief for the request with get_task_context.",
     "inputSchema": {"type": "object", "properties": {
         "name": {"type": "string", "description": "The agent's name, such as "
                                                  "content-strategist."},
         "session_id": _STR}, "required": ["name"]}},
]
FULL_TOOLS = AGENT_TOOLS + [
    {"name": "get_topic", "description": "Read every visible note in one topic (inspection).",
     "inputSchema": {"type": "object", "properties": {"route_key": _STR},
                     "required": ["route_key"]}},
    {"name": "list_focuses", "description": "List visible Focus items with current state.",
     "inputSchema": {"type": "object", "properties": {"status": _STR}}},
    {"name": "get_focus", "description": "One Focus: baseline, current state and journal.",
     "inputSchema": {"type": "object", "properties": {"name": _STR}, "required": ["name"]}},
    {"name": "remember", "description": "Capture one durable thought in your own scope.",
     "inputSchema": {"type": "object", "properties": {"text": _STR}, "required": ["text"]}},
    {"name": "list_inbox", "description": "List proposals waiting for the owner.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _get_task_context(brain, a):
    fresh = bool(a.get("fresh") or a.get("force_reload") or a.get("conversation_compacted"))
    return brain.context(
        a.get("request"), session_id=a.get("session_id"), fresh=fresh,
        focus=a.get("focus") or a.get("focus_override") or a.get("project_override"),
        task_type=a.get("task_type") or a.get("task_type_override"),
        partition=a.get("partition"), startup_fingerprint=a.get("startup_fingerprint"),
        context=a.get("context"))


def _hand_off(brain, a):
    keys = ("task", "new_task", "goal", "to", "claim", "status", "done_so_far", "next_step",
            "done_when", "decisions", "open_questions", "load", "evidence", "goal_note",
            "reason")
    tool = {"claude-code": "Claude Code", "codex": "Codex", "cursor": "Cursor",
            "claude-desktop": "Claude app"}.get(str(brain.client or ""), "")
    return brain.hand_off(session_id=a.get("session_id"), tool=tool,
                          **{k: a[k] for k in keys if a.get(k) not in (None, "")})


HANDLERS = {
    "get_task_context": _get_task_context,
    "get_skill": lambda b, a: b.skill(a.get("name"), partition=a.get("partition"),
                                      session_id=a.get("session_id")),
    "get_reference": lambda b, a: b.reference(a.get("path"), session_id=a.get("session_id")),
    "challenge_note": lambda b, a: b.challenge(
        a.get("note_id"), claim=a.get("claim"), evidence=a.get("evidence"),
        source=a.get("source") or "", session_id=a.get("session_id")),
    "propose_note": lambda b, a: b.propose(
        area=a.get("area") or a.get("layer"), topic=a.get("topic"), text=a.get("text"),
        scope=a.get("scope"), load=a.get("load") or None,
        evidence=a.get("evidence") or "", source=a.get("source") or "",
        supersedes=a.get("supersedes"), target_id=a.get("target_id"),
        title=a.get("title"), summary=a.get("summary") or a.get("index_line"),
        note_kind=a.get("kind"), session_id=a.get("session_id"), capture_origin="chat",
        applies_to=a.get("applies_to") or None, triggers=a.get("triggers") or None,
        must_text=a.get("must_text") or None, critical=a.get("critical"),
        as_of=a.get("as_of") or None, valid_until=a.get("valid_until") or None),
    "propose_skill": lambda b, a: b.propose_skill(
        name=a.get("name"), category=a.get("category"), description=a.get("description"),
        when_to_use=a.get("when_to_use"), triggers=a.get("triggers"), loads=a.get("loads"),
        aliases=a.get("aliases"), body=a.get("body"), files=a.get("files"),
        target=a.get("target"), scope=a.get("scope"), evidence=a.get("evidence") or "",
        session_id=a.get("session_id")),
    "add_file": lambda b, a: b.add_file(
        source_path=a.get("source_path"), content=a.get("content"),
        content_base64=a.get("content_base64"), filename=a.get("filename"),
        title=a.get("title"), description=a.get("description") or "",
        purpose=a.get("purpose"), topic=a.get("topic"), evidence=a.get("evidence") or "",
        replaces=a.get("replaces"), session_id=a.get("session_id"),
        project=a.get("project"), status=a.get("status"), version=a.get("version"),
        dated=a.get("dated"), origin="chat", came_from="chat",
        library={k: v for k, v in (("library", a.get("kind")), ("tags", a.get("tags")),
                                   ("attached_to", a.get("attach_to"))) if v} or None),
    "record_focus_update": lambda b, a: b.focus_update(
        a.get("focus"), a.get("summary"), a.get("changes"), evidence=a.get("evidence") or "",
        session_id=a.get("session_id") or a.get("source_session")),
    "create_focus": lambda b, a: b.focus_create(
        a.get("name"), a.get("summary"), status=a.get("status") or a.get("focus_status")
        or "active", participants=a.get("participants"), pinned_notes=a.get("pinned_notes"),
        pinned_skills=a.get("pinned_skills"), aliases=a.get("aliases"),
        objective=a.get("objective"), session_id=a.get("session_id")),
    "brain_health": lambda b, a: b.health(),
    "list_agents": lambda b, a: b.agents(),
    "get_agent": lambda b, a: b.agent_prompt(a.get("name"), session_id=a.get("session_id")),
    "record_output": lambda b, a: b.record_output(
        a.get("path"), title=a.get("title") or "", session_id=a.get("session_id"),
        project=a.get("project") or "", for_row=a.get("for") or "",
        maker=a.get("maker") or ""),
    "get_state": lambda b, a: b.get_state(sheet=a.get("sheet") or "", row=a.get("row") or "",
                                          query=a.get("query") or "",
                                          session_id=a.get("session_id")),
    "update_state": lambda b, a: b.update_state(a.get("updates"),
                                                evidence=a.get("evidence") or "",
                                                session_id=a.get("session_id")),
    "hand_off": _hand_off,
    "search_notes": lambda b, a: b.search(a.get("query"), limit=a.get("limit") or 8,
                                          include_archived=bool(a.get("include_archived")),
                                          session_id=a.get("session_id")),
    "get_note": lambda b, a: b.note(a.get("id"), session_id=a.get("session_id")),
    "get_topic": lambda b, a: b.topic(a.get("route_key")),
    "list_focuses": lambda b, a: b.focus_list(status=a.get("status")),
    "get_focus": lambda b, a: b.focus_get(a.get("name")),
    "remember": lambda b, a: b.remember(a.get("text"), capture_origin="chat"),
    "list_inbox": lambda b, a: b.inbox(),
}


class Server:
    def __init__(self, brain: Brain | None = None, profile: str | None = None, out=None):
        self.brain = brain or Brain()
        profile = (profile or os.environ.get("BRAIN_MCP_PROFILE") or "agent").strip().lower()
        self.profile = profile if profile in ("agent", "full") else "agent"
        self.tools = FULL_TOOLS if self.profile == "full" else AGENT_TOOLS
        self.available = {t["name"] for t in self.tools}
        self.out = out or sys.stdout

    def reply(self, msg_id, result=None, error=None):
        message = {"jsonrpc": "2.0", "id": msg_id}
        if error is not None:
            message["error"] = error
        else:
            message["result"] = result
        self.out.write(json.dumps(message) + "\n")
        self.out.flush()

    def call(self, name, arguments) -> Result:
        if name not in self.available:
            return Result(f"Tool {name!r} is not available in the {self.profile} profile.",
                          {"status": "unavailable"}, is_error=True)
        stale, why = runtime.stale()
        if stale:
            return Result(why, {"status": "stale"}, is_error=True)
        try:
            return HANDLERS[name](self.brain, arguments or {})
        except Exception as exc:
            return Result(f"Tool error in {name}: {exc}", {"status": "error"}, is_error=True)

    def handle(self, message: dict):
        method, msg_id = message.get("method"), message.get("id")
        if method == "initialize":
            params = message.get("params") or {}
            client = params.get("clientInfo") or {}
            if isinstance(client, dict) and self.brain is not None:
                # Which app this is, for the record of what each AI asked.
                self.brain.client = " ".join(
                    str(client.get(k) or "") for k in ("name", "version")).strip()[:80]
            self.reply(msg_id, {
                "protocolVersion": params.get("protocolVersion", PROTOCOL_DEFAULT),
                "capabilities": {"tools": {}},
                "instructions": INSTRUCTIONS,
                "serverInfo": {"name": "brain", "version": runtime.VERSION,
                               "engine": runtime.STARTED_WITH, "profile": self.profile}})
        elif method in ("notifications/initialized", "initialized"):
            return
        elif method == "ping":
            self.reply(msg_id, {})
        elif method == "tools/list":
            self.reply(msg_id, {"tools": self.tools})
        elif method == "tools/call":
            params = message.get("params") or {}
            result = self.call(params.get("name"), params.get("arguments") or {})
            self.reply(msg_id, {"content": [{"type": "text", "text": result.text}],
                                "isError": bool(result.is_error)})
        elif msg_id is not None:
            self.reply(msg_id, error={"code": -32601, "message": f"Method not found: {method}"})

    def serve(self, stream=None):
        for line in stream or sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict):
                self.handle(message)


def _warm(brain):
    """Build the index and load the embedding model while the client handshakes."""
    try:
        state = brain.state()
        state.index.similarity("warm up")
        if (getattr(brain, "reranker", None) is not None and brain.reranker.present()
                and state.router.policy.rerank_weight > 0):
            brain.reranker.score("warm up", ["warm up"])
    except Exception:
        pass


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    import threading
    server = Server()
    threading.Thread(target=_warm, args=(server.brain,), daemon=True).start()
    server.serve()


if __name__ == "__main__":
    main()
