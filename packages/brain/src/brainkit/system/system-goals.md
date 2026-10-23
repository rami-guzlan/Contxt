---
id: system-goals
title: The goal ladder: purpose, goals, agent goals
keywords: goal goals ladder purpose check-in check in agent goal measure signal board shared plan coach on track off track
---
The ladder has three kinds of goal, and none of them filters what a request receives. The
Brain's purpose is the `you-goals` note: why the Brain exists, with no target and no end. Your
goals (optional) and agent goals are notes of kind `goal`, loaded `manual`: open one by its id
with `notes_get`, which brings its shared plan (the board blocks the owner marked "Your AIs can
read this"; private blocks never leave the app). A goal has a level (yours or agent), a why, a
cadence, an optional due date and a measure: entered at check-in, or computed by code from a
signal (overdue much-used notes, items waiting, unanswered questions, quiet projects). Each
goal keeps an append-only journal (`journal/goals/<id>.jsonl`) of check-ins, progress notes
and decisions, and every check is a point in the ledger's `goal_checks`. The owner's latest
call sets their goal's status; a computed measure that disagrees shows as a flag beside it.
Agent goals are computed, and only a slip (turning off track) reaches Catch up, once. Propose
an agent goal with `notes_propose` and kind `goal`; it waits for the owner. Projects link to the
goals they serve; each has an objective that opens every brief in it.
