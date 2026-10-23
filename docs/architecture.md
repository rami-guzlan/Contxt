# Architecture

The app is the Brain's front end: where a person sees and steers the context every AI they use
gets. Behind it sit three things: the Brain engine (`packages/brain`, files plus git), a small
application core (`packages/core`) for notes, the task bus that runs the app's own AI work and
the Brain's workspace side, and the adapters that serve them (`apps/server`). One codebase;
replaceable infrastructure. [ADR 0006](adr/0006-context-first.md) records why the app is
shaped this way.

```
 clients       web UI        CLI        worker        AI apps (Claude Desktop, Claude Code, ...)
                 |             |           |                |                    |
 interfaces   REST API  ------+-----------+       MCP endpoint (/mcp)    the Brain's own MCP
                 \__________________________________/                    server (brainkit mcp)
                                   |                                             |
 application              Workspace facade (packages/core)                       |
                 notes . brain . tasks . bus . events . actors . legacy          |
                                   |                                             |
 ports                    BrainPort            TextExtractor                     |
                              |                     |                            |
 adapters          packages/brain (brainkit) <------+----------------------------+
                                   |
 persistence   SQLite (default) or PostgreSQL . content-addressed files . Brain vault (git)
```

Chats reach the Brain through the Brain's own MCP server: every Claude Desktop or Claude Code
window starts one, and it reads and writes the same vault. The app's MCP endpoint (`/mcp`) is
narrower: it hands a model the AI work the app itself starts.

## Layers and rules

- **Domain** (`workspace_core/domain`): records, state machines, schedules and permissions.
  Pure Python; no I/O.
- **Application** (`workspace_core/services`): one service per aggregate, all behind the
  `Workspace` facade. Every method takes the authenticated `Principal` first, checks its
  grant, runs in one transaction, and appends its domain event in that same transaction.
- **Ports** (`workspace_core/ports.py`): what the core needs from outside, as protocols.
  Without a Brain, packets carry no long-term context and proposals are refused.
- **Adapters**: the REST API and MCP endpoint (`apps/server`) translate requests into facade
  calls and errors into status codes; they hold no business rules. The Brain adapter maps the
  port onto the `brainkit` engine.

## The main flows

**Files your AI can read.** A document added to the Brain (a project's page, Library, Files;
`files_upload` from any AI chat; a note added to the Brain; a swept folder) is filed with its shape
kept (Word headings, slides and pages become headings) and a card saying what it covers and
which copy it is. Filed into a project, a file named like one already there becomes its new
version: the text is replaced in place, the card says which version, git keeps the earlier
one. The Brain's capture policy files the owner's documents at once, as an undo point the
dialog offers right away; anyone else's wait for review. The routing engine splits every
document into sections and quotes the ones a request is about, chosen by meaning with the
local embedding model ([Routing](brain/ROUTING.md#filed-documents-the-part-that-answers-chosen-by-meaning)).
The server matches by meaning with a model already in the Brain's model folder
(`CONTXT_BRAIN_EMBEDDINGS`, on by default) and never downloads one. Every process that
writes the vault (the server and each chat's Brain process) takes one lock
(`brainkit/locking.py`), so two writers never interleave a change and its commit.

**Capture.** What a person brings in waits in Capture, private to them (no AI reads it), until
they pull from it or file it: a note typed here, a talk (hold Space or the Talk button
anywhere), a recording, an uploaded audio file, a transcript made elsewhere (Teams `.vtt`, Zoom
or SubRip `.srt`, text, Word) or a document. Each is a note (`services/notes.py`, an item of
kind `page`) that says what it is (`source_label`), keeps what was brought in in the object
store (never the Brain's git), and keeps versions. Audio becomes text on this computer: the
server's transcription worker (`apps/server/.../speech.py`) claims the oldest capture waiting
(`services/captures.py`), reports its progress and fills in its text (a recording with a
timestamp a paragraph). Transcripts read as turns, who spoke and when
(`brainkit.importers.transcript_turns`); a document reads as Markdown with its shape kept,
and filing it in the Brain files the document itself.

**Summaries.** Once a capture's text is in, a model writes its digest beside it: a summary,
key points each marked by how it fits what the Brain holds now (new, repeats, updates or
clashes, naming the entry), decisions, actions, open questions and people. It is a `digest`
task with the capture pinned, answered with `save_digest`. With summaries on (Settings, AI
apps; on by default) the server's digest worker (`apps/server/.../digests.py`) asks for one
as each capture's text arrives and runs it with the local CLI, one at a time; without a CLI
here, the request waits for a model like any AI work. The capture also lists, at once, the
entries it touches, found by meaning part by part (`Captures.related`). Nothing reaches the
Brain until the person pulls it in: "Pull into the Brain" is a distillation request with
their own words for what to keep, and its proposals wait in Review.

**Skills.** A skill is one of the Brain's procedures: its `SKILL.md` and the files beside it
(`services/skills.py`). The Skills place lists each with what it makes, the phrases a person
says to ask for it, the skills that build on it and its last run. How a person uses one
follows from what it is: most run here; one other skills only draw files from (fonts and
logos) is kept, not run; the Brain's own housekeeping (called by name, making nothing) runs in
a conversation, where it has the Brain's tools.

- **Run.** The person says what they need, optionally with a capture, a project and files the
  Brain holds. It is a `skill` task; the local CLI starts at once when it is ready, and the
  page shows its steps live. The model reads the skill with `get_brain_skill`, follows it with
  the Brain's context and saves what it made with `save_skill_result`: shown on the skill's
  page to copy, save as a note, or file in a project. Nothing is published or sent.
- **Files.** A skill that makes files (its `artifacts` name a format: pdf, docx, pptx, an
  image) runs in a folder of its own under the exports folder
  (`skill-runs/<date>-<skill>`, dated in the workspace's timezone): copies of the skill's
  files in `./skill` and of the skills it depends on, file and Python tools (`Read`, `Write`,
  `Edit`, `Glob`, `Grep`, `Bash(python:*)`; restricted mode keeps the file tools inside the
  folder), no web. When the run ends the copies go and what it made is listed with the run
  for download; pictures show in place. A marker file lets a server that stopped mid-run
  finish the folder on its next start, and run credentials older than any run's time limit
  are revoked then too (`Runners.sweep`).
- **Improve and New.** A request for a better version, or for a new skill from a description
  (or "Teach a skill" from a capture), is a `skill-draft` task answered with
  `propose_brain_skill`. An improvement can learn from an example: something the skill made
  ("Teach the skill from this") or a copy the person edited. The proposal waits in Review
  beside the skill as it is now. A person's own edit applies at once, as an undo point; every
  version is kept (`brainkit.history.skill_versions`) and an earlier one can be brought back
  to edit.
- **AI work.** The top bar lists what runs on this computer now, live, and what finished
  lately, each linked to the page its work belongs to.

Files a person or a model made are served so they never run in the app's origin
(`apps/server/.../files.py`): only pictures, audio and video show in place; everything else
downloads, sandboxed, its type never sniffed.

**Projects.** The projects people see are the Brain's (its Focus items): a brief, where the
work stands (status, now, next, blockers, decisions), an append-only progress journal, its
files and the notes filed with it, and the other names people call it by. A request that names
a project by any of those names brings all of that. The app lists them
(`GET /api/brain/projects`), opens one in full (`GET /api/brain/projects/{id}`), starts one
(`POST /api/brain/projects`), records progress (`POST /api/brain/projects/{id}/updates`, only
the parts of where it stands that changed) and changes its names (an `update` decision on its
entry, `fields.aliases`). The workspace's own `projects` rows stay as the task bus's boundary
underneath, each pointing at its Brain project (`brain_ref`).

**Notes.** A note is the person's scratchpad: a working-context item of kind `page`
(Markdown) in their own space, edited in the browser and saved as they type
(`services/notes.py`). Its revisions are grouped the way people work: saves by one person join
the version they are in until a ten-minute pause; a restore or a named version is sealed. A
note nobody named takes its first line as its title. A note is private: a model never finds
one by searching and opens one only when work assigned to it pins it (`context.open_to`), and
only people write notes. It reaches the Brain two ways: **Add to the Brain** files it as a
document, as it reads now, in a project when one is chosen; **Find what to remember** asks a
model to read it and propose what will last.

**The app's AI work.** Finding what to remember in a note is a task of template `distill`
with the note pinned at its current version, auto review, and an output contract naming
`propose_brain_entry` (`services/distill.py`). The model claims it like any work and calls
`propose_brain_entry` with its `run_id`, so every proposal names its task; the task closes when
the model finishes, and the proposals wait in Review. Reconciling a clash (template
`reconcile`) is its sibling: a person says which of a waiting proposal and an entry is
current, and a model rewrites the other so both can stand; its rewrite waits beside the pair.
A request no model can take yet waits as a draft without an assignee; the worker hands it to
the first model that can. Which model does this work is a workspace setting (none: the only
one connected).

**A model's check, and running work now.** `get_due_tasks` returns the caller's ready, due
tasks. `claim_task` atomically moves one to `claimed`, creates a run with a lease, and stores
the resolved packet on the run. Progress, heartbeats and blockers are run events;
`complete_task` ends the run. Besides a scheduled check, a person can start one task from the
app (`apps/server` `runners.py`, [Running the app's AI work](runners.md)): the server launches
a CLI on its own machine (Claude Code) as the task's model, with a credential minted for that
run and revoked at its end, an MCP configuration naming only this app, no built-in tools, and
none of the person's own settings. Its output becomes the run's console in the page. Any task
also yields a prompt to paste into any connected client. The task bus keeps its review
machinery (approvals) underneath for work with a required review; the app's own work uses
auto review.

**Reviewing the Brain.** Waiting proposals are reviewed in batches, grouped by the work that
made them (a request's run, a chat). The Brain's own analysis says what each would change:
entries it replaces, entries it contradicts, live entries it nearly repeats, other proposals
that say the same. A person approves the clear ones together, settles the rest one by one
(replace the old entry or keep both, move it to another topic), and can archive stale entries
in the same batch. Every batch is one undo point: undo puts back exactly the files it changed,
and is refused when any changed since. Review also lists what in the Brain wants a look
(clashes, near twins, misplaced text, entries to re-check).

**The Library and Activity.** The Library browses the whole Brain rather than only searching
it: an overview by area, every entry the owner can see by area and topic (including partitions
the owner owns), and the reference documents, assets and skills it holds (served as downloads
from `references/`, `assets/` and `skills/` only). Activity is the supply chain
([docs/brain/SUPPLY_CHAIN.md](brain/SUPPLY_CHAIN.md)): the log of everything that came in and
was decided with its undo points, the questions the Brain could not answer (gaps), and the
review and capture policies. An entry that needs an update is marked so, with what to check
(the engine's `mark`); it stays, ranked lower and flagged in packets, until someone confirms
or changes it.

**What your AI gets.** Home and every project page have a request box that shows the context a
request would get and why each piece is there, recording nothing (`GET /api/brain/preview`).

**The earlier workspace.** Goals, to-dos, meetings, project memory, sheets, canvases and the
AI work they ran are no longer part of the app, and no table was dropped
(`services/legacy.py`). Settings offers two steps. **Copy it out** writes everything they hold
to a dated folder anyone can read without the app (JSON, to-dos and memories as Markdown,
sheets as CSV, canvases as `.excalidraw`, every working item with its original file); the CLI
does the same (`contxt export-legacy`). **Bring it into the Brain** moves the context in
them to where every AI finds it: each project is matched to its Brain project (by the link it
has, else by name) or gets one; its memories, kept or still suggested, become proposals in that
project's topic, waiting in Review as one batch; meeting transcripts are filed into the project
their meeting fed, and documents into the project they were added to; a project's open to-dos
become its next steps. Each part happens once; running it again adds only what is new.

**Getting started.** The first-time setup (`services/onboarding.py`, Settings, Get started)
is a checklist worked out from the data itself: the owner's own name, a connected model or a
CLI here that can run the app's work, something of the person's in the Brain (or waiting for
their review), a project the Brain follows, and a file in it. Only what the data cannot say is
kept in the workspace's settings: finished, put aside, the tour taken, a step marked done as
is. The guided tour (`apps/web/src/components/tour`) walks every page with a spotlight on the
element it explains (marked `data-tour`), moving between pages as it goes.

## Invariants

1. Only the transitions in `domain/states.py` exist, whoever asks.
2. Every mutable row has a version; stale writes are refused (`VersionConflict`).
3. The run id is the fencing token: after a run ends or its lease runs out, nothing more can
   be written through it (`LeaseLost`).
4. Consequential writes accept an idempotency key; a retry returns the first result, a reuse
   for a different request is refused.
5. The event log is append-only, and every event names its actor.
6. Models never hold human release gates (decide proposals, govern the Brain, administer).
7. A packet stored on a run never changes.
8. A person's notes reach a model only pinned to work assigned to it.

## Storage

| What | Where |
|---|---|
| Records and events | SQLite `data/workspace.sqlite` (WAL) or `CONTXT_DATABASE_URL` |
| File bytes | `data/objects/<sha256>`, written once, shared by every reference |
| Pre-migration snapshots | `data/backups/` |
| Copies of the earlier workspace | `outputs/workspace-export-<date>/` in a Contxt home (`CONTXT_EXPORTS_DIR`; else `data/exports/`) |
| What skill runs made | `outputs/skill-runs/<date>-<skill>/` in a Contxt home (`CONTXT_EXPORTS_DIR`; else `data/exports/`) |
| Long-term context | the Brain vault: Markdown files in git, governed by `packages/brain` |

See the [decision records](adr/) for why each choice was made.
