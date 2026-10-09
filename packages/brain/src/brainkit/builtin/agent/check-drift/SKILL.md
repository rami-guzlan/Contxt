---
name: check-drift
description: The knowledge agent's drift check. Reads notes that something newer in the Brain may contradict (a note that went in on its own, an older dated value, a belief the weekly cross-check flagged) and says which is current, suggesting an update, a retirement or a dispute.
when_to_use: Facts change: figures, dates, owners, tools. Run it to keep what AIs are told current.
triggers:
  - check my brain for drift
  - what is out of date in my brain
  - check contradictions in my brain
artifacts: []
loads: []
quality_gates:
  - every verdict rests on the texts given, quoted where it matters
  - nothing is retired that is still the only source of something
---
# /check-drift

You get the map of the Brain and candidates, each with a reference (`c1`, ...). A candidate is
a pair (A then B: a note and what may contradict it, or an older and a newer dated value) or one
belief with the evidence against it.

## For each candidate, decide

- `revise`: the note is out of date and the newer text says what is current. Write the note's
  new text (`"which": "A"` or `"B"`, `"text"`), keeping what is still true.
- `retire`: the older note is fully replaced by the newer one (`"which"`: the one to retire).
- `dispute`: they truly disagree and the texts cannot settle which is right: the owner should
  decide (`"which"`: the note to mark disputed).
- `fine`: no real contradiction (different scope, different time, or both true).

Prefer `fine` when the texts can be read as both true. Never decide from general knowledge:
only from the texts given and the map.

## Answer with one JSON object only

```json
{"summary": "1 value changed, 1 real disagreement, 2 fine.",
 "findings": [
  {"ref": "c1", "verdict": "retire", "which": "A", "why": "B gives the new price as of October."},
  {"ref": "c2", "verdict": "revise", "which": "A", "text": "...", "why": "..."},
  {"ref": "c3", "verdict": "dispute", "which": "A", "why": "The notes give two owners for the newsletter."},
  {"ref": "c4", "verdict": "fine", "why": "One is about 2025, the other 2026."}
 ]}
```

Every candidate gets one finding; `why` is one short sentence.
