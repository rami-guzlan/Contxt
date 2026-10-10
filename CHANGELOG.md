# Changelog

## 0.1.0 (unreleased)

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
- Moving in takes files of any kind, zips included: documents, instruction files, any text,
  and ChatGPT's and Claude's data exports (their conversations as your own words); what cannot
  be read is named with why.
- Source-available under the PolyForm Shield License 1.0.0.
