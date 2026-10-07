# 6. Context first: the app is the Brain's front end

Date: 2026-10-06. Status: accepted.

## Context

The workspace grew around goals, to-dos, tasks, outputs, meetings, sheets and canvases, with a
Brain beside them. In use, the person who owns it relies on the context their AI gets in every
chat, and not on the workspace: goals, the to-do system and the task UI went unused, while the
app kept its own context (project memory, transcripts, docs) where no chat could see it. What
they need is context management: a place to add what they work on as they do it, so every AI
they use knows it, with progress, preferences, rules and conventions kept and governable.

## Decision

- **One store.** If an AI should know it, it lives in the Brain (files plus git). The app's
  database keeps app state only: sessions, settings, notes, events, and the task bus.
- **Seven places.** Home, Projects, Library, Review, Notes, Activity and Settings. Projects are
  the Brain's projects. The Library is the Brain browsed. Review merges what waited in two
  places. Notes are a private scratchpad that reaches the Brain only when the person adds a
  note or asks a model to find what to remember in it.
- **Removed:** goals, to-dos, tasks and outputs pages, meetings, project memory, sheets,
  canvases (and the Excalidraw package with the React pin it needed), the AI panel beside docs,
  to-do update requests (an entry that needs an update is marked so, with why), recall of
  outputs built on changed entries, per-project and automatic distillation, and the MCP tools
  for those features (`create_artifact`, `request_approval`, `propose_project_memory`,
  `suggest_todos`, `file_meeting_notes`, the work-item tools).
- **Kept under the hood:** the task bus and the local runner, for the AI work the app starts
  (finding what to remember, reconciling a clash). Its review machinery (approvals) stays for
  work with a required review; nothing in the app shows outputs, so no tool creates them.
- **Nothing is lost.** No table is dropped. The earlier workspace can be copied out as files
  and its context brought into the Brain once (`services/legacy.py`); the last full version is
  tagged `workspace-full-2026-10-06` in git.

## Consequences

The app is smaller and does one job. A new person gets a Brain and the pages to steer it; an
existing install keeps its data and moves its context in with two clicks. Capture from chats,
linked folders and seeing the Brain as a map build on this in later phases.
