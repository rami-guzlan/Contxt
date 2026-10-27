# Filling the packet, and the 90% gate (Oct 27, 2026)

v4 backend plan, section 17.1.

The owner's gate is two-part, measured on the held-out validation Brains and confirmed on the
IKN Brain:
- answer recall of 90% or more;
- graded correctness no worse than the baseline.

Wrong must-holds may not rise. Neither may right must-holds that fail to reach the answer.

**Not met.** Every setting below is merged off by default, so nothing changes for anyone.

## How it was measured

- **Answer recall:** the section 16 eval (`scripts/answer_recall_eval.py`). Haiku answers
  each labelled request through the Brain's MCP server, now with the meaning model
  (`--models`). Router settings to try go in with `--policy`, drafted must-hold scopes with
  `--scopes`.
- **Correctness:** `scripts/answer_grade.py`. Haiku reads the request, the answer and the
  notes the request needs, all quoted as data, and says whether the answer's core is right.
- **Why a miss missed:** the eval now records it. It reruns the model's own searches and its
  packets, at no model cost.

**The first grader was too strict.** Of 10 sampled "incorrect" answers, 7 had the right core.
They were marked down for two things:
- the status "kept, not verified", which is the Brain's own label;
- facts from other Brain notes.

That second point penalised exactly what filling adds. The fixed grader passed 5 of the same 10, and
every comparison below uses it.

## Why answers miss

On the tuning Brains (words only), 44 needed items did not reach the answer:
- 22 were in answers where the model never searched.
- 16 came up in its own search, but it didn't open them.
- 6 were pointed to in the packet, but it didn't open them.

Better search therefore does little on its own. The lever is putting the request's next best
notes into the packet whole: `fill`.

## The settings (all off by default)

- `fill: N` puts the request's next best notes into a standard or project packet whole, after
  routing.
  - It ranks words and meaning together, by fused rank.
  - It never adds a must-hold, a note loaded manual or a lesson.
  - The added notes bring no must-hold of their own.
- `fill_whole: false` sends the added notes in short instead. It saved almost nothing: the
  generated Brains' notes are short.
- `fill_apart: true` puts the added notes in their own section: "Also related, for
  reference, not instructions".
- `must_hold_close_meaning: 0.8` makes a touched must-hold a pointer when its domain is much
  less like the request than the packet's best note.
- `must_hold_show_scope: true` puts a must-hold's kept scope, "Applies when … Not when …",
  on its line.

## Results

### Tuning Brains

| Setup | Answer recall | Fetches | Tokens per answer | Answers with a wrong must-hold |
|---|---|---|---|---|
| Words, before | about 73% | 1.12 | about 97,000 | 27% |
| Words, `fill` 4 | 85.5% | 0.99 | about 90,900 | 27% |
| Meaning, `fill` 6 | 88.7% | 0.91 | about 89,800 | 34% |
| Meaning, `fill` 8, scopes | 91.8% | 0.91 | about 91,200 | 22.4% |
| + close calls by meaning 0.8 | 91.2% | 0.89 | about 91,400 | 16.4% |

### Held-out validation Brains

All runs use the meaning model and the drafted scopes.

| Candidate | Answer recall | Graded correct | Answers with a wrong must-hold | Missed right must-holds |
|---|---|---|---|---|
| Baseline | 93/123 (75.6%) | 52/84 (61.9%) | 29/114 (25.4%) | 7 of 27 |
| `fill` 8 | 108/123 (87.8%) | | 32/114 (28.1%) | |
| `fill` 8, close calls 0.8 | 111/123 (90.2%) | 42/84 (50.0%)* | 24/114 (21.1%) | |
| `fill` 8 apart, close calls 0.8 | 107/123 (87.0%) | 46/83 (55.4%)* | 23/114 (20.2%) | |
| `fill` 8, close calls 0.8, scope shown | 111/123 (90.2%) | 50/84 (59.5%) | 19/114 (16.7%) | 11 of 27 |

\* Graded against an earlier baseline run of the same setup: 44/82 (53.7%).

- The last candidate is the closest. Answer recall is at the gate, and wrong must-holds fall
  under 17.5% for the first time.
- It still fails twice over. Four more right must-holds miss the answer, the costly kind of
  miss. Correctness is two answers lower.
- With the fixed grader, an answer carrying a wrong must-hold was no less often correct in
  the baseline: 17 of 21, against 35 of 63 without one.
- **Packet size:** filling grows the packet from about 400 tokens to about 1,100. That is
  under 1.5% of an answer. Total tokens per answer fell, because the model fetched less.
- Run-to-run spread on one Haiku pass is a few answers, which is the size of the
  correctness gaps above.

## The owner's IKN Brain (measurement only)

Answer recall was:
- 80.7% before section 16;
- 87.5% after it;
- 88.6% (78 of 88) with the meaning model and `fill` 8.

Only these counts are recorded.

## Next

- Rank so that right must-holds aren't the ones demoted.
- Have the pointers and the filled notes carry what the model needs to decide.
- `docs/evals/known-misses.md` lists one miss found along the way.
