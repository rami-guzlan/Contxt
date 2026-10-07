---
name: write-adr
description: Write an architecture decision record for a change to services, data or team rules.
triggers:
  - write an adr
  - architecture decision
  - decision record
aliases:
  - adr
artifacts: []
loads:
  - work/architecture
  - references/route-planner-architecture.md
quality_gates:
  - two or three options
  - consequences listed
scope: person:kai
---
# /write-adr

Write an architecture decision record for a change that affects how services talk, where
data lives, or what the team must not do.

1. Title: the decision in a few words, as a statement.
2. Context: what forces the decision, with numbers where there are any.
3. Options: two or three, each with its main cost.
4. Decision: the chosen option and why it beats the others.
5. Consequences: what gets easier, what gets harder, what to watch.
6. Save it as `docs/adr/NNNN-short-title.md` in the repository being changed, and list who
   should review it (Dana for any change to service boundaries).
