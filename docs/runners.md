# Running the app's AI work

A few jobs in the app are work a model does: **Find what to remember** in a note (the model
reads it and proposes what will last), and **reconciling** two pieces of the Brain that clash
(the model rewrites the one that is not current). Each is a task on the app's task bus, and a
model can take it three ways:

| Way | How it starts | Good for |
|---|---|---|
| **Run now** | You click *Run now with Claude Code* beside the request. The app starts the CLI on this computer for that one task and streams its work into the page. | Work you want done now, with nothing to schedule |
| **Copy prompt** | You click *Copy prompt* and paste it into any connected model (Claude Code, Codex, Claude Desktop, ChatGPT). | Any client, any time |
| **Scheduled check** | A connected model runs its worker prompt on its own schedule and takes whatever is waiting. | Work that waits for a model |

Every way claims the same task through the same MCP tools, and what it proposes lands in the
same Review. Nothing is remembered without a person's decision.

## Set up a CLI on this computer

Settings -> AI apps -> **Run the app's AI work on this computer** shows each CLI as three
steps, with its state.

**Claude Code** (one-click runs)

1. Install it: `npm install -g @anthropic-ai/claude-code` (or Anthropic's native installer).
2. Sign in: click **Sign in to Claude Code**. The app opens a terminal running
   `claude auth login`; finish in the browser, then click **Check again**. Without a desktop
   (a server, a container), run `claude auth login` yourself; in Docker,
   `docker compose exec -it app claude auth login`. The app never sees or keeps the
   login: it only asks the CLI `claude auth status`.
3. Run: requests now show **Run now with Claude Code**.

A run acts as a Claude Code model in the app. If the request has no model yet (one waiting for
a model), it is given to your Claude Code model, or to a new "Claude Code (this computer)"
model made on first use.

**ChatGPT (Codex CLI)** (copied prompt or schedule, for now)

1. Install it: `npm install -g @openai/codex`.
2. Sign in: `codex login` (your ChatGPT account).
3. Connect it: Settings -> AI apps -> *Connect a model*, platform Codex. The page shows the MCP
   settings for `~/.codex/config.toml` once, with its token.
4. Run: paste a request's prompt into Codex, or schedule `codex exec` with the worker prompt.

One-click runs for Codex come once they are tested against a real Codex install.

## What a run can and cannot do

A run is fenced in on purpose; the app starts the CLI like this:

- in an empty temporary folder, in restricted mode (`--restricted`): none of your own Claude
  Code settings files are read, so none of your hooks run. A Claude Code from before
  `--restricted` loads project settings only (`--setting-sources project`), which the empty
  folder does not have; one with neither is refused, with how to update it
- with only this app's MCP server (`--strict-mcp-config`), named `contxt-app`
  (Claude Code reserves the name `workspace` and silently skips a server that uses it)
- with no built-in tools at all (`--tools ""`): no shell, no file reads or edits, no web; it
  may call the app's tools and nothing else, and never stops to ask (`dontAsk`)
- with a credential made for this run alone, revoked the moment the run ends; the MCP
  configuration holding it is deleted with the folder
- with no saved session (`--no-session-persistence`) and a 20-minute limit

It sees the note it was asked to read (pinned to its task) and the Brain; it cannot find or
open any other note. Only the owner can start, follow or stop runs. A run that stops before
finishing (you stopped it, it ran out of time, the CLI failed) leaves a blocker on the task
saying why, so the task does not sit claimed until its lease expires.

## Find what to remember

On a note, **Find what to remember** asks a model to read it and propose the facts, decisions
and preferences worth keeping. With no model connected yet, the request waits: the worker
gives it to the first model that can take it (the one chosen in Settings, or the only one
connected), or you can run it now, which uses this computer's Claude Code. Its suggestions wait
in Review, grouped as one batch; the note's panel shows each request and where its
suggestions stand.

## When a run does not start

| Message | What to do |
|---|---|
| not signed in | Sign in (Settings, AI apps), then *Check again* |
| its login no longer works | Claude Code says it is signed in, but its saved login failed an answer: sign in again (`claude auth login`), then *Check again* |
| cannot keep your own settings and hooks out | Update Claude Code (`npm install -g @anthropic-ai/claude-code`) |
| not installed on this computer | Install it; the app looks for it on `PATH` |
| assigned to another model | Use *Copy prompt* in that model's client, or choose this computer's model in Settings |
| only a ready task can run | The request is still being set up; try again in a moment |

The run's console shows what the CLI printed, including its errors.
