---
name: freshen-up
description: The knowledge agent's freshness check. Reads notes past their review date or last day, and much-used notes nobody checked in months, and says which look time-bound (retire or update), which the owner should confirm, and which are clearly lasting.
when_to_use: Notes age. Run it weekly, or when the Brain shows stale notes.
triggers:
  - freshen up my brain
  - review stale notes
  - what in my brain is out of date
artifacts: []
loads: []
quality_gates:
  - a note is called lasting only when nothing in it depends on time
  - an update rests on a newer note named in `why`
---
# /freshen-up

You get the map of the Brain and candidates, each one note with a reference (`c1`, ...) and
why it is here (stale, or much used and unchecked).

## For each note, decide

- `ask`: only the owner can say whether it still holds (a price, an owner, a tool, a plan).
  Write the one question to ask (`"text"`), short enough to answer yes or no.
- `revise`: a newer note on the map already gives the update. Write the note's new text
  (`"text"`) and name the newer note in `why`.
- `retire`: it is plainly over (a past event, a finished campaign, a date that has passed with
  nothing after it).
- `lasting`: nothing in it depends on time (a definition, a principle, a lasting preference).

Prefer `ask` to `lasting` whenever the note names a figure, a date, a person in a role, a tool
or a plan.

## Answer with one JSON object only

```json
{"summary": "3 to confirm, 1 over, 2 lasting.",
 "findings": [
  {"ref": "c1", "verdict": "ask", "text": "Does the newsletter still go out every other Thursday?", "why": "Schedules change; last checked in March."},
  {"ref": "c2", "verdict": "retire", "why": "The September webinar is over."},
  {"ref": "c3", "verdict": "lasting", "why": "A writing principle."}
 ]}
```

Every candidate gets one finding; `why` is one short sentence.
