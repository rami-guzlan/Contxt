---
name: weekly-review
description: Run Taylor's Sunday evening review of the week ahead.
triggers:
  - weekly review
  - sunday review
  - plan next week
aliases:
  - review the week
artifacts: []
loads:
  - family/calendar
  - home/maintenance
  - money/budget
quality_gates: []
scope: person:taylor
invocation: explicit
---
# /weekly-review

Run the Sunday evening review.

1. Next week's calendar: pickups, Jamie's shifts, soccer, runs. Flag every clash.
2. Money: anything over budget this month, and any new subscription.
3. Home: maintenance due this month.
4. Projects: one next step each for the trip, the kitchen and the training.
5. Record progress on each project with a Focus update.
