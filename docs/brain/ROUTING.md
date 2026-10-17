# Routing

Routing is deterministic: the same vault and the same request give the same packet, and
`brain context "<request>" --explain` shows why. There is no language model in the
loop; the only model is a small local embedding model (BAAI/bge-small-en-v1.5 through
`fastembed`), which turns text into vectors. A vault may name another in `brain.json`
(`"embeddings": {"model": "BAAI/bge-base-en-v1.5"}`); `MODEL_SCALES` in `index.py` holds each
model's measured similarity scale. A server process (`local_models`) only uses a model
already in `vault/.brain/models` and never downloads one; without a model, routing uses
words alone.

## Retrieval hints follow the note's version

The Knowledge Agent can write `asked_as` and `applies_when` lines to help find a note.
Those lines are additional search evidence, not a guarantee that the note answers a request.
When the note's title, summary or body changes, versioned hints stop contributing to words,
meaning, generated topic descriptions and must-hold domain descriptions until refreshed.
The note's current text is still searchable, and its old hints remain stored for review.
Legacy owner-written hints without a recorded content hash continue to work.

An enrichment job carries the note version it read. If either the content or the owner's
metadata changes during the model call, its answer is rejected instead of overwriting the
new version. Retrying reads the current note. Rewording `asked_as` after a content edit does
not reactivate the old model's applicability fields.

Calibration is reused only while its bank, model and retrieval inputs match. Editing a note
or its hints can change the meaning distribution even when the note count stays constant,
so those changes invalidate calibration. This changes cache freshness, not ranking formulas
or the calibrated evidence thresholds.

## Order of precedence

| Mode | Triggered by | Delivers |
|---|---|---|
| exact-note | the request is a note id or alias | that note |
| exact-skill | `/name`, or a skill's exact name or alias | the procedure pointer plus the knowledge its `loads` name |
| portfolio | "what is active", "orient me in the brain" | every visible Focus, active first |
| system | questions about the brain itself ("brain MCP", "routing gap") | engine docs; the `system_skill` for deep work |
| focus-update | a request naming a Focus and stating progress ("X approved the outline") | the Focus and an instruction to call `record_focus_update` |
| focus-only | a question about a named Focus, or a status question ("latest on ...") | its current state, baseline and files; for a question about its content, the file parts that answer it |
| focus-aware | work on a named Focus | the Focus, its pinned notes, its project folder, its files, and standard routing |
| standing | "may I publish/send ..." or a lookup the kernel already answers | pointers to the standing notes that answer it |
| lean | nothing clears the evidence floor, and no file part answers it on its own | the closest notes and files, listed, and an instruction to say so |
| standard | everything else | notes, skill candidates, references, and the parts of filed documents that answer it |

A request names a Focus by an alias, by its full name plus a status or work word, by a word
only that Focus uses, or by its distinctive name as a phrase ("30 60 90", "bank of china")
when that phrase is rare in the brain.

## Standard routing: every note competes

Where a note is filed never decides whether it can be found. Every note the caller may see
is scored on its own, and topics only add evidence. A note approved into a brand-new topic is
therefore found on the very next relevant call.

1. **Signals.** Question or instruction, task type (knowledge, workflow, combined), scale
   (micro, standard, deep), artifact words, short-form, requested source documents,
   follow-up edits, and any `intents` that match.
2. **Skills.** Visible skills are scored on their declared phrases, name, artifacts, BM25
   and embeddings. Standard work lists up to three candidates; deep work with a decisive
   winner routes that procedure. The topics the credible candidates `load` become the
   task's declared domains, as do intent `include_topics`, a named Focus's pins and project
   folder, and on a follow-up the previous packet's topics.
3. **Relevance of each note.** Half lexical (BM25 over title, summary and body: how much of
   the request the note covers, and its rank), half semantic (cosine similarity, which must
   also stand out from the other notes for this request, z-scored per request). A request
   word no note contains counts as a strong miss, so "tell me the weather" is not carried by
   "tell". The query is embedded with the model's retrieval instruction. Multiword terms are
   read as one word on both sides ("call to action" is "cta", so it does not match notes
   about cold calling); a vault adds its own in `routing.json` `phrases`.
4. **Soft evidence.** Added to relevance, never gating:

   | Signal | Lift |
   |---|---|
   | the note's topic, read as a whole, matches the request (its topics.md line, or what is filed in it) | `topic_prior` x topic relevance (0.15 x 0..1) |
   | the note's topic is a declared domain | `domain_boost` 0.05 |
   | a topic `fit_terms` word is in the request | 0.03 per term, at most two |
   | the note was added or approved in the last 14 days | `fresh_boost` 0.05, and "(new)" in the packet |
   | the topic's `requires_any` words are all missing, and the request does not name the note (`gate_named`: 60% of its weighted words, two or more, in the note) | x `gate_factor` 0.65 |

5. **Selection.** Notes at or above `max(0.42, 72% of the best)` (80% for a one-answer
   lookup) go in, best first, at most 4 per topic (5 for lookups and deep work). A declared
   domain nothing was picked from adds its best note when that note scores at least 0.42.
   Notes named by an intent (`include_notes`) and topic caveats (`with_notes`) are added.
   The next notes down are listed by title under "Also relevant (not included)"; the agent
   opens one with `get_note`, and when something is still missing it can `search_notes` in
   its own words.
6. **House style.** A writing task gets the owner's ordered core list
   (`house_style_notes`) first, then the rest of `house_style_topics`, most relevant first,
   within 45% of the note budget. Style rules are about how to write, not what, so the owner's
   order beats relevance for them.
7. **Budget.** House style, then the selected notes in order, while they fit. The budget is a
   ceiling, not a target. A follow-up edit gets a small budget and only notes that stand out.
   Nothing selected is dropped: a note too long to come whole comes in short (its title,
   summary and closest sentence), and one past the budget even in short, or a core style rule
   past the style share, is named under "Did not fit" for the model to open with `get_note`.

## Filed documents: the part that answers, chosen by meaning

A document filed in the brain (`add_file`: a proposal, a brief, notes from a meeting, a
guide) keeps its shape: Word headings, slides and PDF pages become headings
(`importers.to_markdown`). The index splits each one at its headings into sections of a
readable size (`sections.py`; a long section is cut into parts at paragraph ends), and
embeds each section with its file's title and its headings. Nothing is stored: sections are
derived whenever the index is built, so a new version is split anew.

**Meaning decides.** With the embedding model, a section is quoted when its meaning is close
to the request's (its similarity, capped by how far it stands out from every other section
for this request), whatever words the two share. Measured 2026-10-06 on 25 labeled requests
over a copy of a real brain with an invented campaign project: meaning found the right part
for 15 of 15 questions asked in a person's own words ("how much did I set aside for the
podcast?" reaches "Podcast sponsorship ... Budget: 4,500 dollars"), word rules for 9, and a
cross-encoder reader did worse than both. Larger embedding models (bge-base, arctic-embed-m)
did not do better on the same tests, so the small one stays.

| Section of | Quoted when its meaning is at least | Notes |
|---|---|---|
| a work file (`type: file` on its card) | 0.60 | the request naming the file or its project lowers the bar by 0.10, and lifts the project's sections by 0.08 |
| a guide kept whole (no type on its card) | 0.90 | a writing task gets none unless it names the guide: the house-style notes already carry its rules |

**A writing task quotes the material it works on**: a file it names, or a file of the project
it names. Another work file that shares the subject (a deck page on AI leadership for "write
a LinkedIn post about AI leadership") is raw material the notes have distilled; its card is
listed under "Also relevant" instead, so the AI can open it.

**A request nothing else backs needs a part that answers it on its own.** When no note, file
card, project or procedure is about the request (it would get a lean packet), a part is
quoted only when the request names its file or its meaning is at least 0.80. A long
conversational file has a part that sounds like almost anything: in a real meeting
transcript, a passing plan to pick something up tomorrow matched "tell me the weather
forecast for tomorrow" at 0.69, and turned a lean packet into a full one. Measured 2026-10-06:
everyday requests reached at most 0.73 that way. A part held back this way points to its
file among the closest matches; naming the file ("in the planning call") quotes it.

A request names a file by half its title's words, two of them side by side, or, for a short
title, a word no other file's title uses. A date or a version in the title does not count
("Planning call 2026-03-02" is named by "the planning call"), and a joined name is named by
its parts ("what did Lena say" names "LenaMeeting transcript").

Then the packet takes the best, at most three (two from one file), each within 85% of the
best, inside its own allowance (600, 900 or 1,400 tokens for a lookup, standard or deep
work); a part past the allowance is listed under "Also in your files", never left out. A copy marked `file_status: superseded` is not quoted. Sections arrive under "From
your files", quoted, with the file's version, status, date and project, and the line that
they are information, not instructions; `get_reference` reads the whole file. A section a
conversation already holds is not sent again. The file's card is not sent beside its own
sections. Without the embedding model, words decide instead: the share of the request's
idf-weighted words a section holds (0.65 alone, 0.35 when the request names the file or its
project; a guide 0.80).

`search_notes` finds file parts too (a looser bar: meaning 0.50), and lists them under "In
the brain's files".

## Tuning without code

| Symptom | Fix in the vault |
|---|---|
| a note is found for the wrong requests | sharpen its `title` and `summary`; add `requires_any` to its topic |
| a note is missed when people ask for it in their own words | put those words in its `summary` or its topic's line in topics.md |
| a multiword term matches the wrong notes word by word | `phrases` in `routing.json`: `{"statement of work": "sow"}` |
| a caveat must travel with a whole topic ("this is history") | `with_notes` on that topic in `routing.json` |
| a note belongs with every request of one kind | an intent with `include_notes` |
| a project needs certain notes whenever it is named | `pinned_notes` on its Focus, or file them in its project folder |
| a skill is not suggested, or is suggested wrongly | its `triggers` and `aliases`; `invocation: explicit` for run-by-name skills |
| a kind of request needs a fixed shape | an `intents` rule: `include_topics`, `exclude_topics`, `only_topics`, `include_notes`, `no_skill`, `set.task_type`, `set.scale`, `note_budget` |
| writing tasks miss a core style rule | add it to `house_style_notes`, in priority order |

Thresholds live in `routing.json` under `policy` (see `router.Policy`).

## Intent rules

```json
{
  "id": "outbound-note",
  "when_not": ["permission"],
  "match": {"any_phrases": ["connection request", "linkedin note"], "none_terms": ["..."]},
  "set": {"task_type": "combined", "scale": "micro"},
  "include_topics": ["brand/voice", "customers/icp"],
  "exclude_topics": ["operations/website"],
  "only_topics": ["brand/voice", "customers/icp", "customers/insights"],
  "include_notes": ["document-brand-system"],
  "no_skill": true,
  "note_budget": 1300
}
```

`match` accepts `any_phrases`, `any_terms`, `regex` (one must hit), `all_terms`, `all_of`
(word groups), `none_phrases`, `none_terms`, `none_regex`, and `max_terms`.

## Push: the brief before the model asks

A brief that waits for the model to ask is missed whenever it forgets, most often on a
follow-up. In Claude Code the prompt hook (`hooks/capture_prompt.py`) asks the router itself
for each message that asks for something, under the conversation's own session (`cc:` and
Claude Code's id; the session-start hook names it, so the model passes it on its own calls).
When the brief holds something the conversation was not given (a note, a part of a document,
a procedure, a must-hold the first time, the startup context when the file is stale), it comes
with the message; otherwise nothing is pushed and the hook only reminds the model to ask. The
model's own `get_task_context` with that session id then sends only what the push did not.
Pushed briefs are logged with `delivery: push`, so the report weighs push against pull.

`hooks.push` in brain.json: `words` (the default, about a second a message), `meaning` (the
router exactly as `get_task_context` runs it, a few seconds while the embedding model loads)
or `off`; `BRAIN_HOOK_PUSH=0` turns it off for a process.

The hook runs only where it is configured. Everywhere else the model has to ask, and the
Brain's MCP instructions say so, but an app may not show those to its model. So connecting an
app (`contxt connect`, or Settings, AI apps) also gives one standing instruction to paste into
that app's own instructions (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, Cursor's User Rules,
Claude Desktop's personal preferences): call `get_task_context` first with the message as
written, again with the `session_id` for every new ask, follow the must-holds and rules, and
propose lasting statements (`BRAIN_INSTRUCTION` in `workspace_connectors.providers`).

The task section of every brief opens with the project's objective when the request works in
one (its summary until it has an objective), then the request, then that the rules outrank it.

## The local retrieval engine (brain-logic plan 5.11)

When a verified local model service runs (a PC with an NVIDIA GPU or an Apple Silicon Mac, with
the pinned models), `engine.py` decides what goes into a brief:

1. **Gate**: a decision model (Kev) answers one yes/no question over the request and a short
   map of the Brain's areas: should this request get anything at all? No means one line (the
   must-holds whose domain is in play still go).
2. **Find**: every note and document part above a loose meaning floor (`engine.floor`), what
   the request names, the router's own picks and the house style for writing. No count cap; a
   ceiling (`engine.ceiling`, 300) only protects speed, and the ledger counts a request that
   hits it.
3. **Relevance cut**: a reranker (Qwen3-Reranker by default) scores every candidate against an
   instruction ("would this note help an AI do this task?"); what clears `cuts.relevance`
   survives. If nothing does, the brief is one line.
4. **Second pass**: on the survivors only, the decision model asks whether each adds anything a
   better one does not cover (out when it does not), whether it contradicts one (both then
   travel, and the brief says they disagree), whether it is current (flagged when not), and
   which must-hold domains the request touches (their must-holds attach, never detach).
5. **Link loop**: what the survivors name (notes in backticks, their files' parts) goes
   through 3 and 4; it stops when a round adds nothing above the cut, three rounds at most.
6. **Fit**: everything that survived, best first; what does not fit the budget becomes a
   pointer (a title and a line), never a drop.

Without a verified service, retrieval runs exactly as without the engine: the parity test
(`scripts/parity_briefs.py`, `tests/test_parity.py`) checks every eval request's brief byte for
byte. The fallback still writes down what exists: each candidate's keyword and meaning scores,
the outcome and its reason, marked fallback. `brain_health` and `brain models` say which mode
runs.

**Models and the lock.** `models.lock.json` pins each model: repository, revision, the checksum
of every file, dtype and runtime. The model service (`brain models serve`, started by the app)
binds to 127.0.0.1, verifies each model against the lock and loads it once for every process;
it refuses a model the lock does not list or whose files differ, and the engine refuses a
service whose lock differs from its own. Decisions go through System One (Jev's request format,
which Kev and Laya speak); relevance through a rerank interface, so models change without code
changes. `brain models pin <name> <folder>` records a downloaded copy's checksums.

**The audit trail.** For every brief the ledger keeps each candidate's keyword, meaning and
reranker scores, the decision model's answers with their probabilities, the outcome (whole, a
pointer, listed, already held, out) and its reason (below the cut, adds nothing beyond a named
note, disputed with one, past the ceiling, over budget), and in the brief's data the mode, the
lock's fingerprint, the gate's answer, the cuts and each layer's time. Activity's request view
shows "why this note" and "why not that one", read back, never recomputed.

**Choosing the setup.** `scripts/engine_compare.py` runs setups A (today) to E (Kev as the
relevance scorer) on the labeled requests, with requests that should get nothing, and the
must-hold decoys. The cuts are fitted on the tuning part of the labeled set and kept in
brain.json with the date and eval run; until then they are starting points.

**Machine setups and model settings (5.11.15, 5.11.16).** `machine.py` reads the computer (RAM,
an NVIDIA GPU and its memory, Apple Silicon or not) at first run and on request, and picks a
setup, each with a default model per role:

| Setup | Detected as | Meaning, reranker, decisions, agent | Ceiling |
| --- | --- | --- | --- |
| Laptop | 16 GB, no GPU with 12 GB or more | bge-small, Qwen3-Reranker-0.6B, Kev-0.8B, Qwen3.5-4B | 100 |
| Workstation | an NVIDIA GPU with 12 GB or more, or a Mac with 32 GB or more | bge-small, Qwen3-Reranker-0.6B, Kev-4B, Qwen3.5-9B | 300 |
| Large workstation | a GPU with 24 GB or more, or a Mac with 64 GB or more | bge-small, Qwen3-Reranker-0.6B, Kev-9B, Qwen3.6-35B-A3B | 300 |
| Small | under 16 GB | bge-small and MiniLM; no decision model or agent | 100 |

The person can make any pinned option the default for its role (Settings, On this computer,
Local models, or `brain models use <name>`); a choice the RAM check says will not fit is refused
with the reason (about 9.5 GB stays with the system; a GPU counts its memory less 1 GB plus
spare RAM), and one that measured slower than the machine's budget (5.11.7) is allowed with a
warning. The choices, what was measured here and which Kev steps qualified live in this
machine's settings (`<model home>/settings.json`), never in a Brain. The machine's ceiling
applies unless brain.json names one.

A decision model the lock marks with `extra.qualify` (Kev-0.8B) runs a Kev step only once it
qualified for it on this machine (`engine_compare.py --record`): until then the gate falls back
to the reranker's best score against the cut, the second pass (with its must-hold domain
question) is skipped, and the brief's audit, Activity and Settings name each fallback. Cuts
fitted for other models (`engine.fitted.models`) give way to the defaults, and a refit is
suggested.

## Measuring it

`brain bench` runs two things.

**Context usefulness** (`vault/eval.json`, the headline). Each case says, from the content of
the notes, which notes a good packet must deliver, which are useful, and which are noise. It
reports must-recall, "listed" recall (needed notes delivered or named under Also relevant),
precision and tokens, for tuning cases and held-out cases separately. Held-out cases are
written before any run and never tuned on; once inspected they retire into tuning and a fresh
set is written. On the 111-note organization brain the engine was developed against: tuning
45 cases must-recall 0.968, listed 1.000, precision 0.901, no noise; held out, first runs,
22 cases 0.840 / listed 0.920 / precision 0.900, no noise. The thresholds in `eval.json` are
regression floors, not targets; tuning noise must stay at zero.

**Behavior checks** (`vault/benchmark.json`). Cases pin the kind of packet: task type,
scale, mode, Focus, skill, token ceilings, no leaked personal Focus, no repeats in a session,
required and forbidden notes. They do not grade topics: a topic is where a note is filed, and
grading it one to one grades the filing, not the packet.

What still misses: requests phrased far from a note's words ("what should I avoid saying" for
a reviewer's red lines, "tag the links" for a UTM scheme, "sounding robotic" for writing
rules). Most such notes are at least listed under Also relevant, and the agent can find the
rest with `search_notes`: rephrased the way an assistant would ("UTM parameters for newsletter
links", "how to avoid AI-sounding writing"), a search put the missing note in the top 8 for
five of six misses in that brain, and first for four.

## Reranker (optional, off)

`router._rerank` can let a local cross-encoder reread the best `rerank_k` candidates and
reorder near-ties. Scores keep their values, so the best score and every threshold are
unchanged. It loads only a model already in `vault/.brain/models` and never downloads on its
own (`brain models --download --reranker` fetches it).

Measured 2026-09-28 with `Xenova/ms-marco-MiniLM-L-6-v2` (92 MB):

| | Tuning must-recall | Held-out must-recall (22) | Held-out precision | Median time |
|---|---|---|---|---|
| no reranker | 0.968 | 0.840 | 0.900 | 23 ms |
| reranker reorders the top 15 (weight 0.08) | 0.968 | 0.840 | 0.901 | 377 ms |
| reranker shifts scores instead | 0.935 | not run | | |

Reading notes one by one, it ranked needed notes higher (top-3 0.53 to 0.61), but in packets
it changed 3 of 22 held-out results and none of the misses, and shifting scores raised the
selection line and cut needed notes. So `rerank_weight` defaults to 0. Set it in
`routing.json` `policy` to try this or another model against the same evaluation.

## Embeddings

With `fastembed` installed the engine embeds every note, skill and topic once (cached by
content hash in `vault/.brain/embeddings.sqlite`) and each request once. They matter: without
them must-recall on that brain dropped from 0.968 to 0.887 on tuning cases and from 0.769
to 0.692 on one held-out set. A context call takes about 25 to 80 ms warm.
