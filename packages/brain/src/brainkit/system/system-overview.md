---
id: system-overview
title: How this brain works
keywords: brain architecture overview engine vault how does the brain work context packet areas people projects tiers state goals tasks updating loop
---
Engine and content are separate. `brainkit/` is the engine; `vault/` is this brain's content:
`brain.json` (shape and policy), `topics.md`, `routing.json`, `knowledge/` (governed notes),
`state/` (sheets of values that change often, each cell with its log), `goals/` (each goal's
shared plan), `skills/`, `references/`, `inbox/` (pending proposals) and `journal/` (Focus
updates, decisions and each goal's journal). Files are the source of truth and git is their
history.

Notes are filed as `knowledge/<area>/<topic>/<added>-<id>.md`: areas of the business
(company, customers, brand, marketing, sales, operations, and assistant for how the AI works
with you), people, one folder per project, and topics. Each note has a title saying what it
is for and a one-line summary. Its kind comes from one vocabulary (identity, rule, fact,
decision, procedure, value, project, goal) and says how it is used; its tier says how fast it
changes: alignment (who you are, what must hold, your goals), state (values and sheets),
knowledge (the rest). Who said it and when it was true ride with it. Old ids resolve through
`aliases.json`.

A request becomes a packet in three steps: the kernel (the company's, the role's and the
person's standing notes; the shared part in AGENTS.md, which CLAUDE.md imports) is already in
the session; `gnomon_get_context` routes the request to what the caller's scope admits; the
packet delivers only what is relevant and not already delivered in this session, with the
project's objective first, the must-holds of the task's domains, and a short "Current state"
block for the sheet rows it names. Goals never change what a request receives. Nothing is
cached on disk except embeddings and the session ledger, so every request reads the current
vault.

What changes the brain is governed: an AI proposes, code checks (tensions, baselines, dated
values, evidence quotes), and the owner decides in Catch up; the owner's own edits apply at
once with an undo point. Tasks move only through `todos_update`. The updating loop
(system-loop) keeps what the brain holds true over time, and the knowledge agent
(system-agent) suggests upkeep; neither writes a note on its own.
