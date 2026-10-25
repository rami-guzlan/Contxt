# MCP

Two MCP servers, for two jobs:

- **The Brain's own server** (`python -m brainkit --vault <vault> mcp`, the `packages/brain`
  engine; `uv run contxt connect` prints the setup for each AI app): what your AI apps use in
  every chat. It hands each request its context (`gnomon_get_context`), opens entries,
  files and procedures, and saves what the conversation learns (`notes_propose`, `files_upload`,
  `projects_create`, `projects_propose_progress`); `outputs_save` says what a file it saved for you was
  made from, so the app's Outputs page can show it. Each packet opens with the Brain map
  (`gnomon_map(tier)` returns one tier whole); `gnomon_open(address)` opens one part
  (`note-id#heading`, `file#section`, `lore_id#story`) within the pull budget the owner sets
  (2 items and about 1,500 tokens by default); `lore_list`, `lore_get` and `lore_propose` read
  and propose lessons; `activity_sessions_search` finds past conversations by their receipts.
  Every Claude Desktop or Claude Code window starts one; they all read and write the same Brain. See [the Brain's architecture](brain/ARCHITECTURE.md).
- **The app's endpoint** (`POST /mcp` on the server): how a model does the AI work the app
  starts (finding what to remember in a note, reconciling a clash). This page is about it.

The app's endpoint uses Streamable HTTP with JSON replies, authenticated with the model's own
bearer token. It is stateless: every request carries the token, and the server stamps the
acting identity from it. No tool takes an actor, and no parameter reaches another model's
queue.

## Tools

| Tool | What it does | Enforced by the server |
|---|---|---|
| `get_due_tasks` | Your ready tasks whose due time has come, most overdue first, plus runs you still hold | assignment, scope, due time, dependencies |
| `claim_task` | Claims one task for a lease; returns the run id and the full packet | atomic: the first valid claim wins |
| `get_task_packet` | Your run's packet, exactly as it was at claim time | read permission |
| `append_task_event` | progress, evidence, note, context_used, heartbeat (renews the lease), blocker (ends the run) | live lease, allowed types |
| `complete_task` | Ends the run, releases the lease; the task is done, or waits for review, or failed | state machine |
| `search_context` | The Brain's entries, and working material you can see, in your own words | scope and permissions; a person's notes are never found |
| `get_context_item` | Reads one pinned input (a note, a document) in full, 40,000 characters at a time (`offset` pages through a long one) | a note opens only when work assigned to you pins it |
| `get_brain_entry`, `get_brain_skill`, `get_brain_reference` | Reads one Brain entry, procedure (listed in packets as skill candidates) or reference document | Brain read permission |
| `save_digest` | Saves the digest a `digest` task asks for: a summary, key points each marked by how it fits what the Brain holds now (`new`, `repeats`, `updates`, `clashes`, with the entry), decisions, actions, open questions and people. Shown beside the item; nothing reaches the Brain from it | the run must be yours, its task a digest, and the item pinned to it |
| `save_skill_result` | Saves what a `skill` run made: a title and the whole result as Markdown (for a run that made files, each file and what it is). Shown on the skill's page; saved again in the same run, it is a new version of the same result | the run must be yours and its task a skill run |
| `propose_brain_skill` | Proposes a skill from a `skill-draft` task: a new version of one (`target`) or a new skill (`name`, `category`, `description`, `triggers`, `artifacts`, `loads`, `body`). It waits in Review beside the version it replaces; nothing changes until a person approves it | proposal only; the run must be yours and its task a draft; an improvement names the skill its task is about |
| `propose_brain_entry` | Proposes durable context; it waits for a person. Pass the `run_id` during a task and the proposal names that task. `replaces` names entries it supersedes (archived when approved), `contradicts` entries it disagrees with when the sources do not settle which is current, `topic` the area/topic it belongs in, and `revises` one entry it is a new text for (a reconcile task asks for this). `goal` and `project` say which of the owner's goals it serves and which project it belongs to (a pull task asks for them) | proposal only; the run must be yours; named entries must exist |

Every write accepts an `idempotency_key`: a retried call returns the first result; a key
reused for a different request is refused.

## The check

A connected model runs one prompt, on a schedule or when asked. The MCP prompt `worker`
returns it (also shown on Settings, AI apps, and in `config/templates/workers/worker.md`):

1. `get_due_tasks`; stop if nothing is due.
2. `claim_task` one task at a time, with `idempotency_key` `<task_id>:<due_at>`.
3. Work from the packet: purpose, instructions, pinned inputs and Brain context.
4. Answer with the tool the output contract names (`propose_brain_entry` once per
   statement, `save_digest` once for a digest, `save_skill_result` for a skill run or
   `propose_brain_skill` for a skill draft), with the run's `run_id`. The packet's Finish
   section names the call.
5. `complete_task`. A person reviews every proposal; the model never publishes or sends
   anything itself.

## Client setup

| Client | Transport | Configuration |
|---|---|---|
| Claude Code | HTTP | `claude mcp add --transport http contxt-app <url>/mcp --header "Authorization: Bearer <token>"` |
| Codex, Claude Desktop, Gemini CLI, local-model clients | stdio bridge | command `contxt`, args `mcp --url <url>/mcp`, env `CONTXT_TOKEN` |
| ChatGPT | HTTP over public HTTPS | needs the private-server profile |

Settings, AI apps, generates the exact snippet for each, with the token filled in once. Claude
Code on the same computer needs none of this to run the app's work at once: see
[Running the app's AI work](runners.md).

### The Brain by URL

The running app also serves the Brain's own tools (the same ones `brainkit mcp` serves over
stdio) at `<url>/brain/mcp`, with the same tokens. An AI app then connects by URL instead of
starting the Brain itself, so one computer left on can hold the Brain for every app on it:

- Claude Code: `claude mcp add --scope user --transport http contxt <url>/brain/mcp --header "Authorization: Bearer <token>"`
- Claude Desktop, Codex, Gemini CLI: command `contxt`, args `mcp --url <url>/brain/mcp`, env
  `CONTXT_TOKEN`.

Replies come back as JSON on each POST; there is no server-sent stream (GET answers 405).

## Protocol notes

- Protocol versions 2025-06-18, 2025-03-26 and 2024-11-05 are accepted; `structuredContent`
  is included from 2025-06-18 on.
- `GET /mcp` returns 405: replies come back on their POST; there is no server-initiated stream.
- Requests carrying an `Origin` header from a page other than the app are refused
  (DNS-rebinding protection). Add trusted origins with `CONTXT_ALLOWED_ORIGINS`.
- Tool failures come back as results with `isError: true` and a message the model can act
  on (`conflict: This task is not available to claim: it is claimed.`). A proposal the Brain
  refuses (`propose_brain_entry` or `propose_brain_skill` with status `refused`) is a failure
  too, with the proposal in `structuredContent`; a retry with the same `idempotency_key`
  (status `duplicate`) is not.
