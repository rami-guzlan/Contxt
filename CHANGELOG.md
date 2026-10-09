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
  answer), Skills, Outputs, Activity (what each AI asked and got; changes and undo points),
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
- Safeguard evaluations (`scripts/safeguards_eval.py`): must-hold recall with decoys and
  held-out requests, disagreement detection on labeled and held-out pairs (with your own
  AI's verdicts, `--ask-model`), false alarms on the demo Brains, and dated values.
- Source-available under the PolyForm Shield License 1.0.0.
