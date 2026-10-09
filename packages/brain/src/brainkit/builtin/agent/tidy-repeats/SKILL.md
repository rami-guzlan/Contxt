---
name: tidy-repeats
description: The knowledge agent's check for redundancy. Reads pairs of notes that look alike and says, for each, whether they say the same thing (merge them), overlap in part (narrow one) or only look alike (leave both).
when_to_use: The Brain holds notes that repeat each other, often because the same rule or fact was captured twice.
triggers:
  - find repeats in my brain
  - merge duplicate notes
  - tidy repeated notes
artifacts: []
loads: []
quality_gates:
  - a merge keeps everything both notes said, and nothing more
  - only the pairs given are judged
---
# /tidy-repeats

You get the map of the Brain and a list of candidates, each a pair of notes (Note A, Note B)
that code found alike in their words, with a reference (`c1`, `c2`, ...).

## For each pair, decide

- `merge`: they say the same thing (or one says all of the other). Keep the better one
  (`"keep": "A"` or `"B"`) and write the merged note: everything either says, once, in the
  Brain's plain style, with nothing added. The other retires when the owner approves.
- `narrow`: they overlap in part but each also says something of its own. Rewrite one
  (`"which": "A"` or `"B"`) so it no longer repeats the other.
- `different`: they only look alike (different subjects, products, people or dates).

Read both in full before deciding. Two notes about different things that share words are
`different`. When in doubt, choose `different`: a wrong merge loses knowledge.

## Answer with one JSON object only

```json
{"summary": "2 of 3 pairs say the same thing.",
 "findings": [
  {"ref": "c1", "verdict": "merge", "keep": "A", "title": "Posting days", "text": "Posts go out on Tuesdays and Thursdays at 9am.", "why": "Both give the posting days; B adds the time."},
  {"ref": "c2", "verdict": "narrow", "which": "B", "text": "...", "why": "..."},
  {"ref": "c3", "verdict": "different", "why": "One is about the webinar, the other the podcast."}
 ]}
```

Every candidate gets one finding. `why` is one short sentence. Follow the owner's rules in the
startup context when one is given.
