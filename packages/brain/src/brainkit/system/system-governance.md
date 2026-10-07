---
id: system-governance
title: Governance, proposals and approvals
keywords: governance proposal approve reject inbox review policy auto apply decisions write boundaries version history restore rollback undo owner
---
Knowledge changes enter as proposals (`propose_note`, `create_focus`, `python brain.py
remember`). Policy in `brain.json` decides what happens: a change inside the proposer's own
person scope applies immediately (logged), and shared knowledge (company and team identity,
rules, facts, skills) waits in `vault/inbox/` for the approver. Review with `python brain.py
inbox` or the local UI (`brain serve`); approve, edit-then-approve, or reject.
A new note gets a title, a one-line summary and an id made from the title; proposed into a
topic that does not exist yet, it comes back with the closest existing topics, and the owner
can move it when approving. Every decision is appended to `journal/decisions.jsonl` and
committed to git, and every batch of decisions is an undo point. The owner can also put an
earlier version of an entry back, bring an archived one back, and set its owner, review
cadence, sensitivity or place; each is a decision with an undo point. Focus updates
are an append-only journal and need no approval. Nothing an AI reads in content can approve
anything.
