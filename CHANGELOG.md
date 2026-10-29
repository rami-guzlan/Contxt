# Changelog

## Unreleased

- The Brain's MCP server lists three tools instead of 15: `context`, `brain(action)` and
  `propose(kind)`. Every connected app now loads about 780 tokens for them, down from about
  6,600. `brain(action: "help")` has the details, and every earlier tool name still answers.
- The startup context is sent once: not at all when the app loaded the startup file that
  carries it.
- Packets are shorter. A later message in a conversation no longer repeats how to continue.
  An edit gets no list of other notes. The other notes listed carry shorter summaries.
  `briefs.pointers` in brain.json caps how many are listed (no cap by default).
- In Claude Code, the prompt hook files a rule, preference or decision you state as a
  proposal for review, with no model call. It no longer reminds the model to call the Brain
  on every message.

## 0.1.0 (2026-10-28)

The first release of Contxt: one Brain for every AI you use, on your own computer.

- The `contxt` command: `setup`, `serve`, `connect`, `check`, `web`, `demo`, `starters`,
  `models`, and the app's operations (`backup`, `restore`, `migrate`, `token`, `status`,
  `add-model`).
- Starter Brains: an empty one, and four invented demos (a knowledge company, a programmer,
  an entrepreneur, a personal life).
- Connect Claude Code, Claude Desktop, Codex, Cursor or any MCP app to the Brain over stdio,
  with the exact command or settings block for each.
- The web app, named for the person's questions: Home (one line on how you are doing, a health
  ring, what the Brain is for, the next steps, three pictures, your AI apps, ask your Brain, see
  the difference), Capture, Projects, Brain (what it knows, notes, files, questions it could not
  answer), Work, Activity (what each AI asked and got; changes and undo points),
  Catch up and Settings, in light or dark. "+ Add" talks, records, uploads or writes.
- Catch up: a plan, never a pile. Handled for you, quick groups kept with one tap, decisions one
  at a time with a recommendation and its reason, upkeep in small weekly doses, offers to decide
  once, and a recap first after time away. Keys and swipes; every change can be undone.
- Presets for what waits for you (Personal, Careful, Regulated), with the table by kind and
  source behind Advanced. A Brain without one is Careful.
- Goals: a guided interview (typed, or talked with Space) on what the Brain is for. Everything
  brought in is summarized and sifted against the goals and the active projects; what is left
  out is listed, one tap from pulled anyway.
- Skills every Brain comes with: pull what matters (the knowledge agent), knowledge check,
  teach, wrap up and the goals interview, with buttons in Capture and on the Brain's files.
- Moving in: bring what ChatGPT, Claude, Cursor and instruction files already know; watch it
  split, checked against the Brain, flagged for private detail and sifted against the goals.
- The first run: a welcome, the goals interview, moving in, connecting an AI app (with "Add it
  for me", after a yes) until its first request arrives, a before and after, and a preset.
- See the difference: the same request answered with and without the Brain, side by side, each
  difference linked to the note behind it; the demos keep pairs of their own.
- Outputs: the outputs folder in the app, with downloads, folders, move and rename, and what each
  file was made from (a skill run, an export, or the chat that saved it, via `record_output`).
- `contxt serve` opens the app signed in the first time.
- Backups from Settings (back up now, download); a Brain backup keeps the original files.
- A change whose git save fails says so, and Home and `brain_health` show it until the next
  change saves it. Windows Brains allow long paths.
- Local models for matching by meaning and for speech to text, downloaded on request (in
  Settings, On this computer, too). Nothing downloads on its own: a Brain, its MCP server
  included, matches by words until you ask (`BRAIN_LOCAL_MODELS=0` lets it fetch on first
  use).
- Must-holds (`load: domain`): a rule that goes first into every brief whenever its domain
  comes up (its trigger words, an area the request reaches, its topics, or, with a model, its
  meaning), outside the note budget, in every packet of a conversation, flagged when stale.
  The startup context lists the domains that have must-holds with their titles and ids; up to
  three critical ones show their line in full. Set on a note's page ("When does this apply?"),
  offered in Catch up for rules that read like safety, health, legal, privacy or money lines,
  and proposed by the knowledge agent. In the demo Brains they take constraint recall on
  requests that never name the rule from 47% to 100% (`docs/evals/`).
- The baseline check: every note proposal is read against the notes it may disagree with,
  by words, figures, names and polarity at once, and by the owner's own AI (Claude Code, no
  tools) in the background. Nothing goes in on its own over a note it may disagree with or
  over a baseline (a rule, a must-hold, a standing note, a note you confirmed or AIs use a
  lot); what went in and the AI then reads as disagreeing comes back in Catch up with one tap
  to take it back. Revising a baseline takes a reason, kept in the journal, and a rule or a
  must-hold shows what it reaches first; a day to think is one setting away. Catch up adds
  "Changes a baseline" cards, a plain word after a run of quick yeses, "Still right?" spot
  checks, and Home shows how many approvals were taken back within a month.
- Dated values: a note can say the day a changing value was true (`as_of`) and the last day
  it holds (`valid_until`). A brief carries the newest of two dated values for the same thing,
  labelled "as of", and lists the older ones as older values, never as current; a question
  about a project gets the project's newest dated values too. A newer dated value is an
  update, not a disagreement, and Catch up offers to retire the older one. Past its last day,
  a note is flagged for a check. The knowledge agent dates the figures it proposes.
- Run contracts: every AI work run the app starts carries a contract (its objective, checks,
  must-holds, scope and budget) that opens its prompt; Claude Code's own hooks, from a
  settings file made for the run, refuse what is out of scope or over budget, bring the
  contract back as the run goes (and a must-hold's line as soon as its domain shows up), and
  send back a run that never finished; the app's MCP replies repeat the contract's line; the
  run's record keeps what the hooks did.
- Dissent: any AI can challenge a note with its evidence (`challenge_note`, and
  `propose_challenge` for the app's AI work); accepted, the note is disputed and keeps the
  challenge as its other view, which planning and decision work sees; turned down, it does
  not come back on the same evidence. A weekly cross-check, on by default, reads your most used
  notes and oldest baselines against the rest of the Brain (and lets your own AI read three
  pairs a week): one belief to look at, at most, each week. An external challenger, offered
  and off until you turn it on, argues against a few beliefs once a week with the web as its
  only extra tool, blind to the Brain's own view of them.
- Safeguard evaluations (`scripts/safeguards_eval.py`): must-hold recall with decoys and
  held-out requests, disagreement detection on labeled and held-out pairs (with your own
  AI's verdicts, `--ask-model`), false alarms on the demo Brains, dated values, and seeded
  wrong beliefs for the cross-check.
- The knowledge agent keeps the Brain accurate, tidy and aimed at your goals. Code makes a
  map of the Brain (every live note with the flags upkeep cares about, the goals, projects and
  skills) and gathers the candidates for seven actions: find repeats, check drift, check
  alignment, freshen up, check projects, check skills and fill gaps. Each follows a procedure
  that ships with Contxt, so any model can do the work without guessing: Claude Code by default,
  or a small local model through Ollama, which reads a shorter map. Its answers become
  suggestions in Catch up and questions with one-tap answers (still true, retire it, mark it
  disputed, answer it); nothing changes without you. It has its own tab in Brain, a strip above
  the Brain's map, a side panel for talking to it on every page, and suggestions at the bottom
  right as the Brain changes, made by code without a model.
- Home's flashcards: what to keep an eye on, one card at a time (stale context, repeats,
  drift, gaps, quiet projects, the agent's questions and what it did), and what is coming.
- Knowledge Work (first called Work), where you shape what your Brain knows and keep it
  current: Overview, Workspace, Library, Prompts, Skills, Agents, Workflows and Outputs, in one
  tab (the addresses stay `/work/...`). Everything in it reads from the Brain, and what it makes
  waits for your yes: drafts, outputs and suggestions, never anything sent or published. Every
  item says whose it is ("Yours" in this app; scopes for teams come later).
  - Overview, governance first: what changed in your Brain since you last looked and who changed
    it (you, your AI, a workflow); what waits for you (Catch up, checks in workflows, new skills);
    how healthy the context is (notes to recheck or flagged, possible duplicates, clashes, skills
    that may be out of date, agents whose pointers broke); then each workflow as a strip of boxes
    and arrows and your agents with their heartbeats; and last, small, the recent runs.
  - Prompts: your own prompts, kept word for word in the Brain's Library with the files that
    came with them, in your own scope, with every version, tags, a project and how often each
    ran. Keep one here, or from any chat ("save this prompt to my Brain": `add_file` with kind
    `prompt`); any AI connected to the Brain finds one by its name, and no brief carries one
    unasked. A prompt's page copies its words, shows its earlier versions and its files, makes
    it a skill, and, secondary, runs it: pick skills in order, an agent, notes and documents,
    see the whole prompt a model gets with its size (or a short version for any AI), improve
    it, run it here or schedule it. Prompts saved before move in once, with their versions;
    the old Compose links open a new prompt with what they picked.
  - Workspace: where you think first. Docs from a template (outline, plan, decision, progress
    update) or blank, links to the calendar or sheet you work from, and files brought in as
    docs, each linked to any number of projects without copying. Your AI drafts from a doc with a
    skill or an agent, pushes back on it (questions only) or continues it, only when you ask;
    what it makes becomes the doc's next version, its end, or a new doc. Docs leave as Markdown
    or Word. Each project's page has its own Workspace section; Capture stays the inbox.
  - Agents: roles written like a job description and kept in the Brain (`agents/<name>/AGENT.md`),
    pointing to the skills, library documents and areas they need, never copies. Your AI writes
    the operating prompt from the form; `get_agent` assembles it with every pointer as it is now;
    ask an agent for something, or add it to Claude Code as a subagent that always fetches the
    current version.
  - Workflows: steps run as one thing, on a schedule, with a button, or from any AI you open
    them to (`list_workflows`, `run_workflow`). A step is a skill, an agent, a prompt, a
    connector step (named, read-only tools of your own connectors, on Claude Code), a Brain
    upkeep job or your check, where the run waits for a yes, your edit or a stop. Each step reads
    what the one before made; a run missed while the app was off runs once, and says so. Four
    templates; a workflow goes out and comes back as a file. Checks count in Catch up.
  - Library: everything kept whole, in one place: guides to follow, references to read whole,
    influences to borrow from and assets (images, fonts, sheets, kept byte for byte), from an
    upload, a page fetched by its address or a GitHub repository's snapshot, refreshed by hand,
    weekly or monthly. Each item has one page, which Brain > Files opens too, saying where it
    came from.
  - Skills: bring one in from a zip, a folder or GitHub; take it out as a zip; copy it into
    Claude Code with a stamp of the version, and see how far behind the copy is. Each skill says
    when it was edited and used, what uses it and what it loads that changed since; asks your AIs
    got again and again with no skill to follow, alike by meaning, are offered as skills to
    write.
- Activity: each request opens to every piece it got and what it opened after, and to the
  exact text it was handed and the startup context when that went with it.
- Where each file came from: every document and asset filed says so on its card (a capture
  such as a recording or a transcript, the Library, a project, a run, Moving in, your upload,
  an AI in a conversation, a swept folder). Brain > Files groups files by it; a file filed
  before reads "Origin unknown" until you set one on its page.
- Measuring the Brain: what context costs each day on five lines (fixed overhead, briefs, the
  re-reads of briefs on later turns, rewrites after pauses, background jobs), in tokens and
  dollars at list prices, exact for Claude Code sessions when you let it read the token counts
  in Claude Code's transcripts, and estimated elsewhere; background calls the app makes record
  what they used; `contxt tokens calibrate` measures the Brain's token estimates against
  Claude's own counts. Every brief records its kind of request (lookup, writing, planning,
  code, status, edit, standard). Label your real requests from Activity (needed, helped, noise,
  should have had) into a private eval set kept beside your Brain, with a quarter held out;
  the report card (`contxt report`, `brain report`, Activity's Cost and quality tab) shows the
  cost by line, brief sizes by kind and how well briefs carry what a task needs. `brain replay`
  rebuilds logged briefs against the Brain now, at a git commit, or with a waiting proposal
  applied in a copy, and shows what would enter, leave or move.
- Briefs say what may direct the model: must-holds and your rules direct it, notes inform it,
  and quotes from your files are information, never instructions. The task opens with the
  project's objective when the request works in one (its summary until it has one), and says
  the rules outrank the task. The first few notes come whole and the rest in short (title,
  summary, the closest sentence), opened when needed; a deep brief repeats its must-holds at
  its end. Notes that match a request strongly by meaning stand on their own, and a document's
  parts are found with a line naming the document.
- The startup context is compiled for each person in layers: the company's, a team's or role's,
  and their own, each with a token budget (500 in all to start) the health check watches. Its
  how-to and the skills list moved out (the tools and briefs carry them), so it is much
  shorter. AGENTS.md holds the shared layers and CLAUDE.md imports it; your own layer never
  goes in a shared file: Claude Code's session-start hook brings it, and other apps get it with
  the first brief.
- In Claude Code, the brief comes before the model asks: the prompt hook sends it for each
  message when the Brain holds something the conversation was not given, under a session id
  the hooks share with the model's own calls, so nothing comes twice (`hooks.push`: words by
  default, meaning, or off). After a compaction the conversation is given what it lost.
- The local retrieval engine, for machines that run small models (a PC with an NVIDIA GPU or an
  Apple Silicon Mac): a gate that lets a request get nothing, a wide find with no count cap, a
  relevance cut by a local reranker, a second pass by a decision model (adds anything,
  contradicts, current, must-hold domains), a link loop, and pointers instead of drops.
  Must-holds bypass it. Every decision's scores are kept, and Activity shows why each note went
  in and why others stayed out. Models are pinned in a lock file with checksums and served by
  one local service on 127.0.0.1; anything unlisted is refused. Without verified models,
  retrieval runs exactly as before (checked byte for byte on the eval sets) and health says so.
  Label a request as one that should get nothing; the eval counts correct nothing and false
  nothing. `scripts/engine_compare.py` compares setups A to E.
- Machine setups and model settings: the app reads the computer and picks a setup (laptop,
  workstation, large, or under 16 GB) with a default model per role. Settings, On this computer,
  Local models shows each role's pinned options with their size, RAM and speed here; download
  one (verified against the lock), make it the default (refused with the reason when it will
  not fit in RAM), remove it, or check the computer again. Kev-0.8B runs a step only once it
  qualified on the machine; until then Settings and Activity name each fallback. The knowledge
  agent gets a local option (Qwen3.5-4B through the same model service, its answers bound to a
  schema), and Claude Code becomes its opt-in once a local agent model is here.
- One statement model: every note is a statement of one kind (identity, rule with its
  convention and preference subtypes, fact, decision, procedure, value, project, goal), and the
  kind lists that used to disagree (note kinds, capture types, what the workspace, distillation
  and the knowledge agent propose) all come from it. A preference from the workspace is now
  kept as a rule of that subtype and waits like every rule (it was filed as a fact). Each note
  says who said it, when the Brain learned it, when it was last confirmed, when to check it
  again (a shelf life by kind) and its tier; no note is rewritten, and briefs are unchanged.
- Goals and objectives: a `goal` kind (purpose, yours or an agent's; never routed into a
  request), and a project `objective` that opens every brief in the project (a change needs a
  reason). What models read says "run" for the app's runs, so "task" means one thing.
- Ingestion and distillation: who said each statement is recorded at the door; an instruction
  found inside a document or said by someone else is kept as what it says, never as your rule;
  a quote an AI says you said is checked against the conversation; an output cannot be evidence
  for the notes in its own brief. Before any model reads, text read before or already held is
  skipped, boilerplate goes, dates, figures and names are found by code, and private details
  are hidden from cloud models under the careful and regulated presets. Triage by a cheaper
  model is ready behind a switch. Distillation keeps contradictions whatever the goals, and
  what it left out is searchable and scored again against the goals.
- Brief text is kept 730 days under the regulated preset (90 under the others), unless set.
- Skills: a run bar at the top (what you need, several skills in order, where it runs, the
  project), each run reviewed as it happens and replayed when done with the brief it was
  given, the Brain's own skills and the knowledge agent's actions one click each, your skills
  by purpose (last used, may be out of date, what uses them, version, Claude Code copy), and a
  quiet drawer of recent runs. Every run's stream is kept on disk with credentials masked.
- Moving in takes files of any kind, zips included: documents, instruction files, any text,
  and ChatGPT's and Claude's data exports (their conversations as your own words); what cannot
  be read is named with why.
- The redesigned app, Gnomon: Home with the heartbeat bar, the Brain as regions of a real
  brain, Catch up, Capture, Projects, Agents, Activity and Settings. It is the same product and
  the same `contxt` command.
- Auto by default: your AI keeps the Brain itself. Every change is an undo point with its
  reason, and it pauses itself at 50 changes a day. Must-holds, private notes, sealed projects,
  proposed lessons, and anything customer-facing or that spends still wait for you.
- The heartbeat: on a schedule, Claude Code reads the connectors already set up in your CLIs.
  It is read-only and never sends, posts or spends. It updates the live status of each region
  and project. n8n on this computer can read your apps with no tokens. Onboarding reads what
  Claude Code, Codex and Gemini already keep on you.
- Learning: beats only stage what they find. A nightly distill nets the day's changes, checks
  them against your goal and filters, and files each one into short-term sheets or long-term
  notes, or sends it to Catch up, with a reason. Live sheets can apply during the day.
- Connectors, the same for every source:
  - one setup from found to on in the app: signed in, read-only check, a test read showing
    items, tokens and cost, then your goal, filters and how often;
  - `contxt connectors check` runs the same check from the terminal;
  - a Sign in button with the right steps for each source, and "Check again";
  - a sign-in that expires during a beat becomes a Catch up card;
  - a read loads only that connector's tools, waits for slow account connectors, is capped in
    turns and cost, and fails rather than coming back quietly empty;
  - connectors that are off fold into a short "Found, off" list.
- Context sheets live in SQLite, with their history as monthly text files in the Brain's git.
- Grouped MCP tools: one tool per area with an `action` (for example
  `notes(action: "search" | "get" | "related" | ...)`). The old names still work.
- The startup context: a short map of the Brain and operating rules any model can follow,
  sent once per session, with diffs after that.
- The Brain as a world:
  - relationships between notes (supersedes, belongs to, cites, mentions, conflicts with, and
    links you keep through proposals);
  - a timeline with "what changed since";
  - a short world overview kept after each distill;
  - the World page, with lessons placed where they were learned and "since my last visit".
- The Test bench (Brain › Test bench):
  - Brain versions as git tags, with diff and restore;
  - the packet by section with why each item was chosen, with include and exclude;
  - no brain, full brain and custom side by side on the same model;
  - saved tests and suites in the Brain folder, scored by you or a Haiku grader;
  - suites rerun after each distill, with a "Quality dropped" card and roll back.
- Retrieval:
  - the top note goes whole and runners-up go as pointers;
  - must-holds measured against the best match;
  - must-hold scopes ("applies when / not when") kept through Catch up;
  - close calls sent as one-line pointers;
  - an answer-recall eval that counts what reached the AI by the end of its answer.
  Fuller packets are in the code and off by default: they raised recall but not correct
  answers (`docs/evals/packet-fill-2026-10-27.md`).
- Tasks is where AI work happens in a project:
  - Work with AI on Claude Code, Codex CLI or Gemini CLI with the model you choose;
  - workflows of up to 10 steps, each on its own AI, handing work on through Outputs;
  - a yes gate before anything is sent outside, plus budgets and retry;
  - orchestrators, and a timeline of what each step did and cost.
  The project Board is gone.
- What it costs (`docs/costs.md`), on Haiku:
  - a typical day with three connectors is about 1.6M tokens, $0.10 to $0.25;
  - a light day is about $0.06, and a heavy one about $0.60;
  - connectors are read every 4 hours by default, backing off to 12 hours when nothing is new;
  - a beat with nothing due costs nothing, and a read with nothing new stops early.
- `contxt web --download` fetches the built web app from this repository's release.
- Source-available under the PolyForm Shield License 1.0.0.
