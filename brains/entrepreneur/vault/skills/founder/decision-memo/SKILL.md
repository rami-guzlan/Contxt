---
name: decision-memo
description: Write a one-page decision memo with a recommendation first.
triggers:
  - decision memo
  - help me decide
  - write up the options
aliases:
  - memo
artifacts: []
loads:
  - me/principles
  - assistant/working-style
quality_gates:
  - recommendation first
  - one page
  - reversibility stated
scope: person:riley
---
# /decision-memo

Write a one-page decision memo.

1. The decision, in one sentence, and the date it is needed by.
2. Recommendation first, with the main reason.
3. Options: two or three, each with cost, risk and whether it can be undone.
4. What would change the recommendation.
5. Check it against Riley's principles: reversible first, sleep on commitments over
   $10,000 and every hire.
