---
name: check-alignment
description: The knowledge agent's alignment check. Weighs the Brain against the owner's goals and projects. Asks the questions that would fill the biggest gaps, suggests retiring notes that serve no goal, and gives must-holds the words that bring them up.
when_to_use: The Brain should serve what the owner is trying to do. Run it after the goals or projects change, or every few weeks.
triggers:
  - check my brain against my goals
  - is my brain aligned
  - what is my brain missing for my goals
artifacts: []
loads: []
quality_gates:
  - every question names the goal or project it serves
  - a note is suggested for retirement only when it serves no goal, project or rule
---
# /check-alignment

You get the map of the Brain and candidates, each with a reference (`c1`, ...):

- **The goals and projects** (`kind: goals`): the owner's own words on what the Brain is for,
  and the active projects. Compare them with the map: which goals or projects does the Brain
  say little or nothing about?
- **Must-holds with nothing to bring them up**: rules that must reach every brief in their
  domain, but name no words or areas that put the domain in play.
- **Notes no AI used in months**: do they serve a goal, a project or a standing rule?

## For each candidate, decide

- For the goals and projects: `question` for each real gap, at most five, the most useful
  first: one question the owner can answer in a sentence or two (`"text"`), naming the goal or
  project it serves in `why`. Nothing missing: `fine`.
- For a must-hold: `triggers`, with the words and phrases a request would use when its domain
  is in play (`"triggers": [...]`, three to eight, lower case).
- For an unused note: `retire` when it serves no goal, project or rule (old campaigns, one-off
  details); `keep` when it does, even if rarely needed.

## Answer with one JSON object only

```json
{"summary": "2 gaps for the Q4 goal; 1 note off the goals.",
 "findings": [
  {"ref": "c1", "verdict": "question", "text": "Who signs off on webinar invitations?", "why": "Q4 webinars: the Brain has no approver for them."},
  {"ref": "c1", "verdict": "question", "text": "...", "why": "..."},
  {"ref": "c2", "verdict": "triggers", "triggers": ["press release", "media", "journalist"], "why": "..."},
  {"ref": "c3", "verdict": "retire", "why": "A 2024 trade show that is over."},
  {"ref": "c4", "verdict": "keep", "why": "The pricing rule still applies."}
 ]}
```

A candidate may get several `question` findings; every other candidate gets one finding.
