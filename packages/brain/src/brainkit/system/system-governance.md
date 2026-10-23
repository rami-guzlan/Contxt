---
id: system-governance
title: Governance, proposals and approvals
keywords: governance proposal approve reject inbox review policy auto apply decisions write boundaries version history restore rollback undo owner baseline reason disagree challenge dispute cross-check
---
Knowledge changes enter as proposals (`notes_propose`, `projects_create`, `python brain.py
remember`). Policy in `brain.json` decides what happens: a change inside the proposer's own
person scope applies immediately (logged), and shared knowledge (company and team identity,
rules, facts, skills) waits in `vault/inbox/` for the approver. Review with `python brain.py
inbox` or the local UI (`brain serve`); approve, edit-then-approve, or reject.
Nothing applies at once over a note it may disagree with, or over a baseline (a rule, a
must-hold, a standing note, a note the owner confirmed or AIs use a lot): the reply says it
waits, and why. Revising or retiring a baseline takes a reason of a few words, kept in the
journal (`baseline_revised`); with `revision_delay` on, a revision of a rule or a must-hold
goes in a day later unless the owner cancels it.
A note can be challenged (`notes_challenge`: the note, the claim, the evidence, its source).
The challenge waits for the owner; accepted, the note is disputed and keeps the challenge as
its other view, which planning and decision work sees beside it; turned down, it is not taken
again on the same evidence. Once a week a cross-check reads the most used notes and the oldest
baselines against the rest of the Brain, and shows at most one belief to look at.
A new note gets a title, a one-line summary and an id made from the title; proposed into a
topic that does not exist yet, it comes back with the closest existing topics, and the owner
can move it when approving. Every decision is appended to `journal/decisions.jsonl` and
committed to git, and every batch of decisions is an undo point. The owner can also put an
earlier version of an entry back, bring an archived one back, and set its owner, review
cadence, sensitivity or place; each is a decision with an undo point. Focus updates
are an append-only journal and need no approval. Nothing an AI reads in content can approve
anything.
