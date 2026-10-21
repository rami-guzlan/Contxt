# General retrieval: plan

Plan only: no code was changed. Written October 16, 2026, at Rami's question: "is this approach
developing a generalized scalable system? ... a system that will be able to do high-quality
retrievals and packet generations from anybody's brain context data? If not, rethink the
context retrieval system." File paths are relative to the Contxt repository; "BL" cites
`brain-logic-plan.md` beside this file.

## 1. The answer, measured

Not yet. The write path, governance, delivery and session tracking are general. The part that
decides what a request gets (the relevance layer in `router.py`), and the way it has been
measured, are fitted to the people who built it.

**The relevance layer runs on hand-set numbers and hand-written hints.**
- `router.Policy` holds 61 thresholds and weights (the 0.42 note floor, the 0.46 lean floor,
  72% of the best, 0.57 for must-holds, 0.60 and 0.90 for file parts, and so on).
- Each was set on a handful of requests, against one real Brain (IKN) and four demo Brains
  written by the same person.
- On top of them, each Brain can carry hand-written routing (`routing.json` intents, topic
  hints such as `requires_any`, house-style lists, must-hold trigger words, `topics.md`
  lines). Rami's IKN Brain carries 4 intents, 25 topic hints, 9 house-style notes and 26
  topic lines. A new person's Brain carries none.

**Measured on the IKN Brain's own 68 labeled requests, by meaning** (October 16, private copy
on F:):

| IKN Brain | Recall, tuning (46) | Recall, held out (22) | Precision, tuning / held out |
| --- | --- | --- | --- |
| As configured | 98% | 88% | 82% / 76% |
| No `routing.json` | 82% | 84% | 63% / 66% |
| No `routing.json`, no `topics.md` (as a new person's Brain starts) | 84% | 88% | 63% / 60% |

Three things follow:
- **The 98% is the configuration.** Without the hints written against those same requests,
  tuning recall falls to the held-out level. That is fit, not generality.
- **Out of the box, recall is about 85%, but precision falls to about 62%.** The hand-written
  hints were doing the precision work: what anybody else's Brain will see today is briefs
  where nearly 4 notes in 10 are not needed.
- **The demo numbers vary by Brain** (recall 60% to 100% across the four starters, words and
  meaning). Small, single-author test sets cannot say how a fifth Brain will do.

The evaluation shares the problem: 48 demo requests and 68 IKN requests, written by the people
who tuned the router, with held-out sets that have already been inspected. One request moves a
number by 2 to 12 points.

**What stays (already general):** the governed write path and the door checks, admission
before relevance (scope, partition, load), every note competing on its own, session tracking
and "already held", budgets, must-holds attached by domain, packets that explain themselves,
modes for exact notes, skills, projects and standing answers.

## 2. Principles

1. **Zero-config is the product.** Headline numbers are measured on Brains with no
   `routing.json` and no `topics.md`, on Brains nobody tuned on. Hand configuration becomes an
   optional override, measured separately.
2. **Improve the Brain's text, not the router.** What a person once wrote by hand (topic
   lines, `requires_any`, intents, trigger words, house-style lists) is produced from each
   note when it is approved, by the model the person chose. The owner sees it and can edit it.
3. **No thresholds that depend on one corpus.** Candidates come from rank fusion, which needs
   no score scales. The line between "something" and "nothing" is calibrated per Brain against
   requests that have nothing to do with it.
4. **The calling model is the last judge.** Whole notes only when the Brain is confident;
   pointers (a title and how it is asked for) for the rest, which the model opens when it needs
   them. The router has to be high-recall and well-calibrated, not perfect.
5. **Learn from use, per Brain.** What a conversation opened, or had to search for, refines that
   note's text. Every Brain improves the same way, without an engineer.
6. **Measure generalization, not fit.** Many Brains, leave-one-Brain-out, a sealed test set,
   third-party data, confidence intervals, and the worst Brain reported beside the mean.

## 3. The design

### 3.1 Enrichment at the door (document expansion)

When a note is approved, and once for every note already in a Brain, one model call writes its
retrieval fields into its front matter:

| Field | What it holds | Replaces |
| --- | --- | --- |
| `asked_as` | 5 to 10 ways a person would ask for this, in plain words, avoiding the note's own vocabulary where it can | `topics.md` lines, `fit_terms`, `phrases`, aliases |
| `applies_when`, `not_when` | one line each: the work this note is for, and look-alike work it is not for | `requires_any`, intents' include and exclude |
| `role` | knowledge, rule, style (how to write, not what), procedure, or pointer | `house_style_notes` and `house_style_topics` |
| `triggers` (must-holds) | the ways people talk about the rule's domain | hand-written trigger words |

- **Indexed as fields** beside the note's own text, by words and by meaning (each `asked_as`
  line embedded on its own, a note scored by its closest line).
- **The model** is the knowledge agent's (the CLI here by default, any model the person picks).
  A small model is enough. Without one, a note is indexed as it is: it still works, it is
  found less often.
- **Governed text.** The fields are part of the note, versioned with it. The entry page shows
  "Found when you ask: ..." and the owner can edit it. Triggers the model suggests for a
  must-hold wait for the owner's yes, like the must-hold itself.
- **Cost:** one call per note, about 400 tokens in and 200 out. A thousand notes is about
  600,000 tokens once.

### 3.2 Candidates by rank fusion

Words (BM25 over the note and its enrichment) and meaning (the closest of its embedded lines)
each rank every admitted note. Reciprocal rank fusion merges the two rankings into about 30
candidates. Ranks need no calibration: the same code works for a Brain of 30 notes or 30,000,
in any domain, with any embedding model.

### 3.3 Calibrated selection: each Brain against a null set

The engine ships a bank of about 300 requests unrelated to any Brain: general knowledge, small
talk, arithmetic, chores, other professions' work. When a Brain's index is built, it scores
the bank once.
- The best score an unrelated request reaches in this Brain sets its "nothing" bar (a high
  percentile of that distribution). A request whose best candidate does not beat what
  unrelated requests reach gets nothing, said so.
- A higher percentile sets the bar for sending a note whole.
- Must-hold domains and file parts use the same calibration.

This replaces the absolute floors (0.42, 0.46, 0.57, 0.60, 0.80, 0.90) with bars each Brain
sets for itself, whatever its size, its notes' length, its vocabulary or its model.

### 3.4 Three tiers: whole notes, pointers, nothing

- **Whole notes:** candidates above the confident bar, best first, inside the budget.
- **Pointers:** the next candidates above the nothing bar, as a title and their closest
  `asked_as` line. The model opens one with `notes_get` when the task needs it.
- **Nothing:** below the nothing bar, with the closest pointers and an instruction to say the
  Brain has nothing.

Today's "in short" notes and "Also relevant" list become this one rule. Precision is measured on
whole notes; recall on whole notes plus pointers (what the model can reach in one call).

### 3.5 Learning from use

The ledger already records what each conversation was handed, what it opened afterwards, and
what it found by searching that no brief brought (a "searched" gap).
- A searched gap adds the request's wording to that note's `asked_as`. In the owner's own scope
  it applies at once, as an undo point; elsewhere it is a proposal.
- A pointer opened in most conversations that get it is a sign the note should come whole: the
  report says so, and the next calibration counts it.
- No learned weights at first: the Brain's text improves, and the ranking stays the same code
  for everyone.

### 3.6 What happens to hand configuration

`routing.json` and `topics.md` stay readable and keep working as overrides. A topic with no
line in `topics.md` is described from its notes' enrichment. The IKN Brain is measured both
ways, so the gap between configured and zero-config is visible and shrinks as stages land.

### 3.7 Language and scale

- **English first.** The stop-word list, the stemmer and bge-small are English. The embedding
  model and word lists are per language; a multilingual model (bge-m3, multilingual-e5) is a
  setting, offered only after it is measured.
- **Scale.** The index updates note by note instead of rebuilding. Target: p95 under 150 ms
  warm at 5,000 notes, tested on generated Brains of 50, 500 and 5,000 notes.

## 4. How we will know

### 4.1 The Brains

| Kind | What | Why |
| --- | --- | --- |
| Real | IKN (private: on F: and in the private `ai-brain` repo, never in this one); more real Brains later, with their owners' consent | real notes, real wording |
| Demo | the four starters | shipped, public |
| Generated | Brains across about 12 personas and jobs (a dentist, a lawyer, a teacher, a founder, an engineer, a nonprofit, a household...), at 50, 500 and 5,000 notes | breadth and scale; labels known by construction |
| Third-party | public long-term memory benchmarks (LongMemEval, LoCoMo): conversations brought in through Capture and distillation, their questions asked as requests | data nobody here wrote; tests the whole path, not only retrieval; licenses checked first |

Generated Brains: one model writes a persona's notes; requests are written by a different model
from the persona alone, never from the notes, so they do not share the notes' vocabulary. The
generator records which note answers each request.

### 4.2 Splits

Brains are split, not requests: tuning Brains, validation Brains, and sealed test Brains nobody
looks at until a stage ends. Anything fitted is checked leave-one-Brain-out.

### 4.3 Measures

Whole-note precision, reachable recall (whole notes and pointers), correct nothing (on the
null bank and on held-out off-topic requests), false nothing, must-hold recall and decoys,
tokens per brief, p95 latency. Each with a confidence interval; the mean across Brains and the
worst Brain; zero-config always, configured beside it.

### 4.4 Gates

A change ships when it raises the validation mean by more than its interval and makes no Brain
worse by more than its interval. The sealed test is reported once per stage. Later, the Lab's
blind comparison of answers with and without a brief (testing-lab plan) checks that better
retrieval makes better answers.

### 4.5 In CI

A quick set (the demos, two small generated Brains, the null bank) runs with the meaning model
on every pull request, with minimums at the last measured values. The full set runs before a
release. The byte-for-byte parity test retires for the relevance layer (it pins today's
behavior, which is what this plan changes) and stays for packet rendering.

## 5. Stages

| Stage | What | Changes behavior? |
| --- | --- | --- |
| 0 | The harness: multi-Brain runner, zero-config mode, leave-one-out, intervals, the null bank, the Brain generator, the IKN private set, a baseline report | No |
| 1 | Calibrated selection against the null set (3.3), replacing the absolute floors | Yes |
| 2 | Rank-fusion candidates and the three tiers (3.2, 3.4) | Yes |
| 3 | Enrichment at the door, a backfill for existing notes, "Found when you ask" on the entry page (3.1) | Yes |
| 4 | Learning from use (3.5) | Yes |
| 5 | Hand configuration becomes optional; `topics.md` described from enrichment (3.6) | Yes |

Each stage is a branch and a pull request, measured against stage 0's baseline. Goals, not
promises, for zero-config on Brains nobody tuned on:
- reachable recall 90% or more held out;
- whole-note precision 80% or more;
- correct nothing 95% or more on the null bank;
- false nothing 3% or less.

## 6. Decisions for Rami

1. Zero-config numbers become the headline (recommended).
2. Enrichment makes one model call per note, through the knowledge agent's model (the CLI here
   by default). Without a model, notes are indexed as they are.
3. Generated Brains and requests are written by a model (Claude Code by default), a one-time
   cost per test Brain.
4. Third-party benchmarks (LongMemEval, LoCoMo) are downloaded once their licenses are checked.
5. The IKN private set stays on F: and in the private `ai-brain` repo; only aggregate numbers
   appear in this repository.
6. Stage 0 starts now: it changes no behavior.
