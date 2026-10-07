---
name: investor-update
description: Draft Loopline's monthly investor update from the latest numbers.
triggers:
  - investor update
  - draft the monthly update
  - update for investors
aliases:
  - monthly update
artifacts: []
loads:
  - fundraising/investor-updates
  - ventures/loopline-metrics
  - fundraising/seed-round
quality_gates:
  - under 400 words
  - bad news stated plainly
  - three asks at most
scope: person:riley
---
# /investor-update

Draft Loopline's monthly investor update.

1. Pull the numbers from the latest metrics note: MRR and its growth, paying companies,
   churn, CAC payback, runway. Ask for anything older than 35 days.
2. Highlights: three at most, each with a number.
3. Lowlights: what went wrong, plainly, and what Riley is doing about it.
4. Numbers table: this month, last month, change.
5. Asks: up to three, each specific enough to act on (an intro to a named kind of person).
6. Keep it under 400 words. Return a draft: Riley sends it personally.
