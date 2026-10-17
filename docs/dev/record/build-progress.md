# Brain logic and Knowledge Work build: progress

Started October 9, 2026 at Rami's word (prompt 140: "implement the logic-plan and ux-plan in the
most logical order"). The plans: `brain-logic-plan.md` (BL) and `knowledge-work-ux-plan.md` (UX),
built in the order of the UX plan's section 6. Read this file first after any compaction, then
`git log` on the current branch in the `Contxt-safeguards` worktree.

Rules for the build: never develop in the live `AI-Brain/Contxt`; one branch per step, each from
the one before, committed per phase; push and pull requests only at his word (no auto-merge, merge
by hand after CI); never put real content from the owner's work Brain in the repo (the private eval set lives
in that vault's `.brain/eval/`); engine code names no organization or person; delivered text has no em or
en dashes.

## Steps

1. Merge `work-tab` (done: rami-guzlan/Contxt#5, dc4b3c0, live on 8787).
2. **BL0 measure + UX A name and structure**, branch `measure-and-structure` from dc4b3c0.
3. BL1 retrieval, briefs, kernel + UX B prompts.
3b. **BL 5.11, the local retrieval engine** (decision 16, approved October 10; prompt 157): built
   with stand-in models on this laptop, behind a byte-for-byte fallback to today's retrieval;
   the comparison and the defaults wait for Rami's PC.
4. BL2 one statement model, origins; then UX C skills and the streaming run review; **+ G0**
   (goals plan): the `goal` kind, the project `objective` at the top of task briefs, "run" in
   model-facing text.
5. BL3 ingestion and distillation.
5b. **G1** (goals plan), after step 5 and before step 6: Goals and Projects, goal pages,
   Settings > Alignment, agent goals with measures and checks, the goal coach, the Home strip.
6. BL4 State + UX D Workspace live context + UX E outputs; **+ G2**: the Tasks sheet, the
   `hand_off` tool, cards and claims, Activity > Tasks and handoffs, the sheet block.
7. BL5 updating loop, verification, streams + UX F workflows canvas; **+ G3**: "Open a task" and
   "Hand off" steps, verification as tasks, team scaffolding.
8. BL6 proof + UX G walkthrough; **+ G4**: the goals plan's evals (its section 11) and the
   walkthrough with a goal, the T-41 story and the interviewees. **Not Settings > Test the
   Brain** (BL 10.4, `testing-lab-plan.md` 10.1): another chat builds it on `test-the-brain`, in
   the worktree `Contxt-test-the-brain` (prompt 169).

Settings.tsx stays additive so the two branches merge cleanly: new tabs and sections live in
their own files (`apps/web/src/pages/settings/`), with one line each in Settings.tsx (prompt 169).

The goals plan is `goals-and-handoffs-plan.md` (all 16 decisions set); its section 9 places each
phase, folded in above at Rami's word (prompt 151). Its checklists sit in each step's plan below.

## Step 2 plan

BL0, measure:

- [x] Ledger: `model_calls` + `model_daily` (background jobs: job, model, tokens, cache, cost,
      ms) and request types on every packet (lookup, standard, planning, writing, edit, status,
      code; 89% right on the demo cases).
- [x] `brainkit/costs.py`: prices (claude-api skill, Oct 2026); fixed overhead per client;
      Claude Code transcript reader (exact first writes, re-reads, rewrites after pauses);
      daily cost by line; calibration through Claude Code (no API key or anthropic package on
      this machine): `contxt tokens calibrate`, a few cents of plan usage, run only by hand.
- [x] App: Claude Code asks (job names: check, comparison, goals, agent, calibration), runner
      runs (job run) and Ollama asks record their usage.
- [x] `brainkit/replay.py`: a logged brief rebuilt now, at a git ref, or with a proposal applied
      in a scratch copy (shares the live models and vector cache), diffed.
- [x] Eval: noise share of brief tokens; private set (`<vault>/.brain/eval/private.json`):
      `brain eval sample|label|run|status`, labeling panel on Activity's request rows; the
      public set `packages/brain/tests/evals/retrieval.json` (37 demo requests, 10 held out)
      with `scripts/retrieval_eval.py`.
- [x] `brain report`, `contxt report`, `GET /api/brain/report`, Activity > Cost and quality.
- [ ] Baseline on the live Brain (costs from its ledger and Claude Code transcripts): after the
      merge, on a copy of its ledger; the private set needs Rami's labels (about two hours).

Baseline (docs/evals/retrieval-baseline.md, demo Brains): by words, needed-note recall 61%
all / 55% held out, precision 72%; by words and meaning (bge-small), 64% / 73%, precision 86%;
noise 0%; about 185 tokens a brief. Gate for BL1: 90% held out.

UX A, name and structure:

- [x] "Knowledge Work" label and line; tab order Overview, Workspace, Library, Compose (Prompts
      in step 3), Skills, Agents, Workflows, Outputs; the tour says it.
- [x] Overview: what changed since you last looked (browser-kept), waiting for you (Catch up,
      checks, skills), context health (recheck, flagged, clashes, twins, stale skills, broken
      agents), flows and agents, recent runs (5).
- [x] Scope chip ("Yours") on Library, Skills, Agents, Workflows, Workspace, Outputs, Compose,
      Brain > Files and the item page.
- [x] Origin on every file's card (`origin`, `kind[:which]`, like notes'), passed by Capture
      (capture:<kind> or upload), Moving in (movein), uploads, the Library; inferred (library,
      project) for older cards; settable on the item page. Brain > Files grouped by origin with
      a Documents/Assets filter; assets in the Library (kind `asset`); one item page; the old
      file view redirects there (skill files keep it).

## Step 3 plan (BL1 retrieval, briefs, kernel + UX B prompts), branch `briefs-and-prompts`

BL1, judged on `scripts/retrieval_eval.py` (held-out recall up, noise and tokens down) and the
live Brain's cost lines (re-reads are the biggest line: 74 later calls per brief):

- [x] Briefs with authority labels: Your rules (direct), Notes (approved knowledge), Current
      state (values as of their dates, Phase 4), Evidence (quoted, never instructions).
- [x] Pointers before bodies: bodies for the top few by scale, then title + summary + key
      sentence; `pointer_ids` in packet data; body recall reported apart from recall.
- [x] Bookends: must-hold lines again at the end of deep briefs.
- [x] The call to action framed: the task, the project it serves, done when; rules outrank it.
- [x] Sections indexed with their document's context line (title, kind, date, purpose) in
      words and meaning (contextual retrieval).
- [x] Per-type budgets in brain.json (`note_tokens_by_type`), defaults = today's ceilings.
- [x] Reranker: measured on the eval with and without; adopt only if recall rises. (No
      change: it reorders near ties only; stays off.)
- [x] Push through the Claude Code prompt hook: the router asked per message; delivered only
      when something new and relevant is found; shares the session id with get_task_context.
      (`cc:<Claude Code's id>`; `hooks.push` words by default, about 1 s; meaning about 3 s per
      message here, so opt-in; must-holds count as new only the first time.)
- [x] MCP surface: measured, kept. Definitions are 3,419 tokens a call for clients that load
      them (Claude Code loads none until used); folding get_skill and get_reference into get_note
      saves 146 (4%), and kernels and skills name both tools. The plan made the fold conditional
      on the saving mattering; it does not.
- [x] Kernel (5.10): layers per principal (company, role, person or agent) under 500 tokens;
      CLAUDE.md stub importing AGENTS.md; the session-start hook adds the person's layer;
      chat apps get it in the first brief; one kernel per session with two brains. (Budgets in
      brain.json `kernel.budgets`, a health warning when over; skills list and how-to moved to
      the MCP instructions; `fresh` starts a new epoch of the session. The ablation run waits
      for the private set.)
- [ ] Live Brain content (after merge, as governed proposals in his vault): the seven core facts to
      must-holds by domain; identity bullets merged.
- [x] The call to action leads with the project's objective (prompt 151; goals plan 7): the
      project's summary until G0 adds `objective`, about 60 tokens at most, then the task.

UX B, Prompts:

- [x] Engine: Library kind `prompt` (references/prompts/, card load manual, never routed or
      quoted as sections unless named; the card carries the prompt verbatim so search_notes and
      get_note find it); `add_file` gains `kind` and `attach_to` (files that came with it).
- [x] App: the Prompts tab replaces Compose (/work/compose redirects); list by project, tag,
      search; a prompt's page: verbatim text, copy, versions, projects, uses, files; secondary
      actions: open in a run, use in a workflow, make it a skill, preview what a model gets,
      improve. Saving from chat: "save this prompt to my Brain" through add_file.
- [x] Migration: saved prompts in the app's database move once into the Brain, every version
      of their words kept; old ids still find them; the old rows set aside with `moved_to`.

## Step 3b plan: the retrieval engine (BL 5.11), branch `retrieval-engine`

Prompt 157 sets how the rest ships: each step ends with full checks (Python, web, typecheck,
build, ruff, format, mypy, retrieval_eval.py with no regression, a look at the demo Brain on port
8790), a push, a PR into main (the first PR also carries step 2's commits), the PR bound with
Auto-fix on, and the next step started at once on a branch from the one just opened. Merge by
hand (`gh pr merge <n> --repo rami-guzlan/Contxt --merge`) only when the app reports it green;
then merge main into the working branch. Never update the live app on 8787. No Qwen3 or Kev
downloads here.

Formats (checked October 9 against Kev's README and Laya's): decisions use System One,
`POST /v1/systemone` with `model`, `state` and `questions` (`noul`, `choice` with up to 255
options, `score`), answers keyed by question id (`noul` a probability; `choice` with
`probabilities` and `confidence`), `/v1/systemone/permute` for option order; Kev serves on
127.0.0.1 (port 8009 in its examples), pinned Hub revisions (Kev-4B `139fdd94`), a fitted
temperature per checkpoint (4B: 2.41). Relevance uses the common rerank shape: a query, an
instruction and documents in; a score per index out.

- [x] Lock: `brainkit/models.lock.json` (role, repository, revision, file checksums, dtype,
      runtime), its fingerprint; verification of a model folder; refusal of anything unlisted.
- [x] The local model service (`brainkit/modelservice.py`): 127.0.0.1 only, each model loaded
      once, shared by the engine, the app and every MCP session through a discovery file;
      `/v1/health`, `/v1/rerank`, `/v1/systemone`; backends load only verified models; stand-in
      backends for tests. The app starts it.
- [x] Adapters (`brainkit/models_client.py`): a decision client in System One's format, a rerank
      client; the engine is "on" only with a verified service whose lock matches.
- [x] The pipeline (`brainkit/engine.py`): gate; wide find (no count cap, a ceiling of 300 only
      as a speed guard, counted when hit); relevance cut; Kev's second pass (adds anything,
      contradicts, current, must-hold domains); the link loop (three rounds at most, stops when
      a round adds nothing above the cut); fit (over budget becomes a pointer, never a drop).
      Must-holds bypass relevance; the gate and the cut never remove one in play.
- [x] Cuts per Brain in brain.json (`engine.cuts`, with `fitted.date` and `fitted.eval_run`);
      defaults documented as starting points until fitted on the PC.
- [x] Audit trail (5.11.9) in the ledger: lock fingerprint, gate answer and probability, per
      candidate the keyword, meaning and reranker scores, Kev's answers, the cuts in force,
      the outcome and its reason, each layer's time; "engine: fallback" in fallback, with what
      exists. Activity's request rows: "why this note" and "why not that one".
- [x] "Should get nothing" labels in Activity's labeling panel and `brain eval`; correct nothing
      and false nothing in eval runs.
- [x] `scripts/engine_compare.py`: setups A to E; here A runs and B to E skip with a clear
      message.
- [x] Fallback: no verified service means retrieval exactly as today (keywords + bge-small,
      MiniLM off); a parity test (engine off, briefs byte for byte the same as before 3b on the
      eval sets); health says which mode runs.
- [x] Push goes through the gate when the engine is on (a gate "no" pushes nothing).
- [x] Stand-in tests: no count cap, the loop's stop rule, pointers not drops, must-hold bypass,
      correct nothing and false nothing, the lock refusing an unlisted model, every decision's
      scores in the ledger.
- Waits for the PC: real model downloads and verification, the comparison A to E, picking the
  defaults, fitting the cuts, speed against 5.11.7. Waits for Rami: the private set's labels
  (with about 20 should-get-nothing requests).

Added by prompt 161 (BL 5.11.15, 5.11.16 and 17.10's Phase 1 part, decision 17):

- [x] Machine setups (5.11.15): read the machine (RAM, GPU and its memory, Apple Silicon or
      not) at first run and on request; pick laptop (the solo default: 16 GB, no GPU with 12 GB
      or more), workstation (a GPU with 12 GB or more, or a Mac with 32 GB or more), large
      workstation (24 GB GPU or 64 GB Mac) or, below 16 GB, code alone plus bge-small and
      MiniLM; a short speed check and quality check on the demo eval set (here: says it needs the
      models). Laptop defaults: bge-small, Qwen3-Reranker-0.6B (MiniLM if it misses the speed
      budget without a GPU), Kev-0.8B, Qwen3.5-4B; the laptop's candidate ceiling starts at 100.
      Each Kev step runs on Kev-0.8B only if it qualified: the gate falls back to the reranker's
      best score against the cut, the second pass is skipped, and Settings names each fallback.
- [x] The lock gains Kev-0.8B (`9a45d25e`), the knowledge agent's role and options
      (Qwen3.5-4B 4-bit, Qwen3.5-9B, Qwen3.6-35B-A3B, Qwen3.8-27B), sizes on disk and the RAM
      each needs; official builds or checksum-verified community builds only.
- [x] Model settings (5.11.16), Settings > On this computer > Local models: the machine and
      setup; per role (meaning, reranker, decisions, knowledge agent) the model in use and every
      pinned option with its size, RAM, and speed and quality once measured; full or fallback.
      Download (verified against the lock, then offline), make default, remove, check this
      computer again. Guard rails: a choice the RAM check says will not fit is refused with the
      reason; slower than the budget warns; changing the reranker or decision model switches to
      its default cuts and suggests a refit. Choices live in this machine's settings; the ledger
      records which models ran. Claude Code for the agent is an opt-in, said in one line.
      Gate (5.11.13): the solo default stays within about 6 GB of RAM, and no default is offered
      that the RAM check says will not fit.
- [x] The knowledge agent's local option (17.10, Phase 1): the shared model service serves the
      agent role (Qwen3.5-4B, answers bound to a JSON schema at serving time and checked again
      in code), wired as the agent's local choice beside Claude Code and Ollama; stand-ins in
      tests.

How 3b's prompt-161 part came out (October 10; committed as 9d49127, opened as
rami-guzlan/Contxt#7 with Auto-fix on; checks before the push: Python 921 passed, web 179
passed, tsc, build, ruff, format, mypy clean, parity 180 briefs the same, retrieval_eval
unchanged; the demo on 8790 looked at):
- `brainkit/machine.py` reads the machine (RAM by the operating system, `nvidia-smi` for a GPU)
  and picks the setup; a machine that reports 15.0 to 15.5 GB gets the laptop setup with the
  small reranker standing in, since no default may be offered that will not fit (5.11.13). This
  laptop reads as 15.6 GB, no GPU: Laptop, 5.6 GB of models.
- The lock marks which Kev steps a model must qualify for (`extra.qualify`, Kev-0.8B only);
  `scripts/engine_compare.py --record` keeps the verdict per machine (the gate when setup C
  clears recall and both nothing gates, the second pass when D clears recall, noise and decoys).
  Unqualified, the gate goes to the reranker's best score against the cut and the second pass,
  with its must-hold domain question, is skipped; the brief's audit, Activity's "why" and
  Settings name each fallback.
- Settings, On this computer, Local models (`pages/settings/LocalModels.tsx`): the machine, the
  setup, per role every pinned option with size, RAM, speed here, downloaded or not, fits or
  why not; download (refused unless pinned with checksums; verified after), make default (only
  once downloaded; refused with the reason when it will not fit; warned when slower than the
  5.11.7 budget), remove (refused while in use), check this computer again (re-times the models
  when they run), time the models. The `brain models machine | use | download | remove | speed`
  commands do the same from a terminal.
- The quality check is the comparison (`engine_compare.py`, on the demo eval sets), run on a
  machine with the models; the Settings button does not run it yet. Waits for the PC.
- The knowledge agent's local option: `local:<model>` through the same service
  (`/v1/generate`, a JSON schema bound at serving time where the runtime can, checked again in
  code). It is the agent's default only where it is downloaded. Claude Code: an opt-in once a
  local agent model is here; until then it stays the agent unless turned off, so the agent
  keeps working on machines without the models. For Rami to confirm (opt-in as written in
  5.11.16 would leave a laptop without models with no agent).
- The model service starts with the app only when this computer's setup models are downloaded
  and verified; otherwise the app says retrieval runs on words and meaning.

## Step 4 plan (BL2 one statement model + UX C skills + G0), branch `statements-and-skills`

Started October 10 from `retrieval-engine` (PR #7). BL2's gate: every note reads without loss
(`brain check` passes) and briefs and `brain bench` stay identical (the parity golden), so the
vocabulary maps old words to new ones and rewrites no note. G0's objective-first task line is
the one intended brief change, and it already shipped in step 3 (the summary stands in).

- [x] One vocabulary (`brainkit/statements.py`): identity, rule (convention, preference), fact,
      decision, procedure, value (the State tier; older `state` notes read as values), project
      (older `focus`), goal; the capture types, distillation's kinds, the note kinds, the MCP
      and CLI choices all derive from it, and every older word still reads.
- [x] `said_by` on every statement: the owner, the owner's AI by inference, another person, a
      document, a synced system, an agent run; set on proposals from where they came, derived
      for older notes from `origin`; shown on the note page and in the API (not yet in briefs).
- [x] Time: `learned` (approval), `confirmed`, and `review_by` derived from a shelf life by kind
      unless set (project 30, fact 180, decision 365, rule and identity 365, procedure 180),
      the owner able to change each in brain.json; exposed now, used by the updating loop in
      step 7 (today's review cadence is unchanged).
- [x] Tier from kind and load: alignment (rules, identity, must-holds, goals), state (values),
      knowledge (the rest).
- [x] Audit retention: brief text 90 days under personal and careful, 730 under regulated,
      unless set (the setting already in Approval).
- [x] Origins on every file and Library item, and the Library's items with kind, origin,
      versions, projects and scope: check what step 2 left and fill the gaps.
- [x] UX C: the run bar on Skills (a prompt, several skills in order, where it runs, the
      project, Run); Brain skills with one-click runs (the built-ins and the agent's actions);
      your skills by purpose (what for, last used, maybe out of date, used by, version, the
      Claude Code copy); a quiet Recent runs drawer; the run review streaming each step live and
      replaying a finished run. Backend: one stream per run kept on disk, secrets masked.
- [x] G0 below.

How step 4 came out (October 10; committed as 7478754, opened as rami-guzlan/Contxt#8 with
Auto-fix on; checks: Python 938 passed in the full run, its one Windows file-lock failure fixed
and every touched file passing after, web 180 passed, tsc, build, ruff, format, mypy clean, parity
180 the same, retrieval_eval unchanged, the demo on 8790 looked at):
- Five kind lists, not three, disagreed: the note kinds, the capture types, the workspace's
  proposal kinds, the adapter's map to note kinds and the knowledge agent's. All now derive from
  `brainkit/statements.py` (the core mirrors it in `domain/statements.py`, a server test keeps
  them equal). The disagreement had a real effect: a preference proposed from the workspace was
  filed as a fact, so under the personal preset a preference from a chat applied at once,
  though the presets say preferences always wait. It is now a rule of subtype preference, and
  waits. A decision is filed as kind `decision` (still `type: decision`); a procedure as kind
  `procedure`, which the config treats as a constraint, as rules were for procedures before.
  For Rami to confirm: preference as a rule subtype (the plan's vocabulary) over today's fact.
- No note is rewritten; the 180 parity briefs are byte for byte the same; `brain check` passes
  on every demo Brain. Statement fields are read from what notes record and shown as
  `statement` in the entry API; the derived review date waits for the updating loop (step 7);
  "a brief can say where a quoted document came from" (16.4) waits too (it changes briefs).
- G0: goal notes load `manual`, with `level`, `goal_status` (not `status`, which is a note's
  own) and the other fields checked; projects take `objective` (60 words at most; a change needs
  a reason) and `goals`, through the MCP tool, the REST API and the entry fields. Model-facing
  text says "run" for the app's runs, with a test that reads every tool description, run
  template, run instruction and claim message and fails on "task" as a word.
- UX C: the run bar, run review (live, replay, the brief it was given, how it ended, where its
  work waits), Brain skills one click each, your skills by purpose with their facts, Recent runs
  in a closed drawer, and every run's stream on disk (`<data>/runs/`, 200 runs kept) with
  credentials masked; the purpose facts read git once per Brain state (6 s the first time on
  the demo, 0.2 s after). Settings.tsx untouched in this step.

## Step 4 additions from the goals plan: G0

- [x] The `goal` kind in the one vocabulary (BL2): owner, level (purpose, yours, agent), serves,
      scope, progress, measure, due, cadence, status, why, started, review_by; loaded `manual`,
      filed under the owner's area like `you-goals`; every existing note reads as before and
      `brain check` passes.
- [x] Projects gain `objective` (a sentence or two, about 60 words at most, governed like the rest
      of the baseline; a change needs a reason and makes an undo point) and `goals` (optional
      links); the call to action switches from the summary to the objective; a project without
      one gets the summary meanwhile (and a nudge on its page in G1).
- [x] "Run" instead of "task" in model-facing text (runner prompts, run contracts, tool
      descriptions), so "task" means only the new kind; records and tables keep their names;
      tests that grep model-facing text.

## Step 5 plan (BL3 ingestion and distillation), branch `ingestion-and-distillation`

Started October 10 from `statements-and-skills` (PR #8). Built without models where the plan
allows; triage and the gates that need labeled transcripts wait (listed at the end).

- [x] Who said it at the door: every proposal path records `said_by` (a chat over MCP: the
      owner's AI; the app: the owner; swept folders, Moving in files, Work uploads and filed
      documents: a document; meetings: another person; runs and agents: an agent); a distilling
      model passes it per statement.
- [x] Instructions inside content: a rule found in a document, a meeting or a synced system is
      kept as "The document says: ...", never as a rule; its card says where it came from; the
      owner can still make it a rule.
- [x] Hash dedupe before any model call: a capture read before, or held word for word, makes no
      model call.
- [x] Evidence must be real: a quote an AI attributes to the person is checked against what the
      ledger logged in that conversation; a quote not there marks it inferred, and it waits.
- [x] Pre-pass (code): split by structure (speakers, headings, slides), drop boilerplate, find
      dates, figures and names, find sensitive spans (emails, phone numbers, account and ID
      numbers).
- [x] Privacy: sensitive spans redacted in what goes to a cloud model, on under careful and
      regulated, off under personal unless turned on (decision 13).
- [x] Triage behind a switch (Haiku 5.5 or a qualified local model; under regulated, local or
      redacted), off until measured; stand-ins in tests.
- [x] Distillation's instructions: contradictions exempt from the goal test; who said it on
      every statement; values as dated values until the State tier (step 6) takes them as cells.
- [x] Reconcile: the circular-evidence rule (an AI output built from a brief cannot count as
      evidence for the notes in that brief); duplicates collapse.
- [x] The left-out list as a searchable record, re-scored when the goals change.
- [~] Gates as seeded tests: no circular promotion (seeded test), every fabricated quote caught
      (a seeded set of five, and the said ones pass); "no seeded contradiction left out" is now
      in the instructions and needs a distilling model to measure. Cost per capture: the cost
      report's jobs line counts each distillation and triage call once real runs happen.
      Precision, recall and tier routing wait for labeled transcripts and the interview sorting
      exercise (Rami) and the models.

How step 5 came out (October 10; committed as 923159a, opened as rami-guzlan/Contxt#9 with
Auto-fix on; checks: Python 959 passed, web 182 passed, tsc, build, ruff, format, mypy clean,
parity 180 the same, retrieval_eval unchanged):
- Who said it is set on every new note from its proposer's word or its origin; Moving in counts
  as the owner's own words (instruction files and pastes: the owner; exports a model read: the
  owner's AI), so the owner's CLAUDE.md rules stay rules.
- A rule from a document, someone else in a meeting or a synced system becomes "The document
  says: ..." (or "Someone else said: ..."), a fact with `instruction_from`; the review card says
  so, and the owner can still make it a rule.
- Quotes are checked against the requests the ledger logged in that conversation (the person's
  messages as written); a missing one marks the statement inferred and pending, with a card
  line.
- Hash dedupe covers captures read before under another capture, text the Brain holds word for
  word, and copies in one request; asking again about the same capture still reads it.
- The pre-pass is in the core (`services/prepass.py`); redaction applies where a model reads a
  capture (the run's packet and `get_context_item`) and in the run review's "brief it was
  given", never in what the person sees. Switch: Settings > Approval, "Hide private details
  from cloud AI" (`pages/settings/Privacy.tsx`, two lines in Settings.tsx).
- Triage: `apps/server/.../triage.py` behind the distillation settings' `triage` (off); the
  core calls it through a hook, so Capture's "remember" and the request route both use it; a
  capture with nothing durable makes no distillation call; the packet hands the model only the
  kept parts, saying so. The choice sits beside the model for AI work (Settings > On this
  computer).
- The circular-evidence rule refuses a proposal whose text repeats (similarity at the review's
  close mark) a note the output's own conversation was handed.
- The left-out record: `GET /api/brain/distill/left-out?q=`, scored against the goals and
  active projects at read time; Capture shows it, searchable, with "fits your goals now".

## Step 5b: G1 (after step 5, before step 6), branch `goals-and-projects`

- [x] Goals and Projects at `/projects` (Projects until a first goal; projects-only layout; the
      new-project form, objective first).
- [x] Goal notes and migration (`you-goals` as the purpose; agents' goal lines become
      suggestions); goal pages at `/goals/:id` (header, check-in, updates feed from journals,
      board with notes, checklists, docs, projects, links, decisions; four templates; the "AIs
      can read" switch and plan files; suggestions; Ask AI).
- [x] `measures.py` with today's signals; `goal_checks`; goal journals; Settings > Alignment
      (the old `?tab=goals` redirects; the kernel's layers and budgets under Rules); agent goal
      drawers; the goal coach and the form; the Home strip and the weekly review (off by
      default); the knowledge agent's four goals, its new gathers and "why I'm doing this".
- [~] Done when (goals plan 10): one card per seeded slip (seeded test, engine and API); only
      shared blocks reach an AI (API test: a private note is in neither the plan file nor
      `get_note`); no goal changes a brief's notes (goal notes load `manual`; a test asks about
      the goal and the brief does not carry it; parity 180 the same). On the demo Brain, set by
      hand: a goal saved, checked in and a suggestion made a step in about a minute, the
      check-in itself a few seconds. The coach was tested with a stand-in model (questions,
      then a draft); timing the coach on a real model waits for real runs.

How step 5b came out (October 10):
- Engine: `brainkit/ladder.py` (goal notes, `set_goal`, `change_goal`, `check_in`,
  `journal_note`, `run_checks`, `cards`, `write_plan`, `context`, `link_project`, the
  knowledge agent's four `STARTERS`, `must_holds`), `brainkit/measures.py` (seven kinds, the
  signal library: notes overdue, items waiting, unanswered questions, quiet projects; must-hold
  recall, milestones and a sheet column listed with what they wait for), the ledger's
  `goal_checks` (kept for good, past retention), `journal/goals/<id>.jsonl`, and the plan file
  `goals/<id>/plan.md` (now a governed folder, committed like the rest). `Brain.ladder`, `goal`,
  `goal_cards`, `act_goal`. `get_note` on a goal opens with its shared plan. A goal's stored
  `goal_status` is its lifecycle (active, paused, met, missed, dropped, retired); how it is
  going comes from checks. An agent goal names who keeps it in `kept_by` (a note's `owner` stays
  a scope). Goal fields are editable through `governance.update`, only on goal notes. Goals are
  written with `kind: goal` even in an older layer vault.
- Status rules as plan 4.3: your call stands for one cadence, stale after it, "Not checked in"
  after two; a computed measure that disagrees is a flag. Agent goals: on track at target,
  needs attention within a tenth, off track further out or on a second miss in a row; a card
  only when a goal turns off track, kept until it recovers or is set aside.
- App: `goal_boards` (migration 0009) keeps each board and its suggestions (said-no ones
  remembered); saving writes only shared blocks to the plan file. `services/goals.py` (ladder,
  get, set from the coach's draft with the "Plan it" template filled in and first steps as
  suggestions, change, check-in, decisions, links, starters, checks, the coach's prompt and
  reader, Home's strip, the weekly review built by code, Alignment's Rules). The worker runs
  due checks every ten minutes (code only). Catch up gains slipped agent goals (one card per
  slip) and suggested steps grouped by goal, and an agent's "Goals it serves" line that names
  no goal is offered as a goal with a measure. The knowledge agent's page leads with its goals,
  and each action says which goal it serves; check-alignment gathers your goals with no
  check-in, no projects or no plan for the obstacle. A system note, `system-goals`.
- Routes: the ladder lives at `/api/goals` (with `/home`, `/rules`, `/settings`, `/starters`,
  `/checks`, `/coach`, and per goal `/check-in`, `/board`, `/suggestions/{id}`, `/decisions`,
  `/projects`), because `/api/brain/goals` already answers the purpose interview. A project's
  objective changes at `PUT /api/brain/projects/{id}/objective`, with a reason.
- Web: Goals and Projects (the sidebar says so once a goal exists), goal cards with the check-in
  on the card, "Set a goal" (talk it through, or fill it in), objective-first new projects,
  "Serves" on project cards and pages, the objective editable with a reason; a goal's page
  (`/goals/:id`) with its header, check-in, board and rail (projects, "AI on this" waiting for
  G2, suggestions, updates with filters, what your AI gets); Settings > Alignment
  (`pages/settings/Alignment.tsx`; Settings.tsx changed only the tab's line, its import, its
  render line and the `goals` redirect); Home's strip; Catch up's goal sections.
- Not as planned, on purpose: note blocks keep their text on the board (in the app's database)
  rather than in Workspace docs, and a Doc block links a Workspace doc by id; blocks move with
  buttons, since drag and drop arrives with UX D's library in step 6; the sheet block and
  sheet-driven progress wait for State (step 6); an accepted suggestion becomes a checklist
  item until tasks arrive in G2; the purpose's trend signals (corrections a week) wait for
  step 7, so the purpose shows the interview's "how will you know" answer for now.

## Step 6 plan (BL4 State + UX D live context + UX E outputs + G2), branch `state-and-tasks`

Built in this order, committed per part:

- [x] 6a, the State tier in the engine (BL 8): `brainkit/state.py`. Sheet types
      (`vault/state/<sheet>/schema.json`: key column, typed columns with friction class `free` /
      `confirm` / `locked`, age limit, source, sensitivity, partition rule, scope), rows with key
      and aliases, append-only cell events (`vault/state/<sheet>/<row>.jsonl`: value, as of,
      written at, who said it, source, session or run, confidence), the current value as the
      latest valid event, a Markdown snapshot per sheet. Column types: text, number, money, date,
      date range, status, person, link, reference. Computed columns: one formula per column with
      a small safe evaluator (arithmetic, dates, text join, comparisons, AND, OR, IF, COUNT, SUM,
      AVERAGE, MIN, MAX over linked rows, a cell's age), a summary row; never cell events, never
      editable by AIs. Templates: Accounts, Repos or Services, Standards, Vendors, Contacts,
      Content calendar, Project board, and the built-in Tasks sheet. Staleness by column age.
      Promotion and demotion as suggestions. Partitions sealed; must-holds win over cells.
- [x] 6b, reading and writing State from AIs: `get_state` and `update_state` (free applies and is
      marked AI-filled until a person touches it, confirm waits, locked is refused, regulated
      waits for every AI write: decision 4); the brief's "Current state" block when a request
      names an entity or a working context is active (one line a value with its date and what
      changed since this session saw it, 300 tokens a row at most, computed values marked);
      working contexts (BL 8.3: explicit switching, the `context` argument, a resumption card,
      14 idle days asks).
- [x] 6c, G2 in the engine: the Tasks sheet and `brainkit/handoff.py` (`hand_off`: take, save,
      pass on, finish, goal notes; the card at about 250 tokens; the rules in goals plan 5.8),
      registered on the Brain's MCP and the app's; `get_task_context` with a task as `context`
      returns the card; pending handoffs one line each in first briefs; agents' own tasks for
      their slipped goals (one open per goal, five per agent).
- [x] 6d, the app: State API and Workspace's live context (grid with AG Grid Community, board
      with dnd-kit, calendar with FullCalendar's standard edition; templates; a row's history;
      AI-filled cells marked; formula columns in plain words; the summary row); the Brain tab's
      State logs; outputs linked to project, State row and maker (BL 16.5) with grouping by
      project and entity and filters (UX E); `/api/work/handoffs` and Activity > Tasks and
      handoffs (Now and Timeline); the board's sheet block and sheet-driven progress; "AI on
      this" rails and project pages semi-reflected; Catch up's "Handed to you" and "Not claimed
      for a day".
- [~] Gates (BL 8.9, UX D and E, G2) as seeded tests: rows retrieved for named entities 100% (a
      seeded set of five names and aliases), a State block at most 300 tokens a row, seeded
      stale cells flagged 100%, no cross-partition leak, computed values match a reference 100%
      (15 formulas, and unsafe ones refused); the T-41 story end to end, and a fresh session
      resumed from the saved card (its done so far, decisions and next step lead the brief).
      Whether formulas make date and count answers more accurate waits for real model runs.

How step 6 came out (October 10):
- Engine: `brainkit/state.py` (sheets in `vault/state/<sheet>/`: schema.json, one append-only
  cell log per row, SNAPSHOT.md; nine column types; free, ask-first and owner-only columns; age
  limits; partition rules; eight templates including the built-in Tasks sheet; summary rows;
  promotion and demotion suggestions) and `brainkit/formulas.py` (one formula per column read
  through Python's `ast` into a short list of allowed shapes; TODAY, CREATED, UPDATED, AGE,
  COUNT, SUM, AVERAGE, MIN, MAX over linked rows, LOOKUP, IF, AND, OR, NOT, JOIN, DAYS,
  ADD_DAYS, ROUND). `brainkit/handoff.py`: `hand_off` (take, save, pass on, finish, goal notes),
  the card at about 250 tokens with the project's objective and the goal's line filled by code,
  credentials masked, evidence checked against recorded outputs and decided proposals, a done
  task writing to its project's journal and its goal's. `state` is a governed folder.
- Briefs: a named row (key, or an alias of two letters or more) gets "Current state", dated,
  AI-filled and stale values marked, computed ones marked, at most 300 tokens; in the same
  conversation an unchanged row comes as one line, and a changed one marks what changed since it
  was sent. `get_task_context` takes `context` (a task, a goal, a project, a State row or
  general), which the conversation keeps; a context idle 14 days asks to resume or close; a
  task's card leads the brief; a conversation's first brief lists tasks waiting to be picked
  up. The parity briefs stay byte for byte the same.
- MCP: `get_state`, `update_state` and `hand_off` on the Brain's server and the app's (runs);
  one sentence more in the server instructions; `record_output` takes project, for and maker.
- Reminders: a run that works a task (an agent's run started by a handoff) has a contract
  check that only `hand_off` satisfies; Claude Code's Stop hook, `python -m
  brainkit.hooks.task_stop`, sends a session with an active, unsaved task back once. A slipped
  agent goal opens a task for its agent (one per goal, five per agent).
- App: Workspace has Your docs and Live context (sheets from templates, what waits for your
  tap); a sheet's page has the grid (AG Grid Community), the board (dnd-kit, plus a "Move to"
  menu on every card) and the calendar (FullCalendar's standard edition, 6.1), the summary row,
  columns with who may change them and formulas in plain words, and a row's drawer with its
  marks, what waits and its history. Activity > Tasks and handoffs (Now and Timeline, a task's
  drawer with its card, log and the hand-off composer). Catch up: handed to you, not claimed for
  a day (Remind, Take back), values waiting. A goal's "AI on this" lists its tasks, a suggestion
  you accept becomes a task, the board has a sheet block whose column can drive the goal's
  computed measure. Project pages show their tasks and what AI is on. Outputs group by project,
  then by what each is for (an account's bucket), with filters, and each can be linked by hand.
  Measures gain a sheet column, milestone tasks done and unclaimed handoffs.
- Not built here: a working-context picker in the app (contexts are named in a chat, or by
  opening a task); a Brain-tab view of every sheet's log (each row's history is on its drawer,
  and Activity's timeline covers tasks); promotion and demotion suggestions shown in Catch up
  (the engine makes them); Claude Code's session-start hook listing handoffs (the first brief
  does); the hook registered by an installer (it is documented in its module).

## Step 6 additions: G2

- [x] The board's sheet block and sheet-driven progress; the Tasks sheet (built in, columns in
      the goals plan 5.1) and its validation; owners and tool queues.
- [x] The `hand_off` tool (take, save, pass, finish, goal notes) with its reminders (the run
      finishing gate, Claude Code's Stop hook, first briefs); cards (about 250 tokens) with the
      agent's words plus what code verifies; claims, reminders, take-backs; pending handoffs in
      first briefs and the session-start hook; agents' runs from handoffs.
- [x] "AI on this" rails; Activity > Tasks and handoffs (Now and Timeline); project pages
      semi-reflected; Done with evidence; journal lines; milestones; Catch up cards.
- [x] Done when: the T-41 story end to end, and a fresh session resumed from a saved card redoes
      nothing (seeded test with a stand-in agent).

## Step 7 plan (BL5 updating loop + UX F workflows canvas + G3 + BL section 17), branch
`updating-loop`

- [x] 7a, the updating loop in the engine (BL 9): corrections make suspects and a "Still true?"
      card; salience offered for a note that proved wrong; the exceptions ledger (an approval
      that bends a rule counts; at three in 90 days, ask); approval health (median seconds,
      rate, advice); the quarterly alignment review offered; single-source flags; independent
      evidence by brief lineage; output checks against must-holds (deterministic from each
      must-hold's words, a model check as a hook), sending a run back once and flagging a
      recorded output; blind judging held by a test; verification with sources as an upkeep
      action whose findings arrive only as challenges or cards with citations; admins per scope
      scaffolded (the solo owner is admin of every scope); blast radius at approval through
      the replay harness.
- [x] 7b, the knowledge agent run locally (BL 17): a core prompt of about 600 tokens, the
      skills rewritten for a 4B model with marked examples, the code-run loop (one bounded
      question a step, code checks, one retry, six steps, hand-ups up the ladder), the tools,
      typed checks through Kev with a code fallback, the change digest, the impact check, the
      memory of suggestions with lessons offered as notes, a run record per job, a labeled agent
      set run with stand-ins.
- [x] 7c, UX F: the workflow canvas on React Flow with the node library (triggers, upkeep,
      ingestion, distillation, State, verification, human check, output, connectors shown as
      coming later), a node's settings and last run beside it, templates; step kinds that
      declare what they take and give; G3's "Open a task" and "Hand off" steps.
- [x] 7d, the app: Catch up's "Still true?" from corrections, bent rules, corroboration,
      approval health, the quarterly review, agent hand-ups and lessons; "That's wrong" on a
      request; the agent's runs with their steps; measures gain corrections a week and drafts
      sent back.
- [x] Gates as seeded tests: wrong beliefs found 8 of 8 within two cycles, correction suspects
      right 60% or more, 20 briefs replayed in 10 seconds or less, exception sequences flagged
      at the third, every deterministic must-hold violation caught, verdicts unchanged when the
      proposer is hidden or swapped, verification findings only as cards with citations,
      secrets never in a stream; the agent set's bars with stand-ins (valid answers 100%, no
      direct writes 100%, impact lines matching a reference 100%). Agreement with Claude Code,
      hand-up rates and speed per machine setup wait for the PC.

## Step 7 additions: BL section 17, the knowledge agent run locally (decision 17)

- [x] The core prompt (about 600 tokens: who it is; suggest, never write; trust the code-made
      map; never invent a note, figure or quote; say when the Brain lacks something; its tools;
      the answer format) and the agent's skills rewritten for a 4B model in
      `builtin/agent/<action>/SKILL.md` (one job, a marked worked example, the exact answer
      shape); the person's kernel and the must-holds in play with every job.
- [x] Code runs the loop: code gathers the facts, the model answers one bounded question in the
      schema, code checks it (valid ids, allowed tool, arguments in range; one retry), code
      calls the tool; up to six steps a job; hand-ups up the ladder (Kev, the 4B agent, 9B or
      larger if downloaded, Claude Code if turned on, the person through Catch up).
- [x] The tools (17.4): to look (the map, search_notes, get_note, get_state, changes_since,
      history, impact, past_suggestions, read-only Library, skills, agents, workflows, projects,
      goals); to suggest (note add, edit, merge, narrow, retire; a State update; a challenge or
      "Still true?"; a task through hand_off; a goal note; a refit of the cuts); to use the app
      for the person only when asked (drafts of a project, a sheet, a workflow, an agent's role;
      a skill or workflow run), never irreversible or outside the machine. No tool writes.
- [x] Kev inside the agent (17.5): stale, duplicate, contradicts, worth suggesting, which tier;
      the 4B model writes only what needs words; on a laptop, unqualified Kev-0.8B checks go to
      the 4B model with a schema.
- [x] The change digest (`changes_since`), the impact check (`impact(item)`: links, skills,
      agents and workflows that point to it, briefs that used it in 30 days, must-holds that
      reach them, computed columns and goal measures, open tasks; the replay harness for edits,
      merges and retirements, one impact line on every card) and the suggestion memory
      (`past_suggestions`, episodes found again by topic; a lesson that holds becomes a governed
      note; never its own suggestions as evidence).
- [x] Audit (17.8): a run record per job (models and lock, core prompt version and skill, each
      step's question, answer, tool call and result, Kev's scores, impact lines, the ending).
- [x] How we know (17.9): a labeled agent set (about 15 cases per action on the demo Brains, plus
      a private set from Catch up decisions); bars per machine setup (within 10 points of Claude
      Code, valid answers 100%, no direct writes 100%, impact lines match a reference 100%,
      hand-ups under 15% on the solo default, each step inside the laptop budget). The
      comparison of 4B, 9B and Claude Code waits for the PC, a Mac and a 16 GB laptop.

## Step 7 additions: G3

- [x] Workflow steps "Open a task" and "Hand off"; verification with sources as tasks;
      correction and output-check signals; teammates as owners and admins for shared goals
      (scaffold; the solo app shows nothing of teams).

## Step 7: what came out (branch `updating-loop`)

- The updating loop (BL 9) in the engine: corrections name their suspects from the brief before
  them (5 seeded cases, the 60% bar held); the exceptions ledger asks at the third bent rule in
  90 days; approval health advises when approvals take seconds and nearly always pass;
  single-source notes are flagged; outputs count once per brief lineage; admins per scope
  (solo: none); the blast radius replays 20 briefs in under 10 seconds; 8 of 8 seeded wrong
  beliefs found within two cycles.
- Output checks: every seeded deterministic must-hold violation caught (figures, dashes,
  forbidden phrases); a skill result that breaks one is sent back once with what broke, then
  kept and flagged; a recorded output is flagged.
- Blind judging held by a test: the model check reads only the two texts, the same whether the
  proposer is hidden, the owner or another AI.
- Verification with sources: findings arrive only as challenges or "Still true?" cards, each
  with its citations; one without a source is never kept. The test found a real bug (an "ask"
  card was built without its key, so keeping it crashed), fixed.
- The knowledge agent run by code (BL 17): core prompt, skills with marked made-up examples,
  the six-step loop with one retry and hand-ups, the look and suggest tools (none writes), Kev
  typed checks with a code fallback, the change digest, the impact line, suggestion memory and
  lessons, a run record per job; the labeled set (3 cases per action today) passes every bar
  with the oracle stand-in.
- The app: Catch up's "Keeping what it knows true" (Still true?, bent rules, approval health,
  corroboration, the quarterly review, lessons kept as notes, the agent's hand-ups);
  "That's wrong" on an Activity request; the agent page's runs step by step; routes under
  /api/loop.
- G3: workflow steps "Open a task" and "Hand off" run by code at once (T-1 opened and handed to
  Claude Code in a test); ingestion steps (Library refresh, URL fetch, folder sweep) run by the
  server; "Find what to remember" as a step; the measures gain corrections and drafts sent back;
  teammates as goal owners scaffolded (a solo Brain refuses them; one naming teammates keeps
  them, with the scope's admins).
- UX F: the workflow canvas on React Flow 12.11.6 (Canvas or List), the node library by group
  with what each kind takes and gives, triggers with "when something happens" and direct
  connectors shown as coming later, the picked box's settings and its last run, and a red line
  where a step cannot take what it is given. On the demo, the fit check caught my own
  Accounts template (a sheet step gave nothing a later step could read); the sheet step now
  passes on the value it wrote, and a test holds every template to fit.
- Waiting for the PC or real runs: agreement with Claude Code, hand-up rates and speed per
  machine setup; growing the agent set to about 15 cases per action. Waiting for Rami: the
  private agent set from his own Catch up decisions.

## Step 8 plan (BL6 proof + UX G walkthrough + G4), branch `proof-and-walkthrough`

Not Test the Brain (prompt 169: another chat builds it on `test-the-brain`).

- [x] The drift eval (BL 10.6): seeded long tasks through the run hooks with and without
      re-anchoring, scored against their contracts (`brainkit/proof.py`, stand-in worker with
      bounded attention).
- [x] The four-week soak: captures, corrections, changed values, bent rules and items left
      waiting through four simulated weeks; kernel stability, explained brief movement, stale
      values caught, exceptions flagged, goal-card noise.
- [x] The alignment tax: alignment's share of first and later briefs, and the check's time.
- [x] The final report card (`scripts/report_card.py`): retrieval, every section's gate tests,
      drift, the soak, the tax, the agent set, and what waits. First run:
      `report-card-2026-10-10.md` beside this file.
- [x] Measured results for the paper: `../research/paper-notes.md`, "Measured in the build".
- [x] System notes rewritten: the overview (vault folders, the one vocabulary and tiers, what a
      packet carries, governance in a paragraph), the knowledge agent (eight actions, the
      code-run loop, tools, Kev, run records, lessons), and a new note on the updating loop.
- [x] G4 evals as seeded tests (`test_g4.py`): the disagreement flag exactly when measure and
      call disagree (9 of 9 cases), goals optional, the objective at the top of every task brief
      within 60 tokens, measures against a reference computation, one card per slip, the
      handoff card near 250 tokens, no secret in a card, a goal note or a plan file.
- [x] The walkthrough script (`walkthrough-script.md` beside this file): every screen on the
      demo Brain with its bars, then a real day on his Brain, then G4 with the interviewees.
- [ ] Waits for Rami: the walkthrough itself, the real day, a goal of his through the coach,
      the T-41 story and the two interviewees, board restraint counted, objectives judged
      blind, and his sign-off.

## Step 8: what came out

- Drift (stand-in): with re-anchoring, objective kept 5 of 6, must-holds in view 100%, all
  finished; without, 0 of 6, 8%, none. The loss: a distractor three calls before the end,
  inside the eight-call cadence.
- Soak: kernel stable all four weeks; no unexplained brief movement; 4 of 4 superseded values
  caught; the third bent rule flagged in week 3; one card per slip.
- Tax: 42% of a first brief (414 of 994 tokens), 14% of later ones (47 of 323); the output
  check under a millisecond.
- G4 found a real gap: a secret pasted into a goal's "why", a check-in line or a shared board
  block was kept as written in the goal note, journal and plan file every AI reads. Goal text
  is now masked the way task cards are.
- On the demo: all 30 endpoints the screens use answer; the screens I opened render.

## Log

- 2026-10-09 21:20: step 2 committed, 29211c7 on `measure-and-structure` (70 files). Checks:
  Python 866 passed (the 3 that failed in the full run were edits made mid-run; they pass
  alone), web 175 passed, tsc, build, ruff, mypy clean. Live Brain cost baseline (private,
  kept on the laptop only), about $1.67 a day, re-reads the biggest
  line (74 later calls per brief), the Brain about 0.85% of what its Claude Code sessions cost.
  Not pushed (waits for Rami's word).
- 2026-10-10 01:31 (05:31 UTC): rami-guzlan/Contxt#6 merged by Rami as 7dc4f0e, carrying
  steps 2 and 3 (measuring context; briefs that say what directs; prompts kept in the Brain word
  for word; the layered kernel, push before the model asks, and the call to action led by the
  project's objective). All eight CI checks were green: Python, Core on PostgreSQL, the model
  tests, web, install and connect on Ubuntu, Windows and macOS, and the Docker image. Main is
  merged into `retrieval-engine` (97b8c6e); main held only the merge commit, so no file changed.
  The live app on 8787 was not touched. Still with Rami from this step: the live Brain's content
  proposals (core facts to must-holds by domain, the identity bullets merged), approved in his
  app, never committed to the public repo.
- 2026-10-10: rami-guzlan/Contxt#7 merged as a859309 (by hand with gh, after the app reported
  all eight checks green), carrying step 3b: the local retrieval engine built with stand-in
  models behind a byte-for-byte fallback (parity on 180 eval briefs), the lock and the shared
  model service, the audit of every decision and Activity's "why", requests that should get
  nothing, the setup comparison A to E, the machine setups and Settings > On this computer >
  Local models, and the knowledge agent's local option. Main fast-forwarded into
  `statements-and-skills` (step 4), no conflicts. The live app on 8787 was not touched. Waiting
  for the PC: real model downloads, pins and verification, the comparison B to E, defaults, cut
  fitting, speed, Kev-0.8B's qualification. Waiting for Rami: the private set's labels, and
  confirming Claude Code for the agent as an opt-in once a local agent model is here.
- 2026-10-10: rami-guzlan/Contxt#8 merged as ccb5edd (by hand with gh, all eight checks green),
  carrying step 4: one statement model (five kind lists from one vocabulary; a preference from
  the workspace now a rule of that subtype that waits), statement fields read from what notes
  record, brief text 730 days under regulated, G0 (goal notes, the project objective, "run" in
  model-facing text with a test that holds it) and UX C (the Skills run bar, run review with
  replay and the brief it was given, Brain skills one click each, skills by purpose, recent runs,
  every run's stream on disk with credentials masked). Main fast-forwarded into
  `ingestion-and-distillation` (step 5). Waiting for Rami from it: confirming a preference as a
  rule subtype.
- 2026-10-10: rami-guzlan/Contxt#9 merged as 565e94e (by hand with gh, all eight checks
  green), carrying step 5: who said each statement at the door, instructions inside content
  kept as what the document says, quotes checked against what the person said, the
  circular-evidence rule, hash dedupe before any model call, the code pre-pass with redaction
  for cloud models under careful and regulated, triage behind a switch that stays off, and the
  left-out record searchable on Capture. Main merged into `goals-and-projects` (2a7da89, no
  conflicts), whose PR rami-guzlan/Contxt#10 carries step 5b (G1) with Auto-fix on; step 6
  starts on `state-and-tasks`. Waiting for Rami from step 5: labeled transcripts and the
  interview sorting exercise for its precision, recall and tier-routing gates. Waiting for real
  runs: measuring triage, and cost per hour of meeting.
- 2026-10-10: rami-guzlan/Contxt#10 merged as 6518e94 (by hand with gh, all eight checks
  green), carrying step 5b (G1): goals as notes loaded only when asked for, check-ins and
  journals, computed checks with one Catch up card per slip, the knowledge agent's four goals,
  Goals and Projects, a goal's page with its board and shared plan file, the goal coach (tested
  with a stand-in), Settings > Alignment, Home's strip and the weekly review. Main merged into
  `state-and-tasks` (bf6642c, no conflicts), whose PR rami-guzlan/Contxt#11 carries step 6 with
  Auto-fix on; step 7 starts on `updating-loop`. Waiting for real runs from step 5b: timing the
  coach on a real model; must-hold recall as a measure waits for the private set's labels.
- 2026-10-10: rami-guzlan/Contxt#11 merged as d2251f0 (by hand with gh, all eight checks
  green), carrying step 6 (BL4 and G2): State sheets with column types, friction, age limits,
  formulas through a safe evaluator and a log per cell; the brief's "Current state" block sent
  as deltas; working contexts; the Tasks sheet and `hand_off` with evidence checked against
  recorded outputs; live context in Workspace on AG Grid, a board and a calendar; Activity's
  tasks and handoffs; outputs filed by project, row and maker. Main merged into
  `updating-loop` (657352a, no conflicts) after the step kinds commit (a419934). Waiting for
  real use from step 6: whether formulas help (kept only if proven helpful).
- 2026-10-10: rami-guzlan/Contxt#12 merged as e25e009 (by hand with gh, all eight checks
  green), carrying step 7: the updating loop (corrections and "Still true?", the exceptions
  ledger, approval health, single-source flags, independent evidence, blast radius, admins
  scaffolded), output checks that send a draft back once, blind judging and cited verification
  held by tests, the knowledge agent run by code with its tools and run records, Catch up's
  loop cards, "That's wrong" on a request, the workflow canvas on React Flow with the node
  library and a fit check, G3's task and hand-off steps and teammates as owners scaffolded.
  Main merged into `proof-and-walkthrough` (step 8; main held only the merge commit). Waiting
  for the PC from step 7: agreement with Claude Code, hand-up rates and speed per machine
  setup. Waiting for Rami: the private agent set from his Catch up decisions.
- 2026-10-10: step 8 committed as 7cb78ea on `proof-and-walkthrough` and opened as
  rami-guzlan/Contxt#13 with Auto-fix on. Checks: Python 1034 passed, web 200, typecheck,
  build, ruff, format, mypy clean; retrieval_eval unchanged (75% recall, 71% precision, 48
  cases); the report card (`report-card-2026-10-10.md`) ran 253 gate tests over nine plan
  sections with none failing. When it is green it merges by hand with gh; that is the last step
  of prompt 157. Still with Rami: the walkthrough (`walkthrough-script.md`), the real day, G4
  with his goal and the interviewees, and his sign-off.
- 2026-10-12: rami-guzlan/Contxt#13 merged as b7587b0 (by hand with gh, all eight checks
  green), carrying step 8: the drift eval, the four-week soak, the alignment tax, the report
  card script, the G4 evals (and the goal-text secret masking they found), and the rewritten
  system notes. That ends prompt 157's build. Same day, at Rami's word ("push all to github so
  I can take over dev from my PC"): `test-the-brain` committed as work in progress (3278e9a)
  and pushed, unmerged and 25 commits behind main; the plans and this record copied into the
  repo under `docs/dev/` with every reference to his work Brain rewritten, plus
  `docs/dev/HANDOFF.md` for Claude Code on the PC. Development moves to the PC.
- 2026-10-12, the PC's first session: cloned; every check passes (Python 1087 passed and 9
  skipped, web 215, typecheck, ruff, format and mypy clean, retrieval_eval unchanged, the report
  card's 253 gate tests none failing). Test the Brain had already merged as
  rami-guzlan/Contxt#16 before the move. Build step 9 (the local models on the PC's GTX 1060:
  pinned, one-command install, run without a 12 GB GPU, setups A to E measured) went to the
  `models-out-of-the-box` branch.
- 2026-10-13: Rami deferred the local models (the step 9 branch is parked), asked that nothing
  go on the C: drive, and set the direction: the rest of the architecture first with a model
  router ready for later, Workflows replaced by a Knowledge Agent on the CLI model the person
  chooses, an updated design to come (HANDOFF 7.0). On `fix-data-leaks`: the owner's goals
  (loaded manual, confidential) reached briefs when a selected note named them or carried an
  older value of a figure a goal sets, and through the engine's find step and link loop; and
  eval, replay and bench ledgers, the requests and briefs built from a Brain, stayed in the temp
  folder, as did hundreds of scratch Brains per test run. All fixed, with tests.
- 2026-10-16: an interactive map of the backend for Rami's redesign with Claude Design (kept
  private, outside the repo) turned up a silent drop: without the local engine, a selected note
  past the brief's budget, a core style rule past the style share and a file part past the file
  allowance were left out with only a log line, against the rule that nothing is silently
  omitted. On `no-silent-drops`: a note too long to come whole comes in short, one past the
  budget even in short is named under "Did not fit", a file part under "Also in your files". The
  parity check's clock is stopped at the day its briefs were kept, since a demo note stops
  being new after 14 days and the check had started failing on main by date alone. Merged as
  rami-guzlan/Contxt#20.
- 2026-10-16, `docs-match-governance`: the governance docs had fallen behind the code. They
  said every file waits and intake always waits, and they gave the personal preset's capture
  defaults as everyone's. The code files the owner's documents at once (except from a chat,
  the CLI or a folder under regulated), treats intake as a file from a chat, and starts from
  careful. Fixed in GOVERNANCE, CAPTURE, CONFIG and SUPPLY_CHAIN. Push before the model asks
  is not set up by any connect path, so at Rami's word ("I'll just tell users to add a global
  instruction to their models") `contxt connect` and Settings, AI apps now give every app one
  standing instruction to paste into its own instructions, and say where it goes. Merged as
  rami-guzlan/Contxt#21.
- 2026-10-16, `agent-any-model`: at Rami's word (the knowledge agent "should be able to connect
  to any model the user chooses defaulting to their CLI connected ai"), the agent's router in
  `models.py` takes Codex and Gemini CLI beside Claude Code, Ollama and the pinned local
  model. Any model a CLI offers can be named (`gemini:gemini-2.5-flash`). With nothing chosen,
  the first CLI here that can answer does the work. Each CLI is asked with nothing but the
  prompt: an empty folder, none of the person's MCP servers. Gemini CLI's flags were checked
  against 0.1.10 on the PC (it reads stdin only without `-p`); Codex is not installed here, so
  its `codex exec` flags follow its documentation. Checks, digests and See the difference still
  run on Claude Code only. Merged as rami-guzlan/Contxt#22.
- 2026-10-16, `door-checks`: the map's two open gaps, at Rami's word ("fix the two open gaps").
  What the app's AI work proposes carries a run, not a session, so it skipped the evidence check
  and the proposal cap. Now its quotes are checked against what the run read (the inputs on
  the run), and a run may propose 40 at most. The circular-evidence rule looked outputs up by
  file path, and the workspace names them by id; now a proposal citing a file the app's AI
  work made names that run's session, and the Brain checks it against what the run was handed.
- 2026-10-16, `hardening`: Rami asked that ingestion, distillation and retrieval be "rock solid"
  before the redesign's features are built.
  - The ingestion audit's attribution findings are fixed:
    - `brain scout`'s finds are a document's word, so their instructions are reported;
    - an exported ChatGPT or Claude history is the owner's own messages;
    - an earlier-workspace memory that was only suggested is the owner's AI's;
    - regulated always redacts what a cloud model triages.
  - Retrieval: "review" and "audit" stay among a request's words, since a code review checklist
    or an audit trail is what such a request is about. Recall on the labeled requests rose
    from 85% to 88% by meaning and from 75% to 77% by words. False nothing fell from 10% to 8%
    and from 8% to 5%. Held-out results and must-hold recall and decoys are unchanged.
  - Precision drops a point. By words alone, "Review the plumbing launch plan" now also pulls
    the investor-update rule ("Riley reviews and sends it"); by meaning it does not. Two kept
    parity briefs changed and were rewritten.
