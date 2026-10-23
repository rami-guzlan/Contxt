# Gnomon brain logic: development plan

Plan only: no code was changed. Written October 9, 2026 from a read of Contxt `main` at 61a5ab3
(after PR #4) and the research collected in `outputs/contxt/research/paper-notes.md`. Work starts
after the Work tab (branch `work-tab`, built October 9 and not yet merged) merges. Updated the
same day after Rami's review of the built Work tab: section 16 lists what that review changes in
the backend logic, and the screens are planned in `knowledge-work-ux-plan.md` beside this file
(the order of both plans together is in its section 6). The Work section is being renamed (see
that plan); this plan still says Work. File paths are relative to the Contxt repository. Gnomon
is the working name; the code says Contxt.

Updated October 10, 2026 (prompts 146 to 148, 152 and 153): section 5.11 adds the local retrieval engine
(decision 16, approved). A gate decides whether a request gets anything. Then come a wide meaning
search, a Qwen3-Reranker cut by relevance instead of by count, Kev's typed second pass and a link
loop. Every model's version is pinned, and every decision's score is kept in the ledger. Sections
4.2, 5.3, 5.4, 5.6, 5.9, 10, 11, 13, 14 and the appendix point to it.

Updated again the same day (prompts 157 to 160):
- 5.11 now covers machine setups, with a 16 GB laptop as the solo default (5.11.15), and a
  Settings page to download any pinned model and make it the default (5.11.16).
- Section 17 adds the knowledge agent run locally on Qwen3.5-4B (decision 17): a short core
  prompt, a code-run loop, typed tools that only suggest, and staying current through a change
  digest, an impact check and a memory of its suggestions, not training.

## 1. Summary

The goal is a brain whose logic is proven by measurement, so UI and UX work can go ahead with
confidence. Two outcomes:

1. Briefs that are accurate, relevant and make AI output better, shown on held-out tests and in
   blind with-and-without comparisons.
2. Context cost held at or below today's while quality rises. Rami's estimate today: about
   10,000 context tokens per 3 to 4 hours, 80,000 to 100,000 a working day, about $1 a day at
   Claude Fable 5.1 prices.

The plan treats the brain as five stages (ingestion, distillation, storage, retrieval,
updating) acting on five tiers (alignment, knowledge, state, episodes, briefs). Four tiers exist
in some form today. State is new: it generalizes the project journals into sheets.

| Workstream | What it fixes | Phase |
| --- | --- | --- |
| Measure | No true cost figure (re-reads and fixed overhead are invisible); no private eval on real requests | 0 |
| Retrieval and briefs | Bodies where a pointer would do; no authority labels; documents' sections indexed without their document's context; retrieval depends on the model remembering to ask | 1 |
| Retrieval engine (5.11) | Nothing judges whether a note helps the task; nothing decides to send nothing; a request with nothing to find still gets a packet of near matches; no record of why a note was in or out | 1 (built anywhere; models chosen on a PC, a Mac and a 16 GB laptop) |
| The knowledge agent, local (17) | Every judgment needs Claude Code or a small Ollama model that fails at structure; the agent cannot see what its suggestions would affect, or remember what was decided before | 1 (model and settings), 5 (loop, tools, impact, memory) |
| Kernel | About 1,350 tokens on every turn, two thirds of it contract, catalog and facts; rendered for one person into a shared file; two brains send two kernels | 1 |
| One statement model | Three vocabularies for what a statement is; no record of who said it; shelf life not tied to kind; audit text gone after 90 days | 2 |
| Ingestion and distillation | Every capture pays a capable model; a contradiction can be left out for serving no goal; AI outputs can come back as evidence for what they were built from | 3 |
| State tier | Fast-changing values (accounts, repos, standards) have no home that is structured, light to update and fast to retrieve | 4 |
| Updating loop | Corrections teach nothing; changes approved without seeing their effect on briefs; bent rules never counted; rubber-stamp approvals undetected | 5 |
| Proof | Results the UI work and the paper can stand on | 6 |
| Changes from the UX review (section 16) | State has no native editor; saved prompts are hidden in the app's database; assets live apart from the Library; files do not say where they came from; outputs are not tied to projects or accounts; workflows are not limited to context work | 2, 4, 5 |

Order: Phase 0 first; Phases 1 and 2 can run side by side; 3 and 4 need 2; 5 needs 4; 6 last.

## 2. The model: five tiers through five stages

### 2.1 The tiers

| Tier | What lives there | How fast it changes | Friction | How it reaches a brief | Human analog |
| --- | --- | --- | --- | --- | --- |
| Alignment | Identity, rules, conventions, preferences that shape every AI, must-holds, goals | Rarely, by amendment | A reason, the impact, a cooling-off delay | Kernel every session; must-holds whenever their domain is in play | Values, conscience |
| Knowledge | Durable facts, decisions, procedures (skills), filed documents | Months | Proposals under the preset | By relevance, under a budget | Semantic and procedural memory |
| State | Current values per entity: accounts, repos, standards, vendors, projects; open loops | Days to weeks | Logged and undoable; friction set per column | By key, when an entity is named or a working context is active | Long-term working memory (Ericsson & Kintsch 1995); a cockpit's speed bugs (Hutchins 1995) |
| Episodes | Raw inputs and records: talk, recordings, transcripts, files, exports, briefs, outputs | Constantly, append-only | None; kept as evidence | By search, quoted with source and date | Episodic memory |
| Briefs | The packet for one task | Per request | Built by code | Assembled | Working memory |

Promotion moves things up the table (a stable value becomes a fact), demotion moves them down (a
fact revised every week is really a value). Friction rises with the tier.

### 2.2 What each tier does at each stage (the target)

| | Ingestion | Distillation | Storage | Retrieval | Updating |
| --- | --- | --- | --- | --- | --- |
| Alignment | Only from the owner's own words or a promotion the owner approves; never from content | Flagged as candidates; always wait | Standing and must-hold notes, the goals note; amendments in git and the decisions journal | Kernel; must-holds by domain; authority labels in every brief | Amendments with reason, impact and delay; an exceptions ledger; a quarterly alignment review |
| Knowledge | Proposals from chats, captures, swept folders, Work uploads | Statements with kind, who said it, evidence, sources and dates; compared with the Brain (new, covered, replaces, contradicts) | Markdown notes in git; filed documents split into sections, indexed with their document's context | By relevance under a budget: bodies for the top few, pointers for the rest | Proposals by preset; shelf life; weekly cross-check; suspects from corrections; blast radius before approval |
| State | Sheet edits, `sheets_propose_update` over MCP, values found in captures, syncs | Values routed to cells instead of notes | Typed sheets; an append-only log per row; readable snapshots | By key; "changed since you last saw it" | Light writes; friction per column; age and source-linked staleness; promotion and demotion |
| Episodes | Everything raw | Digests; left-out lists kept and searchable | Originals outside git; the session ledger with retention by preset | By search, as quoted evidence | Append-only; deleted only by the owner; provenance chains for the circular-evidence check |
| Briefs | (none) | (none) | Kept in the ledger as episodes | Assembled by code: kernel delta, must-holds, state, notes, pointers, the skill | Measured per brief; rebuilt by the replay harness to test changes |

## 3. What the code already does

Build on these; do not build around them.

- **Admission before relevance.** Scope chain (company > dept > person, closest wins) and sealed
  partitions filter candidates before any scoring (`brainkit/scopes.py`; `brainkit/router.py`,
  header "ADMISSION is not relevance").
- **Deterministic, explainable routing.** Order: exact address, portfolio, questions about the
  brain, a named Focus, then standard scoring: BM25 plus local embeddings, meaning weighted 0.5
  (`router.py`, `Policy`: `semantic_floor` 0.34, `lean_floor` 0.46, `note_abs_floor` 0.42,
  `select_relative` 0.72, per-topic caps 5/4/5, `related_count` 8). Past-review notes are
  multiplied by `stale_factor` 0.75, disputed ones by 0.85, notes approved in 14 days get a lift
  (`router.py`, near line 1889). Follow-ups are read as edits or continuations.
- **Budgets are ceilings.** `packets.py`, `note_budget`: micro 900, standard 2,400, deep 3,400
  tokens; follow-ups 350; 600 reserved when a skill comes along; portfolio 1,200. Must-holds sit
  outside the budget and open every brief (near line 278). A note already delivered in the
  session is not sent again.
- **The kernel** carries identity, rules, core facts, the must-hold index and up to three
  critical one-liners, rendered into `CLAUDE.md` and `AGENTS.md`, fingerprinted so a stale copy
  gets the current one (`brainkit/kernel.py`; `system/system-kernel.md`).
- **Safeguards, measured on a demo Brain** (`outputs/contxt/build/safeguards-progress.md`):
  must-hold recall on requests that never name the rule went from 47% to 79% (words) and 83%
  (meaning) on held-out requests, decoys 2%; disagreement checks plus a model check
  (`baseline.py`, `tension.py`); dated values (`as_of`, `valid_until`) where the newest wins;
  challenges, disputed notes with their other view, and a weekly cross-check that found 6 of 8
  seeded wrong beliefs by itself and 8 of 8 with the owner's AI reading three pairs a week
  (`dissent.py`).
- **Capture.** A cue detector notices rules, corrections, decisions and procedures and nudges the
  agent to propose; it never writes (`brainkit/capture.py`; the prompt hook
  `brainkit/hooks/capture_prompt.py`). Captures (talk, recordings transcribed locally,
  transcripts, documents) get a digest whose key points are marked new, repeats, updates or
  clashes (`packages/core/.../services/captures.py`). Moving in reads any file, zips, and
  ChatGPT or Claude exports keeping only the person's own messages (`brainkit/movein.py`,
  `apps/server/.../movein_files.py`).
- **Distillation** ("Find what to remember", `packages/core/.../services/distill.py`): two tests
  (still true next month; serves a goal, an active project or how the person works), then each
  statement is compared with the Brain (new, covered, replaces, contradicts), with kind, evidence
  quote, sources, goal, project, `as_of` and rare must-holds; everything left out is listed with a
  reason (`MAX_ITEMS` 20, `MAX_LEFT_OUT` 50). Reconcile and merge are its siblings.
- **Governance.** Presets (personal, careful, regulated) set a capture matrix by type and origin
  (`brainkit/governance.py`, `PRESETS`, `CAPTURE_TYPES`); anything that shapes every AI
  (`SHAPING`: preference, rule, convention, change) never applies from a chat or a folder unless
  the owner allows that type; 12 proposals per session at most; a repeated proposal returns the
  waiting one; every decision is a git commit and an undo point.
- **Goals steer what gets pulled in, never what a request receives** (`brainkit/goals.py`: the
  goals note is loaded `manual`).
- **Projects** are a governed baseline plus an append-only journal with fixed fields (status,
  current, blockers, next, decisions) that needs no approval (`brainkit/focus.py`;
  `system/system-focus.md`).
- **The session ledger** keeps each brief's exact text and each kernel version for
  `sessions.retention_days` (90) and daily use counts for good (`brainkit/sessions.py`, lines 16
  to 18 and 645).
- **Token counts** come from tiktoken `o200k_base`, else characters / 4 (`brainkit/util.py`,
  lines 18 to 34). That is an OpenAI encoding: Claude's current tokenizer counts differently (the
  Opus 4.7 and later tokenizer, used by Fable 5.1, runs about 1 to 1.35 times older counts), so
  today's figures are estimates.
- **The knowledge agent** (`brainkit/agent.py`, `packages/core/.../services/agent.py`): code
  gathers candidates for seven upkeep actions, a model judges, the owner decides.
- **Evaluation tooling**: `brain bench` (`brainkit/bench.py`, `evaluate.py`: needed, useful and
  noise notes per request, held-out cases) and `brainkit/safeguards_eval.py`.

## 4. Token economics

### 4.1 Where context actually costs money

List prices (Claude API, October 2026): Fable 5.1 $10 per million input tokens, $50 output,
cache reads $0.25; Opus 5.5 $4 and $20 (reads $0.20); Sonnet 5.5 $2 and $10 (reads $0.20); Haiku
5.5 $0.10 and $0.50. Writing to the prompt cache costs about 1.25 times the input price for the
default 5-minute cache. Under a subscription the same tokens count against usage limits instead
of dollars; the shape of the cost is the same.

Brain content costs money in four places:

1. **Fixed overhead, every turn.** The kernel in `CLAUDE.md` and `AGENTS.md`, the MCP tool
   definitions and the server's instructions sit at the front of every request in every session.
   Cached, they cost $0.25 per million per turn on Fable; after an idle gap longer than the
   cache's life they are written again at about $12.50 per million. How much of the tool
   definitions loads depends on the client: Claude Code defers MCP tool schemas until used,
   other clients load them all.
2. **Briefs, delivered once and then re-read.** A brief is written to the cache once and then
   re-read on every later turn until the conversation is compacted. Illustration: a 1,500-token
   brief at turn 10 of a 200-turn session costs about $0.019 to write and about $0.071 in
   re-reads, roughly six times what "1,500 tokens delivered" suggests.
3. **Cache rewrites after pauses.** A session idle past the cache's life rewrites its whole
   prefix, brain content included.
4. **Background jobs.** Digests, distillation, checks and the knowledge agent make their own
   model calls. Illustration: a one-hour meeting transcript (about 13,000 tokens in, 1,000 out)
   costs about $0.18 to digest on Fable 5.1, $0.036 on Sonnet 5.5 and $0.002 on Haiku 5.5.

So delivered tokens are a floor, fixed overhead may matter as much as briefs, and the model a
background job uses matters more than anything in the brief. Phase 0 measures all four lines.

### 4.2 Levers, roughly in order of effect

1. **Measure the true cost first** (Phase 0): per session, fixed overhead, briefs, an estimate of
   re-reads, and background jobs; token counts calibrated against Anthropic's `count_tokens`
   endpoint on a sample, since the local tokenizer is an approximation.
2. **Route background jobs by difficulty.** Code first (free); Haiku 5.5 for triage and
   classification; the owner's chosen model for distillation and judgment; a local model only
   for a job it has passed a qualification set for. Measured on the eval, never assumed.
3. **Trim fixed overhead.** A kernel budget; tool descriptions cut to what a model needs to pick
   the tool; server instructions under about 100 tokens; fewer tools (see 5.7).
4. **Pointers before bodies.** Most notes arrive as title, one-line summary and their key
   sentence; full bodies only for the top few; the model opens the rest with `notes_get`, which
   the ledger counts. This is the progressive disclosure Agent Skills use.
5. **Budgets set by evidence.** Start from today's ceilings and lower each request type's budget
   only as far as needed-note recall holds on held-out requests.
6. **Deltas, never repeats.** Session dedupe exists; add "changed since you last saw it" for notes
   and state rows, and after a compaction resend only what the conversation still needs.
7. **Silence when nothing is new, or nothing fits.** A pure edit gets one line (exists); pushed
   briefs (5.6) go out only when the router finds something new and relevant; a request the gate
   finds nothing for gets one line instead of a packet of near matches (5.11). Since a brief is
   re-read about 74 times a session on the owner's live Brain, every packet not sent saves the most.
8. **No boilerplate.** Every line in a brief must carry information. A "noise tokens" metric
   catches regressions. (On October 9 the older brain-kit engine sent packets with eighteen
   identical placeholder entries, about 1,000 tokens that told the model nothing.)
9. **Skip known content before any model call.** Hash dedupe of captures, sections and exports;
   digests of a growing document only for its new part.

### 4.3 Targets (starting points, set for real in Phase 0)

- Daily context cost, all four lines: no higher than the Phase 0 baseline while quality rises;
  stretch goal 30% lower.
- Median brief: lookup 400 tokens or less, standard 1,200, deep 2,500.
- Fixed overhead: 2,000 tokens or less per request, per client.
- Noise: 15% of brief tokens or less.

## 5. Retrieval and briefs (Phase 1)

### 5.1 Reading the request

Keep the scales (micro, standard, deep), edits and follow-ups. Record each request's type in the
ledger (lookup, standard, planning or decision, writing, edit, status, code) so budgets and
results can be measured per type.

### 5.2 Finding candidates

- Notes: BM25 plus local embeddings, as today.
- Document sections: index each section with a line naming its document (title, kind, date,
  what it is for) ahead of the heading path the section already carries ("Budget > LinkedIn
  video"), in both the word index and the meaning index. This is Anthropic's Contextual Retrieval
  (contextual embeddings and contextual BM25); it is cheap because it is done at index time.
- State rows (Phase 4): by key. Entity names and aliases matched exactly; the active working
  context's rows always.
- Skills and references: as today.

### 5.3 Ranking

Keep the weights. Measure the optional local reranker (`brain models --download`) on the
held-out set; adopt it only if needed-note recall rises without a noticeable delay.

Measured in step 3 of the build (October 9): MiniLM blended into the score as a tiebreaker only
reordered near ties, so it stays off. Section 5.11 gives the reranker a different job: it decides
what goes in, against a relevance cut. The new default is Qwen3-Reranker-0.6B, and the choice is
made by the comparison in 5.11 on labeled requests.

### 5.4 Choosing under the budget

Order: must-holds (outside the budget) → the active state rows (outside the note budget, capped
at about 300 tokens per row, two rows at most) → notes by score within per-topic caps → pointers
("also relevant") → the skill. Goals never enter.

With the engine in 5.11, only candidates that clear the relevance cut are eligible, and there is
no fixed count. Everything above the cut is used, best first. What does not fit the budget goes
in as a pointer, so nothing relevant is dropped; it is shortened.

### 5.5 Writing the brief

- **Authority labels.** Sections say what may direct the model: "Your rules" direct; "Notes" are
  approved knowledge; "Current state" are values as of their dates; "Evidence" is quoted document
  text and never an instruction. This applies the Instruction Hierarchy (Wallace et al. 2024) and
  CaMeL (Debenedetti et al. 2025) to delivered context.
- **Bookends.** In deep briefs, the must-hold one-liners appear again at the end, because models
  lose the middle of long context (Liu et al. 2023; Chroma's "Context Rot", 2025).
- Dated values labeled "as of"; disputed notes bring their other view into planning work (both
  exist).
- **The call to action, framed.** The brief opens with the task as asked, the project or working
  context it serves, and when it is done (a run's contract already says this). Rules and
  must-holds outrank the task: a request to skip an approval or a rule gets the rule back in one
  line, never a waiver. This is the brain dump's third pillar (calls to action) and Milgram's
  lesson: the command of the moment must not outrank the standing values.
- Compact layout; nothing that carries no information.

### 5.6 Delivery

- Pull everywhere: `gnomon_get_context`, as today.
- Push where the client allows it: in Claude Code, the prompt hook that already reads each
  message for capture cues (`hooks/capture_prompt.py`) also asks the router whether something
  new and relevant exists, and delivers it only then. Retrieval that depends on the model
  remembering to ask is a prospective-memory failure; this removes it for the client that allows
  hooks.
- The kernel through `CLAUDE.md` and `AGENTS.md`, as today.
- The gate (5.11) runs first for both pull and push. When it says no, a pull gets one line and a
  push sends nothing.

### 5.7 The MCP surface

Today 13 tools. Keep a small core always described (`gnomon_get_context`, `notes_search`,
`notes_get`, `notes_propose`, plus `sheets_propose_update` from Phase 4); fold `skills_get` and
`files_open` into `notes_get` if Phase 0 shows the saving matters; generalize
`gnomon_get_context`'s `partition` argument into `context` (a working context, Phase 4) rather
than adding a tool to switch contexts.

### 5.8 Signals every brief leaves

Logged per brief, for tuning and the report card: opened afterwards (`notes_get` or
`notes_search` in the same request: something was missing), corrections that follow (Phase 5),
questions the brain could not answer (exists), and for sampled sessions, a model's offline
judgment of which delivered items the answer used.

### 5.9 Gates

- Needed-note recall at the default budget on held-out real requests: 90% or more.
- Noise: 15% of brief tokens or less.
- Must-hold recall (held out): 95% or more (79 to 83% today).
- Decoys: 2% or less.
- Pushed briefs that contained something used: 70% or more.
- Time to build a brief: measured in Phase 0, then held.
- From 5.11:
  - correct nothing: requests labeled "should get nothing" that get one line, 95% or more;
  - false nothing: requests that needed something but got nothing, 2% or less;
  - speed within the budgets in 5.11.7 on the reference PC and Mac;
  - every decision's scores present in the ledger, 100%.

### 5.10 The kernel

In plain words (decision 14, approved October 9, 2026): the kernel is the startup text every AI
session reads first (`CLAUDE.md` and `AGENTS.md`), on every turn. It is rebuilt three ways:

1. **Smaller and layered**: a one-line pointer to the brain; a constitution in three layers
   (company: who the organization is, the action policy, company-wide rules; role: a department,
   or an agent's definition; person: one's own preferences); a short index of the must-hold
   domains. Under 500 tokens, down from about 1,350. A test decides what stays: a line that costs
   nothing on real tasks when removed goes.
2. **Delivered by what each tool can do**: in Claude Code, `CLAUDE.md` shrinks to a few lines
   that pull in `AGENTS.md`, and the session-start hook adds the personal layer fresh each time;
   in Codex, Cursor and similar tools, `AGENTS.md` holds only the shared layers and the personal
   layer arrives with the first brief; in chat apps, the first brief carries everything, as
   today.
3. **A live Brain's core facts become must-holds**: a figure never to use, an audience rule
   and the rest go into every brief whose topic touches them, instead of into every session,
   coding sessions included.

Why: fewer tokens on every turn; nothing off-topic in front of the model; no stale or duplicated
kernels; and a structure that works for teams (personal layers never sit in a shared file,
company-wide changes get the most scrutiny, agents get kernels the same way people do).

The detail behind it:

Today (`brainkit/kernel.py`, rendered into `CLAUDE.md` and `AGENTS.md` at the repository root)
the owner's live Brain's kernel is about 1,350 tokens (a characters / 4 estimate: tiktoken is not
installed in the Contxt venv), read on every turn of every session:

| Section | Tokens | What happens to it |
| --- | --- | --- |
| Start, and Working with the brain | about 430 | One line stays; the rest already lives in the MCP server's instructions and the tool descriptions |
| Skills catalog (35 names) | about 200 | Leaves: the brief names the skill that fits; a team's catalog would run to hundreds |
| Core facts (7) | about 255 | Most become must-holds by domain: they must hold whenever marketing copy or prospecting comes up, not in a coding session |
| Identity (6) | about 215 | Stays, tightened: several bullets overlap, and the disclosure line appears twice |
| Rules and action policy | about 190 | Stays: this is the constitution |
| Banner, title, scope | about 70 | Shrinks |

Problems beyond size:

- It is rendered for one person (the owner's scope chain) into a shared repository file and
  rewritten after every governed change. In a team each member has a different chain, and a
  shared file that changes with anyone's approval means churn, merge conflicts and everyone's
  prompt caches invalidated.
- Every session gets the same kernel whatever the work is.
- The retrieval contract exists three times: in the kernel, the server's instructions and the
  tool descriptions.
- Two connected brains send two kernels. On October 9 a session in the brain-kit repository
  started with brain-kit's kernel as its project file (about 890 tokens) and received Contxt's
  live kernel in its first brief (about 1,350) because the fingerprints differed.

Kept: generation from governed notes, the fingerprint and resend of a stale kernel, scoping by
chain, the must-hold index with critical one-liners, and the render for models without tools.

Target: a kernel compiled for a principal (a person or an agent) from layers on its scope chain,
holding only what must shape every response and that a brief could not deliver in time.

- **Contract**: one line, with the fingerprint.
- **Constitution**: company (who we are in a line, the action policy, company-wide rules), role
  (a department, or an agent's own definition), person (preferences for every task). Each layer
  has a token budget shown in the app; starting points 150, 150 and 100.
- **Index**: the must-hold domains and the active working context, as pointers.
- About 400 to 500 tokens in all. An ablation run on the eval decides what stays: a line leaves
  when removing it costs nothing on held-out tasks.

Delivery by what the client can do:

- **Claude Code**: `CLAUDE.md` becomes a short stub that pulls in `AGENTS.md` through Claude
  Code's file import (`@AGENTS.md`) for the shared layers, and the session-start hook
  (`hooks/session_start.py`, which today prints a status line and warns when `CLAUDE.md` is
  stale) delivers the person's layer fresh. Personal changes never rewrite a shared file and
  never go stale.
- **Codex, Cursor and other tools that read `AGENTS.md`**: the file holds the shared layers,
  which change rarely; the person's layer comes with the first brief.
- **Chat apps** (the Claude app, ChatGPT): the first brief carries the kernel, as today.
- **Models without tools**: the critical must-holds in full, as today.

Team rules:

- Checked-in files carry only shared layers; a person's layer never enters a shared repository.
- A change to the company or role layer reaches every session of every member. It needs two
  approvals in the team edition, a notice, the cooling-off delay rules already have, and the
  blast-radius replay (section 9).
- Agents get kernels the same way. The Work tab stores agents as `agents/<name>/AGENT.md`; an
  agent is a principal with a chain (company > department > agent), so one compiler serves people
  and digital coworkers.
- One brain is primary in a workspace; any other connected brain contributes only its contract
  line and its must-hold index.

For the owner's live Brain now: move the core facts to must-holds by domain, keep the action policy and
the rules, and merge the overlapping identity bullets. That is about 400 tokens, and none of those
facts can be missed when their domain comes up, because must-holds bypass relevance.

Gates: 500 tokens or less per principal; no held-out regression in the ablation; one kernel per
session when two brains are connected.

### 5.11 The retrieval engine: local models, a relevance cut and an audit trail (decision 16)

Approved October 10, 2026 (prompts 146 to 148, 152 and 153).

#### 5.11.1 Why

- **It runs when nothing fits.** In development, `gnomon_get_context` brings unrelated content. On
  October 10, a question about an outside model returned 18 brain-kit modules, each with the same
  filler line. A goals-planning request the night before got product facts.
- **Nothing judges.** Meaning matching (bge-small) finds similar notes, but nothing asks whether
  a note helps the task. The only way to send nothing is for every score to fall below a
  similarity floor.
- **Nothing explains.** Nothing records why a note went in or stayed out.

The demo baseline finds 73% of needed notes on held-out requests, against a 90% gate.

#### 5.11.2 Machines and principles

- **Machines** (updated October 10, prompt 160): the solo Brain's default is a laptop with 16 GB
  of RAM, Apple Silicon or Windows. Dedicated PCs with an NVIDIA GPU, larger Macs and the team
  server unlock bigger models. Each machine runs one of the setups in 5.11.15, and every model can
  be downloaded and made the default in Settings (5.11.16). Without models the Brain still runs on
  code alone, and health says it is degraded.
- **100% local.** No API at any step. Hosted Jev is out for that reason.
- **Best results first, then cheapest, then fastest.** Local inference costs nothing per call.
  The money is in what Claude reads, so a tighter brief is the saving.
- **The same pinned model versions everywhere** (5.11.8).
- **Every decision's score in the ledger**, so an audit can explain any yes or no (5.11.9).
- **One local model service.** The app starts it, it binds to 127.0.0.1 and loads each model
  once, and it is shared by the engine, the app and every MCP session. MCP servers run one
  process per client, and loading a 4B model in each would be slow and wasteful. In the team
  edition the same service runs on a GPU server, behind a key.
- **One adapter per role.** Decisions use Jev's request format (Kev, Laya and hosted Jev all
  speak it), and relevance scores use a rerank interface, so models swap without code changes.

#### 5.11.3 The roles

| Role | Job | Filled by |
| --- | --- | --- |
| Gate | Before any search: should this request get anything from the Brain at all? | Kev, one yes/no question over the request and a short map of the Brain's areas. A second check after the reranker: if even the best candidate is below the cut, send nothing |
| Find | Cast a wide net for candidates | Code (scopes, sealed partitions, exact names and aliases, must-hold domains, keyword search) and the meaning index |
| Reranker | A model trained for one job: score how relevant a passage is to a request, reading both together. More accurate than the meaning index, which reads each alone, but too slow to run on the whole Brain | Qwen3-Reranker-0.6B |
| Judge | Decide which candidates go in | The reranker's score against the cut, then Kev's second-pass questions |
| Fit | Arrange what passed under the budget | Code (5.4) |

#### 5.11.4 The pipeline: a relevance cut, not a count

1. **Gate (Kev).** No means one line and nothing else.
2. **Find.** Every note and document section above a loose meaning floor, plus exact name
   matches and the must-holds of the domains in play. There is no count cap. A high ceiling
   (starting at 300) only protects speed, and the ledger counts any request that hits it.
3. **Relevance cut (Qwen3-Reranker).** Score every candidate with an instruction such as "Judge
   whether this note would help an AI do this task", and keep everything above the cut.
4. **Second pass (Kev, on the survivors only).** Typed questions a relevance score cannot
   answer:
   - Does this add anything the notes already chosen do not cover?
   - Does it contradict another survivor? If so, both travel as a disputed pair.
   - Is it current?
   - Which must-hold domains does the request touch?
5. **The link loop.** When survivors point to notes, document sections or State rows that were
   not candidates, fetch those and run steps 3 and 4 on them. Stop when a round adds nothing
   above the cut, with three rounds at most. Scoring the same notes again adds nothing, so a
   round only pays when it brings new candidates or asks a new question.
6. **Fit (code, 5.4).** Everything above the cut is used, best first. What does not fit the
   budget goes in as a pointer (title and a line, about 20 tokens) that the AI can open with
   `notes_get`. Nothing relevant is dropped; it is shortened.

Must-holds keep bypassing relevance (5.4). The gate and the cut never remove a must-hold whose
domain is in play.

#### 5.11.5 Models, pinned

Every model below is in the lock (5.11.8). The setup a machine runs (5.11.15) picks the defaults,
and the user can download the others and make any of them the default (5.11.16).

| Role | Solo default (16 GB laptop) | Options to download |
| --- | --- | --- |
| Meaning index | bge-small-en-v1.5 (today) | Qwen3-Embedding-0.6B, the same family as the reranker, multilingual; it becomes the default if it wins the comparison (5.11.11) |
| Reranker | Qwen3-Reranker-0.6B (Apache-2.0, multilingual, long inputs, takes an instruction) | ms-marco-MiniLM-L-6-v2 (in Contxt today), the fallback when the reranker misses the speed budget on a machine without a GPU |
| Decisions | Kev-0.8B, kev-1.0 (a LoRA adapter and pointer head on Qwen3.5-0.8B-Base; Apache-2.0 throughout; calibrated with one temperature) | Kev-4B (about 9 GB: GPUs with 12 GB or more, Macs with 32 GB or more); Kev-9B (about 17 GB: GPUs with 24 GB or more) |
| Knowledge agent (section 17) | Qwen3.5-4B, the post-trained model (one checkpoint that can think or answer directly; there is no separate instruct model), thinking off, 4-bit, text-only | Qwen3.5-9B; Qwen3.6-35B-A3B (mixture of experts, fast for its size); Qwen3.8-27B; or Claude Code, which uses the person's own plan and leaves the machine |

The knowledge agent's options are all Apache-2.0 (Qwen3.8's 2.4T Max model, which has its own
license, is not offered). Qwen3.6 and 3.8 have no official small sizes, so 4B and 9B come from
Qwen3.5. Only official builds, or community builds verified by checksum, enter the lock; remixes
never do.

Not used:
- **Laya**: its README calls it near chance until trained on your own data, and it ships
  over-confident.
- **Hosted Jev**: an API.

Runtimes:
- **CUDA**: PyTorch for Kev and the reranker; llama.cpp for the knowledge agent's quantized model.
- **Macs**: MLX for Kev and the knowledge agent. The reranker runs on PyTorch's MPS or an MLX
  conversion, whichever passes the speed bar.
- **Windows without a GPU**: PyTorch on the CPU for Kev and the reranker; llama.cpp for the agent.
  This is the slowest case. The agent works there as a background job, never while you wait.
- **Team server**: vLLM or the same runtimes, behind the service's key.

Re-read each model card when the pin is set; both projects behind Kev and Laya are weeks old.

#### 5.11.6 Kev's limits, and how the engine handles them

- **No count limit.**
  - A choice question takes up to 255 options.
  - A request takes any number of questions; its server batches them by tokens.
  - The small models are validated to 8,192 tokens of state.

  The engine batches by tokens, never by a fixed number of notes.
- **Each question reads the shared state and itself only.** The request can be the state, with
  one question per survivor, so it is read once per batch.
- **English only.** Teams working in other languages need a multilingual decision model,
  qualified the same way, before it is offered.
- **Weak at date arithmetic.** Dates come from State's computed columns (8.2), never from Kev.
- **Option order can change an answer.** Keep a fixed order. For close calls on choice questions,
  use Kev's permutation endpoint.

#### 5.11.7 Speed and cost budgets

These are starting targets, set for real by the first measurements on the reference machines.

| Step | PC with GPU (p50) | Apple Silicon Mac (p50) | 16 GB laptop, Apple Silicon (p50) | 16 GB laptop, Windows without a GPU (p50) |
| --- | --- | --- | --- | --- |
| Gate | 60 ms | 150 ms | 200 ms | 600 ms |
| Find | 100 ms | 100 ms | 150 ms | 200 ms |
| Relevance cut, all candidates | 300 ms | 800 ms | 1.2 s | 2 s with MiniLM, whichever reranker meets it |
| Second pass and loop | 150 ms | 400 ms | 500 ms | 1.5 s |
| Whole brief, p95 | 1 s | 2 s | 3 s | 5 s |

On a laptop the speed ceiling on candidates (5.11.4) starts lower (100) and is tuned by the
measurements.

RAM on the solo default (16 GB laptop), measured on first setup and shown in Settings:

| What is in RAM | About |
| --- | --- |
| The operating system, a browser and the Gnomon app | 6 to 8 GB |
| Qwen3.5-4B agent, 4-bit, text-only | 2.2 GB, plus its working memory |
| Qwen3-Reranker-0.6B | 1.2 GB |
| Kev-0.8B on its Qwen3.5 base | about 2 GB |
| bge-small | under 0.2 GB |
| Models in all | about 5 to 6 GB, leaving 2 to 4 GB free |

Kev-4B (about 9 GB, with no 4-bit build yet) does not fit beside the rest on a 16 GB laptop. It
is offered only where a GPU with 12 GB or more, or a Mac with 32 GB or more, has room for it.

Embeddings are computed at index time, as today, and the gate's map of the Brain's areas is
cached until the Brain changes. Per-call cost is zero; the saving shows in the four cost lines
(4.1), above all re-reads.

#### 5.11.8 Pinned versions

- **A lock file** (`models.lock.json` in the engine) records each model's repository, revision,
  file checksums, dtype and runtime version.
- **Downloads are verified** against the lock, and the service refuses a model it does not list.
- **Changing a pin is a governed change.** The replay harness (10.3) shows how the eval's briefs
  move before it lands.
- **Choosing among pinned models is the user's call** (5.11.16). "The same versions everywhere"
  means a model is always the same pinned version wherever it runs. Which models a machine uses
  can differ, and the ledger records which ran for every brief.
- **Team edition**: the server publishes its lock and the models each scope uses, chosen by that
  scope's admins (9), and clients refuse a mismatch.

#### 5.11.9 The audit trail

For every brief, the ledger keeps the following, under the audit retention setting (6):

- the lock fingerprint;
- the gate's answer and its probability;
- for every candidate: its keyword score, meaning score and reranker score, Kev's answers (each
  question with its probability), the cuts in force, and the outcome (body, pointer or out) with
  the reason (below the cut, adds nothing beyond a named note, contradicts a named note, over
  budget);
- the time each layer took.

Activity's request view shows "why this note" and "why not that one". Audits read the stored
scores and never recompute them, so small differences between GPUs never change an explanation.

#### 5.11.10 Setting the cuts

- **Who fits them.** The cuts (the gate's probability, the reranker's score, Kev's second-pass
  probabilities) are fitted on the tuning part of the labeled set (5.11.11). A model's confidence
  does not automatically match what is relevant in a given Brain.
- **Where they live.** Each Brain keeps its cuts in `brain.json`, with the date and the eval run
  they came from.
- **Defaults** come from the public demo set.
- **When to refit**: when a pin changes, or after the Brain grows a lot (the knowledge agent
  suggests it).

#### 5.11.11 Labeling, and the comparison that picks the setup

**Labeling builds the answer key.**
- The private set (decision 12) is about 80 real requests from the ledger. For each, every note
  is marked needed, useful or noise. The labeling panel on Activity's request rows and
  `brain eval sample|label|run` exist from step 2.
- Add about 20 requests that should get **nothing**: coding Contxt in a development repo, general
  questions, other people's work.
- The public demo set (37 requests) gains should-get-nothing cases, paraphrases and decoys.
- Split 70% for tuning (where the cuts are set) and 30% held out (looked at once, at the end).

**The setups**:

| | Setup |
| --- | --- |
| A | Today: keywords and bge-small |
| B | A plus Qwen3-Reranker with the relevance cut |
| C | B plus the Kev gate |
| D | C plus Kev's second pass and the link loop |
| E | Kev as the main relevance scorer instead of the reranker |

Each runs with bge-small and with Qwen3-Embedding-0.6B in the find step, because finding needed
notes starts there.

**Scored on**:
- needed-note recall at the budget;
- noise share;
- decoys;
- correct nothing, and false nothing;
- brief tokens;
- each layer's time at p50 and p95, on the reference PC, Mac and 16 GB laptops (Apple Silicon
  and Windows).

**The winner** is the fastest setup that clears every bar in 5.11.13. A tie goes to the setup
with fewer models. Because laptops run smaller models, the comparison is run per machine setup
(5.11.15), and each setup's defaults are its own winner.

#### 5.11.12 Kev beyond retrieval

Each use is qualified on its own labeled set under decision 7's rule (local models only after
they qualify):

- the request type (5.1; 89% by rules today);
- the must-hold domains in play;
- whether a push is worth sending (5.6);
- distillation's triage (7.2 step 2: durable or not, which tier, which entity), where Kev can
  replace Haiku 5.5 once it qualifies;
- whether two notes contradict or repeat each other (`tension.py`, the cross-check);
- the goals plan's typed checks.

#### 5.11.13 Gates

- Needed-note recall on held-out requests: 90% or more (5.9).
- Noise: 15% of brief tokens or less.
- Decoys: 2% or less.
- Correct nothing: 95% or more.
- False nothing: 2% or less.
- Speed within 5.11.7, for each machine setup.
- Brief tokens no higher than setup A's.
- Every decision's scores in the ledger: 100%.
- Every model matches the lock: 100%.
- On the solo default, models stay within about 6 GB of RAM, and the app never offers a default
  that the RAM check says will not fit.

#### 5.11.14 Building it

The pipeline is built with stand-in models in tests, on any machine:
- the model service and its adapters;
- the lock;
- the ledger fields;
- the "why" view;
- the labeling additions.

The comparison and the choice of defaults run on Rami's PC, a Mac and a 16 GB laptop, after the
private set is labeled. This belongs to Phase 1, in step 3 of the build or as a step 3b right
after it, together with the machine setups (5.11.15) and the model settings (5.11.16).

#### 5.11.15 Machine setups

At first run, and whenever the user asks, the app reads the machine (RAM, GPU and its memory,
Apple Silicon or not). It picks the setup that fits and runs a short speed check and a quality
check on the demo eval set.

| Setup | Detected as | Default models |
| --- | --- | --- |
| Laptop (the solo default) | 16 GB of RAM, Apple Silicon or Windows, no GPU with 12 GB or more | bge-small, Qwen3-Reranker-0.6B (MiniLM if it misses the speed budget without a GPU), Kev-0.8B, Qwen3.5-4B |
| Workstation | An NVIDIA GPU with 12 GB or more, or a Mac with 32 GB or more | The laptop's, plus Kev-4B and Qwen3.5-9B; Qwen3-Embedding-0.6B if it wins the comparison |
| Large workstation | A GPU with 24 GB or more, or a Mac with 64 GB or more | Kev-9B, and Qwen3.8-27B or Qwen3.6-35B-A3B for the agent |
| Team server (later) | A shared GPU server | Chosen per scope by its admins; the lock is published to every client |

Machines below 16 GB get code alone, plus bge-small and MiniLM, and the agent runs through Claude
Code if the person turns it on.

Kev-0.8B is the weakest of the decision models: 0.697 on new sources, against 0.838 for Kev-4B.
On a laptop, each Kev step (the gate, the second pass, the uses in 5.11.12) runs only if Kev-0.8B
passes that step's bars in the comparison. A step that fails falls back:
- the gate falls back to the reranker's best score against the cut;
- the second pass is skipped;
- Settings names each fallback.

#### 5.11.16 Model settings (Settings > On this computer > Local models)

- **What the page shows**:
  - the machine it found and the setup in use;
  - for each role (meaning, reranker, decisions, knowledge agent): the model in use, and every
    other pinned option with its size on disk, the RAM it needs, and its speed and quality on
    this machine once measured;
  - whether the engine is running in full or in fallback.
- **What the user can do**:
  - **download** an option (verified against the lock, then used offline);
  - **make it the default** for its role;
  - **remove** it;
  - **check this computer again**, which reruns the speed and quality checks and recommends.
- **Guard rails**:
  - a choice the RAM check says will not fit is refused, with the reason;
  - a choice slower than the budget gets a warning but is allowed;
  - changing the reranker or the decision model switches to that model's default cuts and
    suggests a refit on the Brain's labels (5.11.10).
- **Where choices live**: the app's settings on this machine; the ledger records which models
  ran.
- **Team edition**: admins set each scope's models; members see them read-only.
- **Claude Code for the knowledge agent** is an opt-in choice. It uses the person's own plan,
  and the agent's work then leaves the machine. Settings says so in one line.

## 6. One statement model (Phase 2: storage foundation)

No behavior changes in this phase; it gives every later phase one shape to work on.

- **One vocabulary for what a statement is**: identity, rule (with the subtypes convention and
  preference), fact, decision, procedure, value (State), project. It replaces three lists that
  disagree today: capture types (`governance.CAPTURE_TYPES`), distillation kinds (the
  instructions in `distill.py`) and note kinds (`governance.NOTE_KINDS`, `model.Note.kind`).
  Old notes keep reading correctly.
- **Who said it** on every statement (`said_by`): the owner, the owner's AI by inference,
  another person (in a meeting or an email), a document, a synced system, an agent run. With the
  approval, it sets the statement's authority. People misattribute sources (source monitoring,
  Johnson et al. 1993); a brain without this field does too.
- **Time**: `as_of` and `valid_until` (exist), plus when the Brain learned it (approval, git),
  when it was last confirmed, and `review_by`, derived from a shelf life by kind unless set:
  project 30 days, fact 180, decision 365 or until replaced, rule and identity 365, procedure
  180 or when used after a change. The owner can change any default.
- **Tier**, derived from kind and load: rules, identity, must-holds and goals are alignment;
  values are state; the rest is knowledge.
- **Audit retention**: brief text kept 90 days under the personal and careful presets, 730 days
  under regulated (decision 9), a setting in the app.
- **Origin** on every file and Library item: where it came from (a skill, a project, a capture
  source such as a recording or an export, a Library upload, a run's output). Brain > Files groups
  by it, and a brief can say where a quoted document came from (16.4).
- **The Library holds every item kept whole**: references, guides, influences, assets and saved
  prompts, each with a kind, an origin, versions, projects and a scope (16.2, 16.3).

Gates: every existing note reads without loss (`brain check` passes); briefs and `brain bench`
results are identical before and after.

## 7. Ingestion and distillation (Phase 3)

### 7.1 Ingestion

Paths stay: chats over MCP, the app, swept folders, Capture, Moving in, and Work uploads (new
with the Work tab). Changes:

- Record who said it at the door.
- An instruction found inside content is stored as "the document says ...", never as a rule,
  and its review card says where the rule came from. Memory injection works through exactly this
  gap (Greshake et al. 2023; Rehberger 2024).
- Hash dedupe against the Brain and earlier captures before any model call.
- **Evidence must be real.** When an AI proposes something with a quote it attributes to the
  person, the quote is checked against the requests the ledger logged in that session (and the
  raw message, where the Claude Code prompt hook saw it). A quote that is not there marks the
  statement as inferred, and it waits. A fabricated quote is the shortest path to a poisoned
  memory.

### 7.2 The distillation pipeline

1. **Pre-pass (code, free).** Split by structure (speakers, headings, slides), drop boilerplate,
   dedupe, find dates, figures and entity names (reuse the figure extraction in `tension.py`),
   and find sensitive spans with deterministic recognizers (emails, phone numbers, account and
   ID numbers; optionally a local named-entity model such as Microsoft Presidio's).
2. **Triage (cheap, per chunk).** Is it durable? Which tier: alignment candidate, knowledge, a
   state value, or episode only? Which project or entity? Haiku 5.5, or a local model that has
   passed the qualification set; structured output, validated.
3. **Privacy.** Label sensitivity and scope; redact spans only in what goes to a cloud model,
   by preset (decision 13).
4. **Distill (the owner's chosen model).** Today's instructions with three changes:
   - Contradictions are exempt from the goal test. Today the goal test runs before the
     comparison with the Brain, so a statement that serves no goal can be left out even when it
     contradicts something the Brain holds. That is schema distortion (Bartlett 1932), and the
     paper's own Lysenko and Challenger cases in miniature.
   - Every statement carries who said it.
   - Values go to State as cell updates (entity, column, value, as of) instead of notes.
5. **Reconcile (code).** Replaces and contradicts as today; the circular-evidence rule: an AI
   output built from a brief cannot count as evidence for the notes in that brief (the links come
   from `outputs_save` and the ledger); duplicates collapse.
6. **Output.** Knowledge proposals (governed), state updates (light), alignment candidates
   (always wait, labeled), and the left-out list, kept as a searchable episode record and
   re-scored when the goals change.

### 7.3 Cost controls

Only new material reaches a model; triage before distillation; one distillation call per
capture with its chunks batched; the existing caps (`MAX_ITEMS` 20, 12 proposals a session).

### 7.4 Gates

- Statement precision (the owner keeps it): 85% or more.
- Recall against a gold set (labeled transcripts and the interview sorting exercise): 80% or
  more.
- Seeded contradictions left out: none.
- Tier routing accuracy: 90% or more.
- Seeded circular promotions: none.
- Fabricated evidence quotes on a seeded test: all caught.
- Cost per hour of meeting: measured, and lower than Phase 0.

## 8. The State tier (Phase 4)

### 8.1 What it is

Structured, current values per entity that change faster than anyone can review: an account's
stakeholders and health, a repo's owners and gotchas, a standard's current version. Not
knowledge (it is not reviewed before it applies), and not documents (Work uploads are documents).
It is created and edited in Workspace as sheets, boards and calendars (16.1), and audited in the
Brain tab as State logs: every change, with who, when and why.

### 8.2 Data model

- **Sheet type**: a name, a key column, columns (name, type, friction class `free` / `confirm`
  / `locked`, age limit in days, linked source, sensitivity), a partition rule (for example one
  partition per account) and a scope.
- **Row**: one entity, with its key and aliases (so requests can name it exactly).
- **Cell event** (append-only): sheet, row, column, value, as of, written at, who said it,
  source, session or run, confidence. The current value is the latest valid event; the history
  is the events. Kimball's slowly changing dimensions name the same choice per column: overwrite,
  or keep history.
- **Files**: `vault/state/<sheet>/schema.json` and `vault/state/<sheet>/<row>.jsonl`, the same
  pattern as project journals, committed in batches, with a generated Markdown snapshot per sheet
  for people and git diffs (decision 3).
- **Templates by role**: Accounts, Repos or Services, Standards, Vendors, Contacts, a Project
  board, a Content calendar. Projects become a built-in sheet type that reads the existing
  journals.
- **Column types**: text, number, money, date, date range, status (a fixed list), person, link,
  and a reference to another sheet's row (an account's contacts, a repo's owner). Types make
  values checkable and make views possible.
- **Views, not copies**: a board groups rows by a status column, a calendar places rows by a date
  column, a grid shows everything; all three are one sheet. Dragging a card or moving an event is
  a cell write with its history, exactly like editing the grid.
- **Computed columns** (simple formulas, kept only if they prove helpful). One formula per
  column, applied to every row, written with column names and shown in plain words. Inputs: the
  row's other columns, today's date, a cell's age (days since it last changed, from the cell
  log), and linked rows (a count or sum over them, or one field looked up through a reference
  column). Functions: arithmetic, date differences and offsets, text join, comparisons, AND, OR
  and IF, and COUNT, SUM, AVERAGE, MIN and MAX over linked rows. A summary row per sheet gives
  counts, sums and averages per column and counts by status. The engine computes them at read
  time with a small safe evaluator (never a model, never arbitrary code); they are never written
  as cell events, AIs cannot edit them (they may propose a new formula column, which goes through
  governance like any schema change), and briefs carry their values marked as computed. Why they
  help context: date arithmetic and counting are where models slip, so "days until renewal: 23"
  in a brief is more reliable than a date the model must subtract, and a rollup ("4 open issues")
  says in a few tokens what listing every linked row would take hundreds to say. Left out:
  cell-by-cell formulas (`=B2*C3`), arrays, pivot tables, macros and scripts; they turn context
  into a calculation model and are hard for an AI to read.

### 8.3 Working contexts

A working context is what Rami called a state: a project, an account, an on-call week, Q4
planning, or "general". It holds the active rows, the partition, its projects, and a resumption
card (where you left off, the next step, open loops). Switching is explicit (the app's picker,
the `context` argument, or a request that names it), with suggestions when a request names an
entity; a context idle for 14 days asks whether to resume or close. Research behind it: attention
left behind on the last task (Leroy 2009), goals that fade without cues (Altmann & Trafton 2002),
recall that is best in the original context (Godden & Baddeley 1975).

### 8.4 Writing

- The owner in Workspace's editors (grid, board, calendar): applies, logged, undoable; the Brain
  tab shows the State logs.
- An AI through `sheets_propose_update` (a batch of cell updates with evidence): `free` applies, marked as
  AI-filled until a person touches it; `confirm` waits for one tap; `locked` is refused.
- Distillation: values found in captures (7.2).
- Syncs (later): mirrored columns follow their source.

### 8.5 Reading

When an entity is named or a context is active, the brief carries "Current state": the row's
values one line each with their dates, and what changed since this session last saw it, capped as
in 5.4. `sheets_get` (or `notes_search` with a sheet filter) answers questions across rows ("which
accounts renew this quarter?").

### 8.6 Staleness

Per-column age limits; source links (a commit touching a repo's linked paths flags its rows; a
changed mirrored field overwrites the cell); ages shown as colors in the editor.

### 8.7 Promotion and demotion

A value unchanged for months, or the same pattern across many rows, becomes a proposed note; a
note revised three or more times in 30 days is suggested for State. The owner confirms either
way.

### 8.8 Safety

Must-holds override any cell; partitions keep client rows apart; an AI-filled cell cannot support
a promotion until a person has touched it; the circular-evidence rule applies.

### 8.9 Gates

- Rows retrieved for named entities: 100%.
- State block size: 300 tokens or less per row.
- Seeded stale cells flagged: 100%.
- Cross-partition leaks on the seeded client test: none.
- Computed values match a reference calculation on a seeded test: 100%.
- With computed columns, answers to date and count questions about seeded rows are more accurate
  than without them. If they are not, and the interview sketches never reach for a computed
  column, formulas are left out.

## 9. The updating loop (Phase 5)

- **Learn from corrections.** When the owner corrects an AI's output (the capture cue for a
  correction, or "that's wrong" in the app), the notes in the brief before it become suspects; the
  most likely one (by overlap with the correction) gets a "Still true?" card.
- **Blast radius before approval.** For a baseline or a much-used note, the replay harness
  rebuilds the last 20 briefs that received it against the proposed change and shows what
  entered, left or moved, and the token difference. Baseline revisions already show which
  conversations used the note (`baseline.py`, `impact`); this shows the difference itself.
- **Exceptions ledger.** An approval that bends or overrides a rule is counted against it; at
  three in 90 days the owner is asked to change the rule or stop the exceptions. Vaughan's
  normalization of deviance (1996), as a check.
- **Quarterly alignment review**: goals, rules and must-holds still right? A knowledge agent
  action.
- **Approval health.** Median time to approve and the approval rate over 30 days; when approvals
  take seconds and nearly always pass, suggest moving more types to "applies with undo" and
  keeping fewer, weightier decisions (automation complacency, Parasuraman & Manzey 2010).
- **Shelf life** feeds the paced "Still true?" queue that exists today.
- **Salience from consequences.** A note involved in a correction or an incident is offered a
  stronger load (on demand to must-hold), the way people remember what once hurt them (emotional
  tagging of memories, McGaugh 2004). The owner confirms.
- **Checking outputs against must-holds.** Before a Work run finishes, and when an output is
  recorded, its text is checked against the must-holds of its domain: deterministic checks first
  (forbidden phrases and figures, formats, such as a figure never to use or an em dash), then a cheap model
  check for the rest. A violation sends a Work run back once, through the finishing gate that
  already exists, and flags a recorded output. This is the supervisor-model idea (Llama Guard,
  NeMo Guardrails) applied to the owner's own rules rather than general harm categories, and the
  mechanism behind section 10.2's "no must-hold violations". The one retry is also the cheap form
  of Best-of-N (15.8): a second answer is paid for only when the first breaks a rule.
- **Blind judging and a second voice.** Model checks (the baseline check, the cross-check,
  triage) see the two texts without who proposed them or which one is the owner's, so the judge
  cannot side with the owner (sycophancy, Sharma et al. 2023). The external challenger runs on a
  different model family when one is available.
- **Single-source beliefs.** Notes used in planning and decision briefs that rest on one source
  (only the owner's word, one document, one meeting) are flagged for corroboration in the
  cross-check. An echo chamber starts as a belief nobody checked twice.
- **Independent evidence only.** In multi-step and multi-agent Work, evidence is counted by
  independent primary sources: outputs from the same brief lineage count once, however many
  agents repeat them. In the team edition, decision outputs from multi-agent workflows include a
  dissent role by default (groupthink, Janis 1972).
- **Run transcripts are episodes.** A Work run keeps each tool call and result, linked from its
  run record, under the audit retention setting, so every step stays traceable and can be rolled
  back (Pillar 4).
- **Conflicting truths across departments** (team edition). When two departments' notes
  disagree, both are kept as a contested pair visible to both, and the company layer's owner
  decides; neither view silently wins (the pluralism problem, Gabriel 2020).
- **Verification with sources** (knowledge work). An upkeep action, and a workflow step: notes
  that are stale, rest on one source, are used most, or are picked by the owner are checked
  against the web, and each finding comes back as a challenge or a "Still true?" card with its
  citations. Nothing applies on its own; each run has a budget (notes per run, searches per
  note).
- **One stream per run.** Claude Code's event stream for a run is captured once: shown live in
  the run's review, then kept as its transcript (an episode). Secrets that match known patterns
  (tokens, keys, sign-in links) are masked before either.
- **Admins per scope** (team edition). An admin of a scope (a team, a department, the company)
  reviews and manages that scope's notes, State, Library, skills, agents and workflows, and
  approvals route to that scope's admins. In the solo Brain the owner is admin of every scope.
  Every item already carries a scope, so roles arrive without moving data.

Gates: seeded wrong beliefs found 8 of 8 or better within two cycles; correction suspects right
60% of the time or more; replay of 20 briefs in 10 seconds or less; seeded exception sequences
flagged at the third; every seeded deterministic must-hold violation in an output caught;
verdicts on seeded pairs unchanged when the proposer is hidden or swapped; on a seeded test,
verification findings arrive only as challenges or cards, each with its citations; seeded secrets
never appear in a stream or a transcript.

## 10. How we will know it works

Phase 0 builds this; every phase is gated by it.

### 10.1 Eval sets

- **Public** (invented demo Brains, in the repo): today's `eval.json` cases and safeguards sets,
  extended with state, push and budget cases.
- **Private** (the owner's live Brain; never in this repo): 60 to 100 real requests sampled from the
  live Brain's ledger, labeled by Rami as needed, useful or noise, split 70% tuning and 30% held out.
  About 20 requests that should get nothing join it (5.11.11).
- **From the interviews** (a software engineer and an enterprise architect): retrieval cases
  (exercise 17), distillation gold (exercise 12), approval calibration (exercise 20), turned into
  invented equivalents for the public set.

### 10.2 Metrics

| Area | Metrics |
| --- | --- |
| Retrieval | Needed-note recall at budget, noise share, must-hold recall, decoys, state rows found, push precision; correct nothing and false nothing; time per layer (5.11) |
| Tokens | Brief tokens by request type; fixed overhead per client; estimated re-reads; daily cost by line |
| Distillation | Precision, recall, contradictions kept, tier routing |
| Updating | Seeded beliefs found, stale cells flagged, correction suspects, time to caught up |
| Outputs | With versus without the brain on a fixed task set, judged blind by a model with Rami's spot checks; must-hold violations (target none) |

### 10.3 The replay harness

Rebuild the brief for any logged request against any brain state, current or proposed, and diff
the two. The evals, blast radius (section 9) and the paper's results all use it.

### 10.4 The report card

`brain report` (CLI) and later a page in the app: daily tokens by line, held-out recall, noise,
stale cells, approval health. That page is Settings > Test the Brain, specified in
`testing-lab-plan.md` 10.1 and C.5 (its decision 13). It also runs the tests and shows their
results. A separate chat builds it on branch `test-the-brain`, so the build chat does not build
this page in step 8.

### 10.5 The merge rule

No phase merges if held-out recall drops, noise rises, or cost rises, unless a measured quality
gain justifies the cost and Rami agrees.

### 10.6 Drift, time and the cost of alignment

- **Drift on long runs.** Once the Work tab runs multi-step jobs: seeded long tasks, scored at
  the end against their contract, with and without re-anchoring. The run contracts and hooks
  exist; drift has never been measured.
- **A four-week soak.** A demo Brain lives through four simulated weeks of captures, corrections
  and changed values: kernel stability, briefs drifting, stale values caught, exceptions flagged.
  This answers the papers' long-horizon question (alignment over weeks, not single turns) as far
  as a test can.
- **The alignment tax, reported.** Tokens and time spent on alignment (must-holds, rules,
  checks) against the whole, and output quality with and without them, so the paper can state
  what governance costs and what it buys.

## 11. Phases

| Phase | Builds | Size | Done when |
| --- | --- | --- | --- |
| 0. Measure | Token ledger (four lines, calibrated with `count_tokens`); private and public eval sets; replay harness; baseline report | M | Every metric in 10.2 has a baseline |
| 1. Retrieval and briefs | Pointers before bodies; authority labels; bookends; sections with their document's context; reranker test; push through the prompt hook; MCP surface trim; per-type budgets; kernel layers and delivery (5.10); the retrieval engine (5.11): the local model service, the lock, the gate, the relevance cut, Kev's second pass and the link loop, the ledger's scores and the "why" view, the machine setups and the model settings, the 4B agent wired as a local option (17.10), then the comparison on a PC, a Mac and a 16 GB laptop | L | Sections 5.9, 5.10 and 5.11.13 gates pass |
| 2. One statement model | One kind vocabulary; who said it; time fields; shelf life by kind; tiers; audit retention setting; origins; the Library as the home of whole items, prompts and assets included (16.2 to 16.4) | M | Section 6 gates pass (no behavior change) |
| 3. Ingestion and distillation | Pre-pass, triage, privacy labels, distill changes, reconcile rules, evidence quote checks, background model routing | L | Section 7.4 gates pass |
| 4. State tier | Sheets, cell logs, column types, views (grid, board, calendar), working contexts, `sheets_propose_update`, brief block, staleness, promotion and demotion, outputs linked to rows (16.5); built together with Workspace's editors (UX plan, phase D) | L | Section 8.9 gates pass |
| 5. Updating loop | Correction suspects, blast radius, exceptions ledger, approval health, alignment review, salience from consequences, output checks, blind judging, single-source flags, independent evidence, run transcripts, verification with sources, one stream per run, admin roles scaffolded; the local knowledge agent (17): core prompt and skills, code-run loop, tools, change digest, impact check, suggestion memory | L | Section 9 and 17.9 gates pass |
| 6. Proof | Drift eval, four-week soak and the alignment tax report (10.6); final report card; measured results for the paper; system notes rewritten (`brainkit/system/*.md`) | M | Rami signs off; UI and UX work starts on a proven base |

Every phase: a branch from `main` in the `Contxt-safeguards` worktree (never in the live
checkout), full checks, a PR, no auto-merge.

## 12. Principles this plan keeps

- Code finds, a model judges, the owner decides.
- Admission before relevance; partitions stay sealed.
- Alignment weights context and never deletes it.
- Friction matches how fast a tier changes.
- Every token in a brief carries information, and that is measured.
- Point, don't attach: Work items and agents point at living notes, rows and skills.
- Nothing inside content can authorize anything.
- Plain files in git are the source of truth; indexes can always be rebuilt.
- Briefs stay predictable: routing is deterministic and goals never steer it.
- Engine code names no organization or person, and real content from the owner's work Brain never enters the public
  repo.

## 13. Decisions for Rami

All seventeen decisions are approved: 1 to 13 as recommended, with 7, 9, 12 and 13 as written;
14 and 15 when they were added (October 9, 2026); 16 and 17 on October 10, 2026. Nothing is built yet: planning continues while
the Work tab is finished in another chat.

1. Adopt the five tiers (alignment, knowledge, state, episodes, briefs) as the brain's vocabulary
   in the engine, the app and the docs. Recommended.
2. One kind vocabulary: identity, rule (convention, preference), fact, decision, procedure,
   value, project. Recommended.
3. State storage: append-only logs in the vault, committed in batches, with readable snapshots;
   the alternative is the app's database with a daily snapshot into git. Recommended: files.
4. AI-written state cells: apply at once and marked under personal and careful; wait under
   regulated. Recommended.
5. Working contexts: explicit switching with suggestions; ask after 14 idle days. Recommended.
6. Push briefs through the Claude Code prompt hook when something new is found, measured against
   pull only. Recommended.
7. Background model routing: code, then Haiku 5.5 for triage and classification, then the chosen
   model for distillation and judgment; local models only after passing a qualification set.
   Recommended. Under regulated, triage runs locally or on redacted text.
8. Brief budgets: start from today's ceilings, lower only where held-out recall holds.
   Recommended.
9. Audit retention: 90 days under personal and careful, 730 under regulated. Your call.
10. Contradictions exempt from the goal test. Recommended.
11. The circular-evidence rule. Recommended.
12. A private eval set from the live Brain: you label about 80 real requests (about two hours). Recommended:
    without it, tuning runs on invented data only.
13. Redaction for cloud calls: on under careful and regulated, off under personal unless turned
    on. Your call.
14. The kernel (section 5.10): layers compiled per principal (company, role, person or agent),
    500 tokens at most, delivered by what each client can do (a stub plus the session-start hook
    in Claude Code, the shared layers in `AGENTS.md`, the first brief in chat apps); the live
    Brain's core facts move to must-holds by domain. Approved October 9, 2026.
15. The additions from the traceability review (section 15): the call to action framed under the
    rules, evidence quote checks, output checks against must-holds, blind judging, single-source
    flags, independent evidence, salience from consequences, run transcripts as episodes,
    conflicting truths kept visible across departments, the drift eval, the four-week soak and the
    alignment tax report. Approved October 9, 2026.
16. The retrieval engine (section 5.11), approved October 10, 2026:
    - 100% local, on dedicated PCs with a GPU or Apple Silicon Macs;
    - a Kev gate before any search;
    - a wide find with no count cap;
    - a relevance cut by Qwen3-Reranker-0.6B, the default reranker (MiniLM is the fallback);
    - Kev's typed second pass and a link loop;
    - over-budget notes as pointers, never drops;
    - the same pinned model versions everywhere, from a lock file;
    - every decision's score in the ledger, so an audit can explain any yes or no;
    - the setup chosen by a comparison on labeled requests that include should-get-nothing
      cases;
    - amended the same day: a 16 GB laptop is the solo default (5.11.15), and any pinned model
      can be downloaded and made the default in Settings (5.11.16).
17. The knowledge agent, run locally (section 17), approved October 10, 2026:
    - Qwen3.5-4B by default (thinking off, 4-bit, text-only), with 9B, 35B-A3B, 27B or Claude
      Code as choices in Settings;
    - a short core prompt with skills on demand;
    - a code-run loop of at most six steps with a hand-up ladder;
    - typed tools that only suggest, including drafts in the app for the person;
    - Kev for typed checks;
    - staying current through the change digest, the impact check and its memory of past
      suggestions;
    - no fine-tuning or self-training: what it learns lives in the Brain.

## 14. Risks

- **Tuning to one Brain.** Held-out splits plus the public demo sets.
- **Pushed briefs spending tokens.** Push precision is gated; silence when nothing is new.
- **State becoming a second, divergent truth.** Precedence (state wins for current values, the
  brain for rules and precedent, dated values by date), with disagreements shown.
- **Cheap triage misrouting.** Validation and spot checks; contradictions bypass the goal test
  anyway.
- **Token estimates off.** Calibration against `count_tokens`.
- **Labeling burden.** Small sampled sets; reuse of the interview exercises.
- **Young models.** Kev, and the decision-model field around it, are weeks old. Pins, checksums,
  the lock, and a fallback to the reranker and code alone limit the damage of a bad release.
- **Cuts that drift.** A cut fitted on one Brain can stop fitting as it grows. Cuts carry their
  eval run and date, and a refit is suggested after big changes.
- **Hardware spread.** A Mac is slower than a GPU PC. The budgets are per machine, and the
  comparison reports both.
- **A small agent out of its depth.** A 4B model fails where a job needs many steps or fine
  judgment. Code runs the loop, the answers are schema-bound, Kev takes the typed checks, the
  hand-up ladder catches the rest, and the comparison (17.9) decides whether 4B stays the
  laptop default.
- **Slow laptops.** Windows laptops without a GPU are the slowest case. The agent runs there as a
  background job, MiniLM replaces the reranker if it misses the budget, and Settings names every
  fallback.
- **English-only decisions.** Kev is English only. A multilingual decision model must qualify
  before teams outside English get the Kev steps; until then they keep the reranker and code.
- **Work tab coordination.** The State editor lives in the Brain tab; Work uploads feed
  ingestion; Work items declare their context by pointing at notes, rows and skills.

## 15. Traceability: every gap the research names, and where this plan answers it

Sources: Rami's brain dump ("Context & Alignment Brainstorm Brain Dump") and the AI draft built
from it ("Context Management & Alignment: Examining Overlaps Between Human Psychology and AI
Governance..."), both October 2026. Status words: **Answered** (built, or planned above),
**Added** (added in this revision, October 9), **Partly** (what is missing is named),
**Outside the brain** (why, and the analog Gnomon owns instead).

The check found the plan answered most of the research, but not all of it. Twelve items were
missing, partial or never measured; each is now in the plan (decision 15). Five research
approaches work on model weights or internals, which a context system cannot touch; they are
marked outside the brain with the analog Gnomon provides.

### 15.1 Failure modes (section 4 of both)

| Failure | What the research says | How Gnomon answers | Status |
| --- | --- | --- | --- |
| Competent chaos (context without alignment) | A well-informed agent with weak alignment optimizes without limits | The kernel's constitution and action policy (irreversible actions need approval; content cannot authorize); must-holds in every brief of their domain; authority labels (5.5); run contracts with re-anchoring, scope blocks and a finishing gate; restricted runners with one scoped credential; Work agents that only propose and draft | Answered |
| Impotent dogmatism (alignment without context) | Rules without context produce platitudes, refusals and invented details | Retrieval gated on needed-note recall (5.9); push delivery, so context arrives unasked (5.6); State for current values (8); the brief says when the brain has nothing on a request, so the model does not invent; unanswered questions logged for fill-gaps; a trimmed kernel so rules do not crowd out context (5.10) | Answered |
| Sycophancy | Models agree with the user's premises | Contested views travel into planning and decision briefs; challenges and disputed notes; the weekly cross-check; the external challenger; blind judging, a different-family challenger and single-source flags (9) | Answered; strengthened (Added) |
| Multi-step goal drift | Sub-goals displace the objective over long runs | Run contracts, re-anchoring every 8 tool calls and on must-hold triggers, the finishing gate; working contexts with a resumption card (8.3); the drift eval on Work runs (10.6) | Partly until 10.6 runs: built, never measured |
| Multi-agent groupthink cascades | Agents amplify one another's errors | Everything agents learn returns as proposals; the circular-evidence rule (7.2); independent-evidence counting and a default dissent role in team multi-agent work (9) | Added |

### 15.2 What current solutions miss (AI draft, section 5)

| Gap | Note on the claim | How Gnomon answers | Status |
| --- | --- | --- | --- |
| Salience: similarity ranks a safety rule like trivia | Overstated as written: Generative Agents rank by importance and Letta pins core memory. The real gap is importance rated by a model and governed by no one | Governed salience: loads (standing, must-hold by domain, on demand, manual), baselines and authority labels; must-holds go into every brief of their domain whatever their score (recall 47% before, 79 to 83% held out, target 95%); salience raised by consequences (9) | Answered and measured; target raised; Added |
| Memory poisoning, canonized reflections | Real (AgentPoison, PoisonedRAG, persistent memory injection in ChatGPT) | Nothing durable applies without governance; capture guards (contradictions, near repeats); the circular-evidence rule; content cannot instruct (7.1); the cross-check and seeded-belief tests; evidence quotes checked against the session (7.1) | Answered; strengthened (Added) |
| Alignment decoupled from storage | Memory treated as neutral storage with alignment bolted on | Alignment organizes admission (scopes and partitions before any score), storage (tiers, loads, baselines), delivery (must-holds first, authority labels) and change (friction by tier). Deliberately not relevance: goals never filter what a request receives, because filtering context through current values is the Lysenko failure | Answered; the paper should state this boundary |

### 15.3 Current approaches (AI draft, section 5)

| Approach | What Gnomon takes, or why not |
| --- | --- |
| Contextual Retrieval (Anthropic) | Taken: sections indexed with their document's context, in words and meaning (5.2) |
| Prompt caching | Taken as economics: a stable kernel so caches hold; the cost model (4) |
| Constitutional AI and RLAIF | Outside the brain: it trains weights. The analog Gnomon owns: an explicit, versioned constitution at inference time, amended under friction (5.10, 9) |
| Sparse autoencoders, representation engineering, InferenceGuard | Outside the brain: they need the model's internals, which closed models do not expose. The analog: every brief's exact text is kept in the ledger, so what a model was given is always inspectable |
| MemGPT and Letta paging | Taken, governed: the brief is the working set; notes, state and episodes are storage; `notes_get` and `notes_search` page on demand. Unlike Letta, an agent cannot rewrite its own core memory without governance |
| CoALA | Taken and extended: briefs (working), episodes (episodic), knowledge (semantic and procedural), plus two tiers CoALA lacks: alignment (a governed constitution) and state (fast, structured values) |
| Generative Agents | Taken: recency (the 14-day lift), importance (governed loads instead of a model's rating), relevance (words and meaning); reflection only through governance; plans as projects and working contexts |
| Supervisor guardrails (Llama Guard, NeMo Guardrails) | Added in a narrow form: outputs checked against the owner's must-holds (9). General harm moderation stays with the model vendor |
| Reflexion (self-critique) | Partly: run re-anchoring and the finishing gate; the output check gives the critique an explicit rubric (9) |
| Best-of-N re-ranking | Not taken as a default: several answers are written and the best kept, so output cost rises about N times; the brain's job is the input. Its cheap form is in section 9 (one retry when a draft breaks a rule); the full form could be an option for high-stakes Work runs later. Explained in 15.8 |
| Sandboxing and least privilege | Answered: restricted runners, scoped credentials, the shell guard hook (`hooks/guard.py`), agents that only propose and draft |

### 15.4 Tensions (section 6 of both)

| Tension | How Gnomon answers | Status |
| --- | --- | --- |
| Alignment-malleability paradox | Tiers with friction matched to how fast each changes (2.1); amendments with reasons and a cooling-off delay; the exceptions ledger and the quarterly review keep rules from fossilizing; content can never amend them | Answered |
| Alignment tax and latency | Deterministic checks first; capped model checks; budgets and cost gates (4, 10.5); the kernel diet (5.10); the alignment tax reported (10.6) | Answered; measured (Added) |
| Memory poisoning and synthetic sycophancy | See 15.1 and 15.2 | Answered; strengthened |
| Multi-agent cascades and goal drift | See 15.1 | Partly, closing with 10.6 |
| Cognitive atrophy and algorithmic obedience | Durable changes wait for a person under the right preset; approval cards carry evidence and reasons; approval health catches rubber stamps (9); the Workspace is a place to think before AI writes; outputs arrive as drafts | Answered inside the brain; what people do with outputs in other tools is beyond it |
| Underestimating the use cases | An adoption question, not architecture: the interviews and the Work tab's path from doing to delegating | Outside the brain |

### 15.5 The four pillars (the brain dump's guardrails; the AI draft's recommendations)

| Pillar | Where it lives |
| --- | --- |
| 1. Fixed orientation with invariant anchoring | The kernel's constitution layers (5.10); must-holds outside the budget; authority labels and the call to action framed under the rules (5.5); content cannot authorize |
| 2. Strategic operational friction | Presets and the capture matrix; friction per State column (8); baselines; the action policy; approval health (9) |
| 3. Multi-layered epistemic validation | Contradiction checks, the weekly cross-check, the external challenger, dated values, shelf life, seeded-belief tests; evidence quote checks, single-source flags, blind judging (Added) |
| 4. Immutable, versioned lineage | Git, the decisions journal, undo points, the ledger's briefs, run records; run transcripts as episodes, the audit retention setting (6) and the replay harness (10.3) (Added) |

### 15.6 The human cases (sections 1 to 3)

| Case | The lesson | The mechanism |
| --- | --- | --- |
| Working memory (Baddeley; Miller; Cowan) and cognitive load (Sweller) | Capacity is small; overload narrows attention | Budgets as ceilings, per-topic caps, pointers before bodies, the noise metric, bookends (5) |
| Milgram | The command of the moment can override standing values | Rules outrank the task in every brief; a request to skip an approval gets the rule back; content cannot authorize (5.5, 7.1) |
| Janis, groupthink | Cohesion silences dissent | Dissent kept visible; independent evidence; a dissent role in team multi-agent work (9) |
| Vaughan, normalization of deviance | Exceptions become the norm | The exceptions ledger (9) |
| Lysenko | Ideology filters out disconfirming data | Contradictions exempt from the goal test; left-out lists kept and re-scored; goals never filter retrieval (7.2, 15.2) |
| Apollo and the scientific method | Context listened to, alignment anchored in reality | Learning from corrections, dated values, staleness tied to sources, the quarterly alignment review (8, 9) |
| Simon, bounded rationality | Good-enough choices under limits | Deliver nothing below the bar; budgets as ceilings (3, 5) |
| Childhood alignment as a living constitution with append-only history | Values change only by deliberate amendment | The kernel's constitution in git, amended under friction, history kept (5.10, 9) |

### 15.7 The stated uncertainties (AI draft, section 7)

| Uncertainty | What Gnomon can and cannot do |
| --- | --- |
| Whose values (Gabriel 2020) | Cannot settle it; makes it explicit: scopes say whose rule applies, the closest wins, and conflicts across departments stay visible and go to the company layer's owner (9) |
| Mechanistic opacity | Cannot see inside the model; makes its inputs fully inspectable (every brief kept) |
| Long-horizon generalization | Cannot guarantee it; measures it: the drift eval and the four-week soak (10.6), the weekly cross-check, exceptions and staleness |

### 15.8 Best-of-N, explained

The model writes several answers to the same request (say four), and a scorer keeps the best.
The scorer can be a rule check, a test suite, a scoring model or another AI. Research uses it to
get safer, better answers without retraining a model; coding tools use it as "write several
fixes, keep the one that passes the tests". The AI draft lists it among the inference-time
methods for closed models.

- **Benefit**: better and safer answers on average.
- **Cost**: about N times the output, plus the scoring, and slower. On Fable 5.1 ($50 per million
  output tokens) a 2,000-token answer costs about $0.10, so best of four costs $0.40 or more.
- **Why it is not part of the brain**: Gnomon controls what a model is given, not how many times
  it writes. Best-of-N multiplies the bill on the output side, against the targets in section 4.
- **The cheap form, already in the plan**: a Work draft that fails its must-hold check gets one
  more try through the finishing gate (section 9), so a second answer is paid for only when the
  first breaks a rule.
- **Where the full form could fit later**: an opt-in for high-stakes Work runs (a client
  proposal, an RFP response), scored against the brief's must-holds and the run contract's
  checks. The proposal-deck-builder skill already works this way: several versions, then design
  and fact checks.

## 16. What the UX review changes in the backend (October 9, 2026)

Rami reviewed the built Work tab (branch `work-tab`) and set the direction: Gnomon is about
context and alignment, not another place to run AI tools. The screens are planned in
`knowledge-work-ux-plan.md`; these are the backend consequences. None of them changes the tier
model, the token targets or the gates. State gains column types and views, the Library gains
kinds and origins, and two mechanisms join the updating loop.

### 16.1 State is edited in Workspace

Sheets, boards and calendars are created and edited in Workspace as the State tier (section 8):
medium-term context that AIs read and update through `sheets_get` and `sheets_propose_update`. Boards and
calendars are views of a sheet, never separate stores (8.2). This replaces the Work tab plan's
decision to link outside sheets and calendars rather than build them; links to outside sheets stay
possible. The Brain tab keeps the audit view, the State logs. Columns can be computed by simple
formulas, kept only if they prove helpful (8.2).

### 16.2 Prompts move into the Brain

Saved prompts were private rows in the app's database (`context_items` of kind `prompt`), hidden
from search unless a run pinned them. They become Library items in the Brain's vault, in the
person's own scope:

- saved verbatim, with any files that came with them, versioned and linked to projects;
- found by name or by search by any connected AI, and never routed into a brief unless a request
  names one (their load is `manual`);
- saved from a chat ("save this prompt to my Brain") through the Library's saving tool: `files_upload`
  gains a kind and inline text, rather than a new tool (5.7);
- the existing saved prompts migrate once, keeping their versions;
- a prompt used often enough suggests a skill (exists).

### 16.3 One Library for whole items

References, guides, influences, assets and prompts share one store, one id and one item page.
Brain > Files becomes a view of the same items grouped by origin, and opening any file there
opens its Library page.

### 16.4 Origin on every file

Every asset and reference says where it came from: a skill, a project, a capture source (a
recording, a transcript, an upload, an export), a Library upload, or a run's output (section 6).
Files filed before origins existed read "origin unknown" until the owner sets one.

### 16.5 Outputs link to context

`outputs_save` also records the project, the State row it is for (an account, a repo), who made
it (a person or an agent) and when, beside the brief it was made from (exists). Outputs group by
project by default, and by entity type wherever the Brain has a State sheet for it (one bucket
per account).

### 16.6 Workflows are context work

Step types: Brain upkeep (the knowledge agent's actions), ingestion (refresh a Library item, fetch
a URL or a repository, sweep a folder), distillation (a digest, "find what to remember"), State
updates, verification with sources (section 9), human checks and outputs. Connector pulls stay a
scaffold until they are tested against real connectors. Each step type declares what it takes and
what it gives, so the canvas can check that two steps fit together.

### 16.7 Skills by purpose

The built-in Brain skills and the knowledge agent's actions (context management) are told apart
from work skills, so they can be run quickly from one place. Every run opens to a review that
streams its steps (one stream per run, section 9).

### 16.8 Roles, scaffolded

Admins per scope (section 9). The solo app shows "Yours" on every item and hides the rest.

## 17. The knowledge agent, run locally (decision 17)

Approved October 10, 2026 (prompts 157 to 160). Today the knowledge agent
(`brainkit/agent.py`, `services/agent.py`) gathers candidates in code and asks Claude Code, or an
Ollama model, to judge them. This section makes a local Qwen model the default and gives it a
design a 4B model can carry. It can manage the whole Brain and use the Gnomon app for the person
when asked, and everything it does stays a suggestion.

### 17.1 Models

- **The solo default is Qwen3.5-4B** (5.11.5): the post-trained model with thinking off, 4-bit,
  text-only, about 2.2 GB of RAM.
- **The options in Settings** (5.11.16): Qwen3.5-9B, Qwen3.6-35B-A3B, Qwen3.8-27B, and Claude
  Code as an opt-in that uses the person's own plan.
- **Its answers are bound to a JSON schema at serving time** (grammar-constrained decoding in
  llama.cpp, MLX or vLLM), so an answer can never be malformed. It is checked again in code.
- **Learning stays in the Brain**: no fine-tuning and no self-training. What the agent "learns"
  is the change digest, the impact check and its memory of past suggestions (17.6). Anything
  durable becomes a governed note.

### 17.2 A short core prompt, skills on demand

- **The core prompt** is about 600 tokens:
  - who it is;
  - its rules: suggest, never write; trust the code-made map, never memory; never invent a note,
    a figure or a quote; say when the Brain lacks something;
  - how to use its tools;
  - the answer format.

  Small models follow short instructions far better than long ones, and long context degrades
  every model (Context Rot, 2025).
- **Each job's procedure loads only when the job runs.** These are the agent's skills in
  `builtin/agent/<action>/SKILL.md`, rewritten for a 4B model: one job, a worked example with
  real fields, the exact answer shape. A 1.7B model once copied a procedure's example text into
  its answer, so examples must be clearly marked as examples.
- **The person's kernel** (5.10) and the must-holds in play come with every job.

### 17.3 Code runs the loop

The model never decides on its own to keep going. For each job:

1. Code gathers the facts: the map, the candidates for one action, the change digest and the
   impact of each candidate (17.6).
2. The model gets one bounded question and answers in the schema.
3. Code checks the answer: valid ids, allowed tool, arguments in range. One retry on failure.
4. Code calls the tool, and the tool returns a result.
5. Repeat from step 2, up to six steps per job.
6. The job ends with suggestions, or with a hand-up: when a job needs more steps, the answer
   stays invalid after the retry, or the confidence on a typed check is low, it goes up the
   ladder.

The ladder:
1. Kev (typed checks);
2. the 4B agent;
3. the 9B or larger model, if downloaded;
4. Claude Code, if the person turned it on;
5. the person, through a card in Catch up.

### 17.4 Tools

All local, typed, validated by code.

| Kind | Tools |
| --- | --- |
| To look | the map of the Brain; `notes_search`, `notes_get`; `sheets_get` (rows and their history); `changes_since` (the change digest); `history` (an item's changes, who and why); `impact` (17.6); `past_suggestions` (its own suggestions and the person's decisions); the Library, skills, agents, workflows, projects and goals, read only |
| To suggest | a note to add, edit, merge, narrow or retire; a State update under each column's rule (8.4); a challenge or a "Still true?" card; a task opened or handed off (`todos_update`, goals plan 5.8); a goal progress note; a refit of the cuts (5.11.10) |
| To use the app for the person | drafts of a project, a sheet from a template, a workflow from a template, an agent's role; a run of a skill or a workflow. Only when the person asks in the agent's panel, or as a suggestion they accept. Never something irreversible or outside the machine (the action policy) |

Every suggestion lands in Catch up, or in the panel, under the presets and the friction of its
tier. The agent has no tool that writes to the Brain or acts outside.

### 17.5 Kev inside the agent

Typed checks go to Kev, which is faster and calibrated:
- is this stale;
- is it a duplicate;
- does it contradict that;
- is this worth suggesting at all;
- which tier does this belong in.

The 4B model writes only what needs words: a merged note's text, a card's reason, an answer in
the panel. On a laptop, each check uses Kev-0.8B only if it qualified (5.11.15); otherwise the 4B
model answers it with a schema.

### 17.6 Staying current: the change digest, the impact check and its memory

- **The change digest** (`changes_since`). Code builds it from undo points, State cell logs,
  proposals decided, the ledger's use counts and the goal checks: what changed since the agent's
  last run, grouped by area. The map carries a line of it.
- **The impact check** (`impact(item)`). Before any suggestion, code lists what depends on the
  item:
  - links from other notes and document sections;
  - skills, agents and workflows that point to it;
  - briefs that used it in the last 30 days;
  - must-holds that reach those briefs;
  - computed columns and goal measures built on it;
  - open tasks that load it.

  For an edit, merge or retirement, the replay harness (10.3) rebuilds the recent briefs that
  used the item and shows what would change. Every card carries the result in a line, for
  example "Merging these touches 3 skills and 14 briefs from the last month; 2 briefs would
  change." This is the blast radius from section 9, computed before the suggestion is made
  instead of only at approval.
- **The memory of its suggestions** (`past_suggestions`). Each suggestion, the person's decision
  (kept, edited, declined) and the reason given are kept as episodes, and found again by topic
  when a similar case comes up. Agents improve this way without training (Reflexion, Shinn et al.
  2023; ExpeL, Zhao et al. 2024). A lesson that holds across cases is offered to the person as a
  governed note, for example "Keep client-specific notes apart even when they look alike", so
  every AI benefits, not just the agent.
- **What it never learns from**: its own suggestions as evidence (the circular-evidence rule,
  7.2), or anything outside the scopes and partitions it may read.

### 17.7 On a laptop

- One model service is shared with retrieval (5.11.2), so the 4B model loads once.
- Upkeep jobs run in the background, on the existing schedule or a workflow. The panel answers in
  seconds on Apple Silicon. On Windows without a GPU, the panel says when an answer will take
  longer and runs as a job.
- At most one agent job at a time, as today.

### 17.8 Audit

Each job writes a run record to the ledger:
- the models and their lock fingerprint;
- the core prompt's version and the skill used;
- each step's question, answer, tool call and result;
- Kev's scores;
- the impact lines;
- where it ended (suggestions, or a hand-up and why).

The run's review shows it as one stream (section 9), with secrets masked.

### 17.9 How we will know it works

- **A labeled agent set.** For each of the actions in 17.4, seeded cases with the expected
  judgment: about 15 per action on the demo Brains, plus a private set from the person's own
  decisions in Catch up.
- **Bars, on each machine setup**:
  - agreement with the labels within 10 points of Claude Code on the same cases;
  - valid answers 100%;
  - no direct writes 100%;
  - impact lines that match a reference computation 100%;
  - hand-ups below 15% of jobs on the solo default;
  - each step inside the laptop budget: 3 s on Apple Silicon, background on Windows without a
    GPU.
- **Acceptance rate is watched, never targeted.** An agent tuned to what gets accepted learns to
  please (sycophancy, Sharma et al. 2023). Blind checks (section 9) keep its challenges honest.
- **The comparison**: 4B, 9B and Claude Code on the agent set, per machine setup. The default
  stays 4B on laptops only if it clears the bars there; otherwise the laptop default becomes the
  hand-up to Claude Code for the actions it fails, and Settings says so.

### 17.10 Building it

- **Phase 1, with 5.11 (step 3 or 3b)**: the shared model service, the machine setups, the model
  settings and the 4B model wired as the agent's local option.
- **Phase 5 (step 7)**, beside the updating loop: the core prompt and rewritten skills, the
  code-run loop, the tools, the change digest, the impact check (with the replay harness and the
  blast radius) and the suggestion memory.
- Built and tested with stand-in models on any machine. The comparison runs on Rami's PC, a Mac
  and a 16 GB laptop.

## Appendix: research anchors

Full references and corrections are in `outputs/contxt/research/paper-notes.md`; every citation
needs checking before it goes into the paper.

| Idea | Anchor |
| --- | --- |
| Tiers by how fast they change | Stability-plasticity dilemma (Grossberg 1980); complementary learning systems (McClelland, McNaughton & O'Reilly 1995) |
| State tier | Long-term working memory (Ericsson & Kintsch 1995); speed bugs (Hutchins 1995); operational data store versus warehouse (Inmon); slowly changing dimensions (Kimball); profile memory (LangGraph and LangMem); temporal entity facts (Zep, Rasmussen et al. 2025) |
| Working contexts | Attention residue (Leroy 2009); memory for goals (Altmann & Trafton 2002); context-dependent memory (Godden & Baddeley 1975); event segmentation (Zacks et al. 2007) |
| Who said it | Source monitoring (Johnson, Hashtroudi & Lindsay 1993) |
| Authority labels | Instruction Hierarchy (Wallace et al. 2024); CaMeL (Debenedetti et al. 2025); indirect prompt injection (Greshake et al. 2023) |
| Contradiction exemption | Schema-driven distortion (Bartlett 1932); normalization of deviance (Vaughan 1996) |
| Circular evidence | Illusory truth effect (Hasher, Goldstein & Toppino 1977); memory poisoning (AgentPoison, Chen et al. 2024; PoisonedRAG, Zou et al. 2024) |
| Bookends and budgets | Lost in the Middle (Liu et al. 2023); Context Rot (Chroma 2025) |
| Sections with context | Contextual Retrieval (Anthropic 2024) |
| Push delivery | Prospective memory; implementation intentions (Gollwitzer 1999) |
| Learning from corrections | Error-driven learning; reconsolidation (Nader, Schafe & LeDoux 2000) |
| Approval health | Automation complacency (Parasuraman & Manzey 2010) |
| Code staleness | Code-comment inconsistency (Wen et al. 2019) |
| A reranker over a cheap first stage | Passage re-ranking with BERT (Nogueira & Cho 2019) |
| Cuts fitted before they are trusted | Calibration of modern neural networks, temperature scaling (Guo et al. 2017) |
| Typed decision models, local | Kev (Palmer 2026, github.com/jaredpalmer/kev); Jev (TypeSafe AI 2026) as the reference. Product sources, not studies |
| An agent that improves without training | Reflexion: verbal feedback kept as memory (Shinn et al. 2023); ExpeL: lessons drawn from past outcomes (Zhao et al. 2024) |
| No self-training on its own outputs | Model collapse under recursively generated data (Shumailov et al. 2024) |
