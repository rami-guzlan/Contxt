---
name: fill-gaps
description: The knowledge agent's gap check. Reads what AIs asked in the last month that the Brain could not answer, and says for each whether the owner should teach it (with the question to answer), whether a note already holds the answer under other words, or whether it was off-topic.
when_to_use: Every unanswered request is a hint of what the Brain should know. Run it weekly.
triggers:
  - fill the gaps in my brain
  - what could my brain not answer
  - find gaps in my brain
artifacts: []
loads: []
quality_gates:
  - questions are for the owner to answer, never answered from general knowledge
  - a note is named only when it is on the map
---
# /fill-gaps

You get the map of the Brain and candidates, each with a reference (`c1`, ...): a request an AI
made, what happened (nothing fit, or the AI searched and found a note), and the closest notes.

## For each request, decide

- `teach`: the Brain should know this and does not. Write the one question the owner can answer
  in a sentence or two (`"text"`). Several requests about the same thing get one question.
- `route`: a note on the map already holds the answer, but under other words. Name it (`"id"`,
  from the map) and give the words to add to its title or summary so it is found next time
  (`"text"`).
- `ignore`: a one-off or off-topic request (small talk, a test, a general question).

## Answer with one JSON object only

EXAMPLE, made up for the shape only; never copy its text:

```json
{"summary": "2 things to teach, 1 note to find better.",
 "findings": [
  {"ref": "c1", "verdict": "teach", "text": "What time do the webinars start, and in which time zone?", "why": "Asked twice this week."},
  {"ref": "c2", "verdict": "route", "id": "brand-colors", "text": "Add: hex codes, palette.", "why": "The note holds the hex codes."},
  {"ref": "c3", "verdict": "ignore", "why": "A test message."}
 ]}
```

Every candidate gets one finding; `why` is one short sentence.
