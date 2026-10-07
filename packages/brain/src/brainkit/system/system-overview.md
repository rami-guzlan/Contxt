---
id: system-overview
title: How this brain works
keywords: brain architecture overview engine vault how does the brain work context packet areas people projects
---
Engine and content are separate. `brainkit/` is the engine; `vault/` is this brain's content:
`brain.json` (shape and policy), `topics.md`, `routing.json`, `knowledge/` (governed notes),
`skills/`, `references/`, `inbox/` (pending proposals) and `journal/` (Focus updates and
decisions). Files are the source of truth and git is their history.

Notes are filed as `knowledge/<area>/<topic>/<added>-<id>.md`: areas of the business
(company, customers, brand, marketing, sales, operations, and assistant for how the AI works
with you), people, one folder per project, and topics. Each note has a title saying what it
is for and a one-line summary; its kind (identity, rule, fact, state, focus) says how it is
used. Old ids resolve through `aliases.json`.

A request becomes a packet in three steps: the kernel (standing identity, rules and core
facts, rendered into CLAUDE.md/AGENTS.md) is already in the session; `get_task_context`
routes the request to what the caller's scope admits; the packet delivers only what is
relevant and not already delivered in this session. Nothing is cached on disk except
embeddings and the session ledger, so every request reads the current vault.
