# Gnomon Knowledge Work and Brain UX: plan

Plan only: no code was changed. Written October 9, 2026 from the owner's review of the built Work tab
(branch `work-tab` in the `Contxt-safeguards` worktree, eight commits from 751d4e2 to 34f2fee,
checks green, not pushed) and the build summary that came with it. The backend logic this plan
relies on is in `brain-logic-plan.md` beside this file; its section numbers are cited as "BL".
This pass makes the screens complete and working. Visual design comes after, once everything here
exists and behaves as expected. File paths are relative to the Contxt repository. Gnomon is the
working name; the code says Contxt.

## 1. Summary

The review's direction: Gnomon is about context and alignment, not another place to run AI tools.
The Work section becomes the place where you govern and shape what your Brain knows and how it
stays current. Running skills, prompts, agents and workflows stays possible, but it is never the
headline of a screen.

| # | Feedback | What changes | Backend it needs | Phase |
| --- | --- | --- | --- | --- |
| 1 | Not "Work": the focus is alignment and context; admins later | Renamed (decision 1); the overview leads with governance; every item shows its scope | Admin roles scaffolded (BL 9, 16.8) | A |
| 2 | Compose as a simple prompt store | Prompts: saved verbatim (with files) from chat or the app, organized like other context; running is secondary | Prompts move into the Brain's Library (BL 16.2) | B |
| 3 | Workspace: native sheets, boards, calendars | Workspace splits into your docs and live context; native grid, board and calendar editors over State sheets | The State tier with column types and views (BL 8, 16.1) | D |
| 4 | Brain > Files: assets by origin; open the Library page | Files grouped by origin (skills, projects, capture sources); every file opens its Library page | Origins and one Library store (BL 16.3, 16.4) | A |
| 5 | Skills rethought | A run bar at the top; Brain skills apart with quick runs; your skills by purpose; runs in a streaming review | Skills by purpose; one stream per run (BL 16.7, 9) | C |
| 6 | Outputs organized for teams | By project by default; buckets by entity (accounts) from State; who made it and when | Outputs linked to project, State row and maker (BL 16.5) | E |
| 7 | Workflows like n8n, simpler, for context work | A canvas with a node library limited to context and knowledge work; verification with sources; connectors scaffolded | Step types that declare inputs and outputs; verification (BL 16.6, 9) | F |
| 8 | Library includes assets | Assets join references, guides and influences in the Library | One Library store (BL 16.3) | A |

## 2. Principles for this pass

- **Context and alignment first.** Every screen answers: what does the Brain hold, where did it
  come from, how current is it, what uses it, and who may change it. Running is an action on a
  screen, never its subject.
- **One item, one home, many doors.** An item lives in one place, and every other screen links to
  its page: a reference in Brain > Files opens its Library page; a prompt saved from a chat opens
  the same page as one saved in the app.
- **Structured context is State.** Sheets, boards and calendars are the State tier, so any
  connected AI reads and updates them through the same tools, and every change is logged.
- **Team-ready, solo now.** Every item shows its scope ("Yours" in the solo app); admin views come
  with the team edition.
- **Function before polish.** This pass settles structure, flows, states, empty states and
  wiring. Colors, type, spacing and motion are the next pass.

## 3. Where things live after this pass

**Sidebar**: Home, Capture, Projects, Brain, Knowledge Work (decision 1), Activity.

**Knowledge Work tabs**, in this order:

| Tab | What it is for |
| --- | --- |
| Overview | What changed, what waits for you, how healthy the context is; then flows and agents |
| Workspace | Your docs (private thinking space) and live context (sheets, boards, calendars your AIs keep current) |
| Library | Items kept whole: references, guides, influences, assets |
| Prompts | Your saved prompts, verbatim, for later (replaces Compose) |
| Skills | Procedures the Brain routes: Brain skills and your skills, with a run bar at the top |
| Agents | Roles, the context they point to, and their kernels |
| Workflows | Context work on a schedule: upkeep, refresh, verify, keep State current |
| Outputs | What was made, by project and by account or other entity |

**Brain tabs**: What it knows, Notes, Files (by origin, opening Library pages), State logs (new:
every State change with who, when and why), Questions, Knowledge agent.

**Addresses** keep `/work/...` (decision 1): links already made, the tour and tests keep working;
only the label changes. `/work/compose` redirects to `/work/prompts`.

## 4. The changes, item by item

### 4.1 Name, framing and the overview (feedback 1)

- **Name.** "Knowledge Work" (the owner's choice) with the line "Shape what your Brain knows and keep it
  current." Alternatives in decision 1.
- **Overview, re-ordered around governance**:
  1. What changed since you last looked: notes added or changed, State rows updated, Library items
     refreshed, by whom (you, an AI, a workflow).
  2. Waiting for you: workflow checks, proposals, AI-filled State cells to confirm, verification
     findings.
  3. Context health: stale notes and State cells, single-source beliefs, broken agent pointers,
     skills that may be out of date.
  4. Flows and agents: each workflow as a strip with its last result; each agent with its
     heartbeat.
  5. Recent runs, last and small.
- **Scope on every item**: a chip ("Yours" in the solo app; Company, Department, Team or Person in
  the team edition), and a scope switcher for admins that stays hidden in the solo app.
- Backend: admin roles scaffolded (BL 9).
- Done when: the overview's first screen shows changes, waits and health before any run; every
  item in Knowledge Work shows a scope chip.

### 4.2 Prompts, replacing Compose (feedback 2)

What it is: a store of your prompts, kept word for word with any files that came with them, so you
can find and reuse them later. A skill is a procedure the Brain routes by itself; a prompt is your
exact words, kept until you ask for them. The page says this in one line.

- **Ways in**:
  - From any chat: "save this prompt to my Brain" makes the AI save it verbatim, with the files
    you attached (BL 16.2).
  - In the app: write or paste one, attach files, give it a name, projects and tags.
  - From a run: save the prompt a run was given.
- **Organized like other context**: by project, kind and tag; search; versions; how often each
  was used; where it was used.
- **Ways out**: copy it; open it in a run (secondary, Claude Code by default); use it as a workflow
  step; "Make it a skill" once it is used often (the existing suggestion).
- **Kept from Compose, demoted**: "Preview what a model gets" (the assembled prompt with its token
  count) opens from a prompt's page; Improve stays as an action there.
- Backend: prompts become Library items in the Brain (person scope), saved through `files_upload` with
  a kind and inline text, found by `notes_search`, never routed into a brief unless named; the
  existing saved prompts migrate (BL 16.2).
- Done when: a prompt saved from a Claude Code chat appears in Prompts word for word with its file;
  a connected AI finds it by name; versions and projects work; a run is optional and secondary.

### 4.3 Workspace: your docs and live context (feedback 3)

Workspace gets two clearly separate groups, each with a one-line explanation:

- **Your docs**: docs, links and uploads, as built. Private thinking space until you add something
  to the Brain.
- **Live context**: sheets, boards and calendars that your AIs read and keep current. This is the
  medium-term context of the State tier (BL 8): values that change too often for review, kept
  structured, logged and current.

**Editors** (one sheet, three views; BL 8.2):

- **Sheet**: a grid with typed columns (text, number, money, date, status, person, link, a
  reference to another sheet's row), a key column, and per column: who may change it ("AIs may
  change", "ask me first", "only me"), how old a value may get, and an optional linked source. A
  row opens to its history; AI-filled cells are marked until you touch them; old values show
  their age.
- **Board**: the same sheet as a kanban, cards grouped by a status column. Dragging a card writes
  that cell, with its history.
- **Calendar**: the same sheet placed by a date column (month, week, agenda). Moving an event
  writes that cell.
- Later: a timeline for date ranges.
- **Formula columns** (decision 5): a column computed from the row's other columns, from linked
  rows and from today, with one formula for the whole column. You write it with column names and
  autocomplete, and the column header says it in plain words ("Renewal date minus today, in
  days"). Examples: days until renewal; days since last contact; days since Health was last
  updated (from the cell's history); open issues counted from a linked sheet; an owner's email
  looked up from Contacts; "At risk" when renewal is near and health is red. A summary row shows
  counts, sums and averages per column and counts by status. Computed cells are read-only and
  marked, so it is always clear what a person or an AI typed and what the sheet worked out. Not
  included: cell-by-cell formulas (`=B2*C3`), arrays, pivot tables, macros and scripts. Formulas
  stay only if they prove helpful (BL 8.2 and 8.9).

**Templates**: Accounts, Repos or Services, Standards, Content calendar, Project board, Contacts.

**Organized**: by project (default); filters by kind (docs, sheets, boards, calendars, links,
uploads); search; recently edited.

**What agents get**: the same rows through `sheets_get` and `sheets_propose_update`; a request that names an
account gets that account's row in its brief (BL 8.5).

**Open-source candidates** (licenses checked again at build time): the grid, Glide Data Grid (MIT)
or AG Grid Community (MIT); the board, dnd-kit (MIT); the calendar, FullCalendar's standard
edition (MIT) or react-big-calendar (MIT). Formulas are column formulas computed by the Brain's
engine (BL 8.2), so no spreadsheet engine is needed in the browser, and briefs and MCP tools see
the same values the screen shows.

This replaces the Work tab plan's decision 6 (sheets and calendars linked, not built); links to
outside sheets stay possible in Your docs.

- Backend: the State tier with column types and views (BL 8, 16.1); built together (section 6).
- Done when: you create a sheet from a template, edit it, see an AI's update arrive marked, drag a
  card on its board and see the cell's history, see the same rows on its calendar, add a formula
  column such as days until renewal, and get the row, computed values included, in a brief by
  naming the account.

### 4.4 Brain > Files (feedback 4)

- **Grouped by origin**: Skills (each skill's files), Projects (files filed for a project), Capture
  sources (recordings, transcripts, uploads, exports), Library uploads. Files filed before origins
  existed sit under "Origin unknown", where one can be set.
- **One page per file**: clicking a reference or an asset opens its Library page: kind, origin,
  source, versions, refresh, the original to download, and where it is used.
- Backend: origins and one Library store (BL 16.3, 16.4).
- Done when: every file shows an origin group, and every click lands on the item's Library page.

### 4.5 Skills (feedback 5)

- **Run bar at the top**, compact: a prompt box, skills picked from a dropdown (several, in order),
  where it runs (Claude Code by default; other command-line AIs later), the project, Run. No link to
  Compose.
- **Brain skills**, a section of their own: the built-in context-management skills (goals
  interview, knowledge check, pull what matters, wrap up, distill, review, health) and the
  knowledge agent's actions (find repeats, check drift, check alignment, freshen up, check
  projects, check skills, fill gaps), each with a one-click run.
- **Your skills**, grouped by purpose or category: what each is for, last used, whether it may be
  out of date, what uses it (agents, workflows), its version, and the state of its Claude Code
  copy.
- **Suggested skills** from repeated asks (exists).
- **Runs, quieter**: a small "Recent runs" drawer. Opening a run opens a review that streams the
  steps live while it runs (each tool call, what it read, what it wrote, the brief it was given)
  and replays the same transcript once it is done, then shows the result and what it proposed.
- Backend: skills told apart by purpose; one stream per run, with secrets masked (BL 16.7, 9).
- Done when: a run from the top bar with two skills streams its steps into the review as they
  happen; a finished run replays; each Brain skill runs in one click; nothing on the page leads to
  Compose.

### 4.6 Outputs (feedback 6)

- **By project** by default; inside a project, by entity wherever the Brain has a State sheet for
  that entity type (one bucket per account for an account team); then by date.
- **Each output says**: who made it (you or an agent), when, from what (a skill, a prompt, an agent,
  a workflow, a chat), for which project and which account or other entity, and the brief it was
  made from.
- **Filters**: project, entity, maker, date range, source, kind; search.
- **Team-ready**: "made by" and "for" fields; the solo app shows "You".
- Backend: outputs linked to project, State row, maker and date (BL 16.5).
- Done when: outputs group by project by default; an output linked to an account sits in that
  account's bucket; every filter narrows correctly.

### 4.7 Workflows (feedback 7)

- **A canvas**, inspired by n8n and simpler: nodes left to right, a node library at the side, a
  node's settings in a side panel when it is clicked, and each node showing its last run's input
  and output. Straight lines first; a branch on a check's result later.
- **The node library is limited to context and knowledge work**:
  - Triggers: a schedule, Run now, from any AI you allow (MCP); later, events (a capture arrives,
    a change is approved).
  - Brain upkeep: the knowledge agent's seven actions.
  - Ingestion: refresh a Library item, fetch a URL or a repository, sweep a folder.
  - Distillation: digest a capture, find what to remember.
  - State: update a sheet from a source or from a step's result.
  - Verification: check notes against the web, with citations (BL 9).
  - Human check: wait for your yes or your edit.
  - Output: a doc version, an output, proposals.
  - Connectors: a "Connect a tool" node shown as coming later, so the layout is ready for it.
- **Templates**: Weekly Brain upkeep; Verify my most-used notes each month; Refresh my Library;
  Meeting to follow-ups; Keep the Accounts sheet current from meeting digests.
- Canvas library: React Flow (MIT), decision 6.
- Backend: step types that declare inputs and outputs, verification with sources, State update
  steps (BL 16.6, 9, 8).
- Done when: a workflow is built on the canvas from the library, runs, shows each node's data; a
  verification run puts cited findings in Catch up and changes nothing by itself.

### 4.8 Library (feedback 8)

- **Kinds**: references, guides, influences and assets, in one list with a kind filter (prompts
  live in the same store but have their own tab, 4.2).
- **Item page**: kind, origin, source (a URL, a repository, an upload, a capture), versions,
  refresh schedule, the original to download, and where it is used (skills, agents, workflows,
  recent briefs).
- Backend: one Library store (BL 16.3).
- Done when: assets appear in the Library with their origin, and Brain > Files and the Library open
  the same page for the same item.

### 4.9 Agents (not in the review; a suggestion)

Lead each agent's page with alignment: its kernel (the role layer, BL 5.10) and what it points to;
then its runs. Agents get kernels the way people do, so their page should show the same thing a
person's does. Decision 7.

## 5. Phases

| Phase | Builds | Backend it needs | Done when |
| --- | --- | --- | --- |
| A. Name and structure | Rename (label only), tab order, the overview re-ordered, scope chips, Brain > Files by origin, assets in the Library, one item page | Origins and one Library store (BL phase 2; the origin field can land first) | Sections 4.1, 4.4 and 4.8 pass |
| B. Prompts | The Prompts tab replacing Compose; saving from chat; migration of saved prompts | Prompts in the Brain's Library (BL 16.2) | Section 4.2 passes |
| C. Skills | The run bar, Brain skills, your skills by purpose, the streaming run review | One stream per run (BL 9) | Section 4.5 passes |
| D. Workspace live context | Your docs and live context; grid, board and calendar editors; templates | The State tier (BL phase 4) | Section 4.3 passes |
| E. Outputs | Grouping by project and entity, makers, filters | Outputs linked to context (BL 16.5) | Section 4.6 passes |
| F. Workflows | The canvas, the node library, templates, verification and State steps | Step types, verification (BL phase 5) | Section 4.7 passes |
| G. Walkthrough | A scripted walk through every screen on the demo Brain, then a real day on the owner's live Brain | Everything above | The owner signs off; visual design starts |

Every phase: a branch from `main` in the `Contxt-safeguards` worktree (never in the live
checkout), full checks, a pull request, no auto-merge, a look on the demo Brain.

## 6. One order for both plans

1. Merge `work-tab` as built (decision 4): it is tested and green, and every later change is then
   a small branch on top of it.
2. BL phase 0 (measure), alongside UX phase A (name and structure).
3. BL phase 1 (retrieval, briefs, kernel), alongside UX phase B (prompts; it needs the Library
   kind).
4. BL phase 2 (one statement model, origins), which completes phase A's origins; then UX phase C
   (skills and the streaming review).
5. BL phase 3 (ingestion and distillation).
6. BL phase 4 (State) together with UX phases D (Workspace live context) and E (outputs).
7. BL phase 5 (updating, verification, streams) together with UX phase F (workflows).
8. BL phase 6 (proof) and UX phase G (walkthrough).
9. Visual design.

## 7. Decisions for the owner

All eight are approved (October 9, 2026): 1 to 4 and 6 to 8 as written, 5 as amended below.

1. **The section's name**: "Knowledge Work" (recommended, your words); or "Govern", "Manage",
   "Stewardship". Either way the addresses stay `/work/...`.
2. **Prompts as their own tab**, stored in the Library (recommended); or a kind inside the Library
   only.
3. **The name of Workspace's structured group**: "Live context" (recommended); or "Trackers", or
   "State".
4. **Merge `work-tab` first**, then build this in follow-up branches (recommended); or rework on
   the branch before merging.
5. **Editors** (amended): a typed grid (Glide Data Grid or AG Grid Community), a dnd-kit board and
   FullCalendar's standard edition, with simple formulas where they genuinely help: one formula
   per column plus a summary row, computed by the engine (4.3; BL 8.2). No cell-by-cell
   formulas. The owner's rule: formulas stay only if they are simple, intuitive and actually helpful,
   which the interview sketches and the eval in BL 8.9 decide.
6. **The workflow canvas on React Flow** (recommended).
7. **Agents' pages lead with their kernel and pointers** (recommended; not in your review).
8. **One streaming run review for every kind of run**: skills, prompts, agents, workflow steps
   (recommended).

## 8. Risks and limits

- **A spreadsheet product by accident.** Sheets stay typed and small, and formulas are column
  formulas only, kept if they prove helpful (decision 5); sheets hold context, not models.
- **Two prompt stores during the move.** One migration, then the old store reads only; the old
  address redirects.
- **A canvas that grows complicated.** Straight lines first, a library limited to context work,
  branches later.
- **Secrets in a streamed run.** Tool output can contain tokens and keys; known patterns are
  masked before the stream reaches a screen or a transcript (BL 9).
- **Carried over from the Work tab build, still open**: connector steps have only been tried
  against a stand-in for Claude Code; scheduled workflows run only while Contxt is open (it no
  longer starts at sign-in); grouping repeated asks by meaning needs the local model downloaded,
  and until then it matches by words.
- **Two plans, one build.** UX phase D cannot ship before the State tier, and UX phase F needs
  verification; section 6 keeps them together.
