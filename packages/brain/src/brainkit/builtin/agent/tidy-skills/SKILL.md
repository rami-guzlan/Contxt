---
name: tidy-skills
description: The knowledge agent's skill check. Reads skills no AI used lately, skills with no words to ask for them, and pairs asked for with the same words, and suggests the phrases that would bring each up or which to retire.
when_to_use: A skill nobody can find is a skill nobody uses. Run it every few weeks.
triggers:
  - check my skills
  - tidy my skills
  - which skills are unused
artifacts: []
loads: []
quality_gates:
  - suggested phrases are what a person would actually type
  - a skill is suggested retired only when another skill covers it or its work is over
---
# /tidy-skills

You get the map of the Brain and candidates, each with a reference (`c1`, ...): one skill (no
words to ask for it, or unused lately) or a pair asked for with the same words (A then B).

## For each candidate, decide

- `triggers`: the phrases a person would type to ask for this skill, three to six, lower case
  (`"triggers"`). For a pair, give the phrases for the one that should keep the shared words
  (`"which": "A"` or `"B"`) and new phrases for the other in a second finding.
- `retire`: another skill on the map does the same work, or its work is plainly over
  (`"which"` for a pair).
- `fine`: it is rarely needed but right as it is.

## Answer with one JSON object only

```json
{"summary": "2 skills need better phrases; 1 overlap.",
 "findings": [
  {"ref": "c1", "verdict": "triggers", "triggers": ["write a podcast recap", "recap this episode"], "why": "No words to ask for it."},
  {"ref": "c2", "verdict": "triggers", "which": "B", "triggers": ["..."], "why": "..."},
  {"ref": "c3", "verdict": "fine", "why": "A yearly report."}
 ]}
```

`why` is one short sentence.
