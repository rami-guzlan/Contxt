# Does the world view earn its place? Oct 26, 2026

The v4 backend plan's section 13.7 evaluation, run on Claude Haiku (`claude-haiku-5-5`).

**Setup:**
- Twenty questions, labelled before any run and never tuned on (`scripts/world_eval_questions.json`): 8 about how entries relate, 8 about time, and 4 for orientation.
- Each question runs on a fresh test fixture Brain, seeded with:
  - three `relates` edges;
  - two project memberships;
  - a superseded day rate;
  - a dispute;
  - six dated decisions.
- Each runs through Claude Code headless with only the Brain's MCP server (`scripts/world_eval.py`, on the operating eval's harness).
- It runs two ways:
  - **with** is main after section 13 (#85 to #89): relations, the timeline, the world view, edges in packets and the since line;
  - **without** is the code from just before section 13 (38d4506), the same Brain and the same questions.
- Scoring is by code: a correct answer holds an expected term.

## Result

| | Correct | Relation | Time | Orientation | First packet | Pulls per answer | Input tokens per answer | Cost |
|---|---|---|---|---|---|---|---|---|
| With the world view | 14 / 20 | 7 / 8 | 3 / 8 | 4 / 4 | 442 | 1.45 | 105,087 | $0.102 |
| Without it | 14 / 20 | 7 / 8 | 3 / 8 | 4 / 4 | 435 | 1.40 | 101,017 | $0.099 |

The run cost $0.20 in all, under the $1 cap. As in the operating eval, about 68,000 of each answer's input tokens are Claude Code's own cached prompt.

**It does not earn its place yet.** By the plan's own ship rule (correct answers rise on these 20), it fails: the score is the same. It costs only about 7 tokens a packet, and the startup stays inside item 6's band.

**Why:**
- **Timeline:** Haiku never called `activity(action: "timeline")`, not even on the eight time questions. It searched notes instead. Nothing in the startup context or the packet points to the timeline; the only pointer is the since line, which a first conversation does not get.
- **Related:** it called `notes(action: "related")` twice (t6, t7). One of them was a time question it then answered from the edge (t7, "what was superseded").
- **The two runs differ on two questions:**
  - t4 ("disputed") went right without and wrong with;
  - t7 went right with and wrong without.
- **Wrong both ways:**
  - r6: a project member found only through "belongs to";
  - t2: the archived 2025 rate;
  - t3, t5, t6: decision dates, which live only in the journal.

**What would change it:** one line in the startup context's operating section, pointing at the timeline for "what changed" and "when". For example: `What changed or when: activity(action: "timeline", since)`. That has to be measured on new questions labelled before it is tried, not on these twenty, which are now spent for tuning.

## Second run: with the timeline line in the startup

The owner approved the fix: one line in the startup context's operating section,
"When, or what changed: `activity(action: "timeline", since)`".

To stay within the section's budget, the pull rule was shortened. It now reads "pull only what the task needs and the packet lacks; never to double-check", dropping "the map lists".

The run used a fresh set of twenty questions, labelled before any run (`scripts/world_eval_questions_2.json`, `--set 2`). They run on the first seed plus four new facts:
- a superseded proposal rule;
- a launch checklist;
- guest booking;
- five more dated decisions.

| | Correct | Relation | Time | Orientation | First packet | Startup file | Pulls per answer | Cost |
|---|---|---|---|---|---|---|---|---|
| With the world view and the line | 16 / 20 | 6 / 8 | 6 / 8 | 4 / 4 | 402 | 420 | 1.85 | $0.108 |
| Without (before section 13) | 9 / 20 | 4 / 8 | 1 / 8 | 4 / 4 | 381 | 410 | 1.65 | $0.102 |

The run cost $0.21, under the $0.50-a-side cap. Haiku called `activity(action: "timeline")` in 7 of the 20 answers, against 0 in the first run, and `notes(action: "related")` in 3.

**It earns its place now:**
- Correct answers rise by 7.
- Time questions go from 1 of 8 to 6 of 8.
- The packet grows by about 21 tokens, and the startup file by 10.

**Still wrong with the world view:**
- s1 and s15: what the proposal rule replaced. The archived old rule was not opened.
- s4: the project's member notes. It named one of the two.
- s10: the proposal limit before Oct 20. This needs the archived text.

The operating eval (#84) was rerun on the same startup to check that the shorter pull rule costs nothing elsewhere. Haiku again passed 10 of 10, for $0.051. The startup file is 420 tokens and the first packets are 346 to 548, as before. One case changed its calls: ask-before-send also called the timeline. None regressed.
