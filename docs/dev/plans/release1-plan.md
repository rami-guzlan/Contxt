# Gnomon v4 on the Contxt backend: the plan

Final plan of Oct 20, 2026. Planning only: nothing in the repository was changed.

**Read in full for this plan:**
- the v4 export (F:\contxt-dev\design\v4-full);
- the Change Log (75 entries);
- the Knowledge Agent Skills page (22 skills and the bundle, with their front matter; "How a run works"; the Code Map);
- the Feature Map;
- the Design Contracts, AGENTS.md, MCP Tools, the UI Spec and the Release 1 file;
- the master plan (the local Oct 17 revision is the one to use).

**Backend:** main at f24c811.

Supporting notes are in F:\contxt-dev\design\notes:
- backend-inventory.md
- design-summary.md

## 0. The rule this plan follows

Claude Design worked from the repository as it was at 2dc4e60. Main has 76 commits since then. Two consequences:
- **The design decides what the product does.** The Change Log is the record of those decisions.
- **The current Brain decides how it's done.** Notes in Markdown with git history, the router and its calibration, the session ledger, governance, checkpoints, the State tier and Focus projects all stay.

Where the Code Map or the UI Spec describe the older code, this plan follows main.

**Owner decisions so far (Oct 20):**
- **One tool surface.** MCP Tools.md is the surface for both the local app and a self-hosted private server. Implement those names, and keep today's names as aliases for one version.
- **One to-do list.** Project to-dos are the Brain's Tasks sheet, filtered by project. The app's task bus stays internal and is renamed "jobs".
- **Workflows become scheduled runs.** The engine stays (Release 2); only the old screens go.
- **Undo** removes a piece from the Brain and from future packets. An "ask first next time" learned from undos may switch on by itself, as long as it is visible and removable.
- **Master plan:** use the local Oct 17 revision.

## 1. What the build keeps from main (newer than the design)

The design shows none of these because they were built after its snapshot. They stay, and the new screens sit on top of them:
- **The calibrated "nothing here" bar** (`calibration.py`): per-Brain bank, evidence percentiles 0.95 and 0.90. The design's named policies (Relaxed, Standard, Careful; contract 15) become presets over these percentiles, with measured effects.
- **Scoring:** hybrid word and meaning scoring, whole and pointer tiers, passage vectors for long notes (#45) and the latency work (#46).
- **Enrichment** (`enrich.py`): "ask:" vectors for the questions a note answers.
- **The eval harness:** `general_eval`, `passage_eval`, `answer_eval`, `journey_check`, frozen cohorts, local CI.
- **The journey fixes from #44:**
  - runs whose tools fail end as failed;
  - one speaker's quote can span several lines;
  - reworded duplicate proposals are refused.

## 2. Concept by concept

| v4 concept (release) | On main today | What to do |
|---|---|---|
| Capture: paste, upload, record, hold Space (R1) | `context_items` captures with a content hash; local transcription with faster-whisper | Keep; add the source lifecycle |
| Source lifecycle: captured → analysis pending → awaiting review → accepted → indexing → searchable, plus excluded, failed, partial (R1) | Spread across the distill task, inbox proposals and the index rebuild | **Add** a source state machine |
| Scout: folders, formats, Scan now, last inspection, differences, repeats stay quiet (R1) | `sync.py` sweeps at session start, once per content hash; `brain scout`, `brain intake` | **Change**: Scan now only, through Capture |
| Distill Thread: anchors, four routing questions, left-out reasons (R1) | Distill task, prepass, `propose_brain_entry` with quote check; notes only | **Change**: typed pieces for every destination |
| Spreadsheet capture: tabs, rows, a whole tab becomes a sheet, the email column never kept (R1) | Documents are read as text | **Add** tab and row anchors, and "tab → new sheet" |
| One proposal store (prp IDs) for Capture, Catch up and the knowledge agent (R1) | Proposal files in `vault/inbox/`, batch decisions | **Change**: add the structured fields; one store |
| Edit before keep everywhere, with Goes to [store › section › row · kind] (R1) | Decisions take approve or reject only | **Add** `edited_text` and `edited_dest`; the kept version is the owner's, the original stays in history |
| In-place dots: waiting suggestions shown on cells and kept items (R1) | None | **Add** a target location on proposals |
| Catch up: stack, Safe to keep, Where they'd land, Rule changes for Sunday (R1) | `core/services/catchup.py` tiers, baseline cards | Keep the logic; re-tier it to v4 |
| Conflicts ask; no newest-wins; Mark disputed (R1) | `packets.py` places the newest dated value | **Change** (section 3.3) |
| Current value with history, Open original at the cited version (R1) | Note `as_of` / `supersedes`, State cell logs, `history.py`, object store | Keep; add a source-version viewer |
| Ask with evidence receipt (R1) | Brief plus ledger plus `brief_decisions` plus `/api/brain/requests` plus `replay.py`; no stored receipt | **Add** stored receipts and an Ask endpoint |
| Try a prompt and Watch a request (R1) | `/api/brain/preview`, `Brain.context(record=False)` | Keep; return the explained steps |
| Corrections from a receipt (R1) | "That's wrong", challenges, Still true? cards | **Add** typed corrections that only propose |
| Projects: Context, Tasks, Files, Outputs (R1); Board (R3) | Brain Focus (objective, aliases, pins, journal, files) plus workspace projects | **Change**: the Focus is the project |
| Project packet: pins, file pointers, budget, preview (R1) | Focus pins, task pins frozen in run packets | Keep; add a pin budget and named overflow |
| Kept with this project: rules, preferences, facts; references from captures (R1) | Focus journal and files | **Add** kept groups and references |
| Latest progress update and timeline; "your AI sees the last five" (R1) | `projects_propose_progress`, journal | Keep |
| "What your AIs asked" per project (R1) | Requests log | Filter receipts by project |
| Context sheets: Brain-wide and per project; send mode, updater, review, archive; cell history (R1) | State tier (typed columns, friction, cell logs, partitions) | **Change** (section 3.5) |
| Auto sheets: Project status, Open loops this week (R1) | `formulas.py` computed columns | **Add** the two built-in sheets |
| Taste profile: Looks, Feels, Works; this-not-that; words; references (R1 written; learning R2) | House-style lists; preference rules | **Add** a Taste store in the Brain; send by request type |
| Brain map regions, Long-term memory, Notes, Sheets, Files, Questions (R1) | Inventory, saved views, gaps from the ledger (`api.gaps`) | Keep; add `gaps.flag` from AIs |
| "Your AIs learned N new things", dismissible (R1) | `recap.py` | Keep |
| Knowledge agent: provider, model, sign-in health, where data goes, no switching, run any job by hand (R1) | `agent.py`, `agent_loop.py`, `kev.py`, runners for claude, codex and gemini | **Change** (section 3.7) |
| Knowledge skills (16 in R1, run by hand) (R1) | `brainkit/builtin/agent/*` procedures | **Replace** with the SKILL.md set |
| Ask the Brain first (R1) | `contxt connect` prints the instruction and the file | **Add** install and remove, with consent |
| Agent profiles: role, taste, tagged sources, instructions, packet (Agents tab, R1) | `agents.py` profiles | **Change**: add taste, sources and packet |
| Auto-governed Home and its change log; standing permission (R1) | Presets plus capture policy by origin | **Change** (section 3.6) |
| Activity: requests, cost and quality, changes and undo points, tasks (R1) | `activity.py`, `costs.py`, events, checkpoints | Keep |
| Settings: apps, approval, on this computer, test the Brain, backups, words-only search labelled (R1) | Mostly present | Keep; label words-only recall |
| States page: every state reproducible (R1) | Partial | **Add** (section 4) |
| Scheduled runs (R2) | Workflows engine | Becomes the scheduler later |
| Connected-tool search `bridge.*` (R2), taste learning (R2), goal dashboards (R2) | Partial or none | Later |
| Components, AI-built components, multiple Brains (R3); cloud sharing (Future) | None | Later |

## 3. What changes

### 3.1 The tool surface (MCP Tools.md, Release 1 subset)

Both MCP servers expose the MCP Tools.md names. Every write takes `reason`, `source` and an `idempotency_key` and returns `{id, status, undo_id?}`. Edits pass the `version` they read. Errors use the eight codes, mapped in `core/errors.py`.

**Release 1 set:** the union of AGENTS.md's live list and every Release 1 skill's look tools and writes.

| Kind | Tools |
|---|---|
| read | `gnomon.capabilities`, `gnomon.get_context`, `gnomon.inspect`, `receipts.get`, `areas.list`, `notes.search`, `notes.get`, `notes.check_known`, `rules.list`, `taste.get`, `sheets.list`, `sheets.get`, `sheets.cell_history`, `projects.list`, `projects.get`, `goals.list`, `goals.get`, `todos.list`, `files.list`, `files.open`, `captures.get`, `captures.distill`, `captures.todos`, `suggestions.list`, `changes.list`, `gaps.list`, `skills.list`, `skills.get`, `agents.list`, `agents.get`, `knowledge.skills`, `knowledge.skill`, `knowledge.map`, `knowledge.nudges`, `knowledge.gather`, `knowledge.ask`, `knowledge.impact`, `knowledge.past_decisions`, `knowledge.jobs`, `knowledge.runs`, `activity.requests`, `activity.cost` |
| suggest | `notes.propose`, `notes.propose_edit`, `notes.propose_merge`, `notes.propose_words`, `notes.challenge`, `notes.propose_archive`, `notes.propose_send_mode`, `rules.propose_change`, `taste.propose_principle`, `taste.propose_pair`, `taste.propose_words`, `taste.add_reference`, `sheets.propose_update`, `sheets.propose_row`, `projects.propose_progress`, `projects.propose_kept`, `projects.packet.propose_pin`, `projects.packet.propose_unpin`, `projects.propose_status`, `goals.propose`, `captures.apply`, `knowledge.run`, `knowledge.submit`, `gaps.flag`, `gaps.answer`, `governance.propose`, `skills.propose_change` |
| work | `captures.create`, `files.upload`, `todos.create`, `todos.update`, `outputs.save`, `outputs.list`, `skills.run` |
| admin, with the user's quoted yes | `suggestions.decide`, `changes.undo`, `governance.get`, `governance.set`, `knowledge.config.get`, `knowledge.config.set`, `projects.create`, `sheets.create`, `sheets.configure`, `agents.create`, `agents.update` |
| Later | `gnomon.route`, `gnomon.remember_route`, `brains.*`, `bridge.*`, `knowledge.schedules.*`, `goals.measure`, `goals.propose_progress`, `taste.signal` (stored only until R2), `taste.pairs.*`, `workspace.*`, `alignment.check` score |

**Today's names become aliases:**

| Today | New name |
|---|---|
| `gnomon_get_context` | `gnomon.get_context` |
| `notes_search`, `notes_get` | `notes.*` |
| `notes_propose` | `notes.propose` |
| `notes_challenge` | `notes.challenge` |
| `sheets_get` | `sheets.get` |
| `sheets_propose_update` | `sheets.propose_update` (now decided by the column's updater) |
| `todos_update` | `todos.update` |
| `projects_create` | `projects.create` |
| `projects_propose_progress` | `projects.propose_progress` |
| `outputs_save` | `outputs.save` |
| `files_upload` | `files.upload` |
| `skills_get` | `skills.get` |
| `files_open` | `files.open` |
| `skills_propose_change` | `skills.propose_change` |
| `agents_list`, `agents_get` | `agents.*` |
| app `propose_brain_entry` | `notes.propose` with source quotes |

The app's task bus tools stay internal for runners.

**Scopes:** `core/domain/policy.py` and `actors.py` map credentials to read, suggest, work and admin. The knowledge agent's runner holds read and suggest only.

### 3.2 Distill and proposals (M03)

- **Distill pieces.** `core/services/distill.py` returns pieces, not just notes. Each piece has:
  - an anchor: moment and speaker, page and section, tab and row, or message;
  - a mark: new, updates, clashes, repeats or answers;
  - a destination, decided by the four questions in order: Taste? Changes often (sheet)? One project? Still useful next month (note)?;
  - a reason;
  - what else it moves;
  - before → after;
  - whether it needs the user.
  - Every segment gets a piece or a left-out reason: small talk, only today, already known, off-goal, private or automated.
- **One store.** Every piece becomes one proposal in the Brain's inbox. The proposal file gains:
  - the source reference (capture ID, version hash, locator, speaker or "unknown", excerpt);
  - the effective date;
  - the destination;
  - the operation;
  - the target and the version it expects;
  - an idempotent operation ID;
  - a target location, for the dots.
- **No second inbox.** Capture, Catch up, the project and the knowledge agent read this one store.
- **Prepass** (`core/services/prepass.py`) adds private-detail recognizers (health, salary, family, contact numbers). Masked spans show as "left out: private".
- **What stays:**
  - the limits of 12 a conversation and 40 a run;
  - exact-duplicate refusal;
  - the near-duplicate rule from #44;
  - quote checks;
  - `_one_voice`.

### 3.3 Current values and conflicts (M04)

- **Effective-date ordering stays.** It already stops late old evidence from winning; the journey check proves it.
- **New: an explicit conflict.** Two approved values with no defined precedence become a disputed record. The packet sends both, labelled, and Catch up asks: keep current, take the new one, keep both dated, or mark disputed.
- **The current-value card** shows the current value, its source, effective date, how much it is used, the proposed replacement, and why that replacement might win.
- **Stale is not expired.** A stale value is still sent, marked stale.

### 3.4 One project (M11)

- **The Brain's Focus is the project.** The workspace project row points at it.
- **Context:** objective, latest progress and timeline, kept rules, preferences and facts, references from captures, live sheets, the packet, aliases.
- **Tasks:** the Tasks sheet, filtered by project, with stable task IDs. Edits and kept proposals update the same row, and each row links its source capture.
- **Files:** Focus files, showing their source status ("Saved isn't the same as searchable").
- **Outputs:** `outputs_save` lineage, plus the record versions read (from the receipt), plus a stale flag.
- **Packet:**
  - Order: must-holds → project brief → pins → live sheet values → notes by meaning → Taste → file pointers → gaps.
  - Pins stay under a budget share (about 30%); a pin that doesn't fit is named.
  - A packet only offers items within the project's scope.
- **Project capture** opens Distill with the project already selected. Captured pieces inherit the project's scope, which closes the client-partition gap.

### 3.5 Context sheets (M11)

- **Who keeps it current:** the State tier's column friction maps onto it (free → auto, confirm → suggest, locked → manual).
- **New settings:** scope (Brain or project), send mode, review cadence, retention and archived.
- **What is sent:** current values only. History is restorable per cell.
- **Built-in computed sheets:** Project status and Open loops this week, both from `formulas.py`.
- **"Settled values → long-term notes"** happens through `tend-sheets`, after a yes.

### 3.6 Governance (M08)

- **Two modes per Brain:**
  - Governed: everything waits in Catch up.
  - Auto: applied with undo, with a server-enforced cap of 50 a day, then a pause shown on Home.
- **The presets map onto them:**
  - personal and careful → Governed, with standing permissions;
  - regulated → a lock.
- **Standing permission** is scoped to source × area × change type, with pause and undo. It replaces the two-day auto-keep.
- **Always waits, whatever the mode:**
  - changes to must-holds;
  - rule changes;
  - changes to project status;
  - moves between Brains.
- **Approval** is a decision recorded on the server, never a flag from the client.

### 3.7 The knowledge agent (M08)

- **Runner:** the user's chosen CLI (Claude Code, Codex or Gemini) through the existing router. A local model is optional.
- **Status on the page:**
  - the model, read from the CLI's config;
  - live sign-in health, from the runner's `describe()`;
  - where data goes, named by vendor.
- **On failure it stops and says so.** It switches only to a fallback the user set, and a retry keeps the same provider.
- **Skills:** replace `brainkit/builtin/agent/*` with the handoff SKILL.md files and their front matter. `builtin.py` keeps the rule that a Brain's own version of a skill overrides the built-in. Release 1 skills, all run by hand:
  - knowledge-agent, teach, wrap-up, distill-capture, judge-clash, sort-notes;
  - check-drift, tidy-repeats, freshen-up, check-goal-fit, fill-gaps, tidy-projects, tidy-skills, tend-sheets;
  - check-alignment, as findings without a score (contract 14);
  - goals-interview, optional.
- **Run loop:**
  - `agent_loop.py` is split into `gather` and `submit` for MCP.
  - A run is held for 30 minutes, with one retry, then one candidate at a time (split mode), then handed up.
  - Every step is kept with the run.
- **Settings** hold thresholds and schedules, never prompts. The live operating prompt is built from them.
- **Gate:** `agent_eval` cases per skill (15 each) before a skill is on for a runner.

### 3.8 Scout (M03)

- **Scan now only** in Release 1. Folders and the format allowlist live in settings.
- **What it records:** the last successful inspection, and differences (new, changed, removed), with renames and saves without changes recognised by content hash.
- **Its results are captures,** which then go through Distill.
- **Watching and schedules are Release 2.**

## 4. What is added

| Addition | Where | Size |
|---|---|---|
| Source state machine, with failed, excluded, partial and retrying; migration 0010 | `core/domain/states.py`, `context_items` | M |
| "Searchable" = present in the live index generation | `brainkit/api.py` (the background recheck from #46) | S |
| Coverage per segment ("2 of 3 tabs searchable") | prepass, plus index | M |
| Typed proposals with source references, edit-before-keep, target locations | `governance.py`, inbox front matter, decisions route | L |
| Conflict records, and the current-value card | `packets.py`, `governance.py` | M |
| Stored, immutable receipts: sent, opened, didn't fit, already delivered, unknown (including captures not yet searchable), token method, scope, policy and index versions | `sessions.sqlite` beside the ledger | M |
| App Ask endpoint (the chosen CLI with only the Brain's tools), returning the answer and its receipts | `apps/server` | M |
| `gnomon.inspect` steps for Try a prompt and Watch a request | router explain mode | S |
| Typed corrections from a receipt (wrong source, wrong interpretation, out of date, not relevant, missing, cut for budget, answer ignored context), which only propose | Brain, plus route | M |
| Dependency-aware undo ("this also undoes…") | `checkpoints.py` | S |
| MCP Tools.md Release 1 surface with aliases; the eight error codes | both MCP servers, `core/errors.py` | L |
| `knowledge.gather`, `submit`, `run` and `ask`; the skill set | `agent.py`, `agent_loop.py`, `builtin.py` | L |
| Taste store (lenses, pairs, words, references); words to avoid feed `outputcheck.py` | Brain | M |
| Project kept groups, references, pin budget, project-scoped capture | `focus.py` | M |
| Sheet scope, send mode and updater; Project status and Open loops sheets | `state.py`, `formulas.py` | M |
| Spreadsheet tabs and rows as anchors; a tab becomes a new sheet | prepass, distill | M |
| Standing permissions, Auto cap, learned "ask first" from undos | `governance.py`, `loop.py` | M |
| Ask the Brain first: install and remove a marked block, show the path | connectors | S |
| Agent profiles gain taste, tagged sources and a packet | `agents.py` | S |
| Every state on the States page reproducible: empty, loading, stale, denied (file and scope), partial apply, partial coverage, retry, expired sign-in, restart recovery, words-only | server plus tests | M |
| v4 web app | `apps/web`, rebuilt | L |

## 5. What goes, and what waits

**Goes in Release 1:**
- the Workflows canvas screens;
- Prompts, and Compose's prompt improver (folds into the project later);
- old workspace tables: `work_suggestions` (unused), plus `goals`, `meetings`, `todos` behind `legacy.py` export;
- the web app's Retired routes;
- the IDEA state machine and `promote`;
- the unused approvals table;
- the REST bus (`/api/bus/*`, `/api/runs/*`);
- `/api/loop/blast`;
- the single-proposal decide route;
- the engine's own review UI (`brain serve`), once Catch up is complete;
- the built-in skills `knowledge-check` and `pull-what-matters`, which fold into distill-capture.

**Never build** (superseded by the Design Contracts):
- the alignment score;
- the two-day auto-keep;
- numeric confidence chips;
- newest-wins;
- the UI Spec's fixed thresholds (0.45, 0.6, 0.75; notes per request).

**Kept for later releases:**
- the Workflows engine, which becomes scheduled runs (R2);
- goal measures and boards (R2);
- the local model service (optional);
- `bridge.*` connected-tool search (R2);
- components and multiple Brains (R3).

## 6. Will it help? UX and retrieval precision

**Yes for real use, especially project work. Not on the gates as we measure them today.**

1. **Projects as scope: the biggest lever.**
   - A project's brief, pins, kept rules and current sheet values go first, every time, without passing the "nothing here" bar or ranking. That is where our false empties and precision misses come from.
   - Capture inheriting its project's scope also closes the client-partition gap.
   - **The catch is knowing the active project.**
     - Aliases already help.
     - Mapping a connected app's working folder to a project would help more: a Claude Code session in the Northwind repo is the Northwind project.
     - When unsure, ask once.
2. **Destination routing removes decoys.**
   - A fact that changes lives in one sheet cell with history, instead of piling up as dated notes that compete.
   - Taste and project-only rules leave the general pool.
   - **Risk:** a misrouted piece is hidden from other contexts. Mitigation: a named pointer where scope allows, and a routing eval.
3. **Pins never come back empty, but they cost precision.** They're sent even when irrelevant. Measure the deterministic part and the ranked part separately, and cap pins.
4. **Receipts and corrections give per-Brain labels** for precision on real use. They only propose changes and go to held-out validation, never to tuning.
5. **Upkeep skills** (repeats, freshen up, drift) remove decoys. The effect is modest in Release 1 because they run by hand.
6. **Honest statuses turn silent false empties into explained ones.** "Accepted isn't searchable yet" and captures listed under Unknown in the receipt explain most "it didn't find it" moments.

**What it won't fix.** A request that belongs to no project still depends on ranking. The precision, false-empty and off-topic gaps on unconfigured Brains stay until the matching itself improves (M05: compare against rank fusion on Brains it hasn't seen).

**UX concern.**
- There is a lot to learn at once: notes, records, sheets, Taste, pins, eight statuses, proposals, receipts.
- The five-step quick start helps. Show current values in one place (sheets) rather than as separate records.

**New measures, run on main first to get a baseline:**
1. Project-scoped requests: packet coverage and leaks across projects.
2. Current-value questions: dated notes versus sheet cells.
3. Distill routing accuracy on labelled captures.
4. Pin-budget behaviour.

**Gates:** existing gates unchanged. The master plan tightens false empty to 2% and adds must-hold coverage of at least 95% and decoys of at most 5%.

## 7. Design copy

**Fixed Oct 20 in F:\contxt-dev\design\v4-full (still to copy into Claude Design):**
- the knowledge agent "nothing is sent anywhere else" line;
- "ALL SIX DONE";
- the onboarding cross-project pin.

**Still open:**
- **Onboarding, "Same quality, whatever tool":** it says "checked against your taste before it reaches you". Gnomon doesn't see a connected AI's chat reply first. Suggested wording: "your AI checks it against your taste before it hands it over."
- **Minor:** the meaning model is said to be 90 MB; it is about 70 MB.
- **Name:** the product is Gnomon in the design and Contxt in the code. The CLI and settings keep `contxt` until a naming migration is chosen (master plan).

## 8. Order of work

Each step comes with its tests, local CI, and a PR merged only after a full local CI pass.

1. **M00, baseline.**
   - Freeze main, the index and model versions, the eval manifests and cohorts.
   - Run the new measures from section 6 on main.
   - Test migrations, backup and restore on copies.
2. **M01 to M04, records.**
   - Privacy (scope applies to derived items).
   - Source lifecycle and Scout through Capture.
   - Typed proposals with edit-before-keep.
   - Current values and conflicts.
3. **M05 to M07, packets.**
   - Project-scoped packet with a pin budget; named policies over the calibrated bar.
   - Session epoch.
   - Stored receipts, inspect and corrections.
   - Dependency-aware undo.
4. **M08, agents.**
   - MCP Tools.md surface with aliases.
   - Governance modes.
   - Knowledge agent provider contract and skills.
   - Ask the Brain first.
5. **M09 to M11, the v4 web app.** Screen by screen, checked row by row against the Feature Map, then the States page.
6. **Release 1 gate.**
   - The journey: capture → review (in Capture or Catch up) → accepted → indexing → searchable → ask → receipt → correct → undo, with real services.
   - The retrieval gates per Brain.
   - Onboarding and AGENTS.md claim nothing the build doesn't do.

## 9. Still needed from the owner

- **Name and license**, before anything public.
- **GitHub billing,** for hosted CI and macOS.
- **The IKN enrichment yes or no.**
