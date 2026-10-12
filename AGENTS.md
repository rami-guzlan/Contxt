# AGENTS.md

Guidance for AI coding agents (Codex, Claude Code and others) working in this repository.
People: start with [README.md](README.md).

## What this is

Contxt keeps one Brain of long-term context (Markdown files in git) and connects it to every
AI app over MCP, with a local web app to see, review and steer it. Everything runs on the
person's own computer.

## If you are asked to set Contxt up

Do it step by step, and show the person each result.

1. Check the prerequisites: `git`, `uv` and Node.js 20.19 or newer (22.12 or newer to run
   the web tests).
2. `uv sync`. On Windows, "Failed to update Windows PE resources" is antivirus scanning a
   launcher uv wrote: run it again (each try gets further), or set `TMP` and `TEMP` to a
   folder inside the repository first.
3. `uv run contxt web --download` for the built web app (or, with Node.js 20.19+:
   `npm install`, then `npm run build`).
4. Ask which starter they want (`uv run contxt starters`; `empty` for their own Brain), then
   `uv run contxt setup --brain <starter>`. Setup refuses to overwrite an existing `brain/`;
   never delete or move one to get past that. Ask the person.
5. `uv run contxt connect <app>` prints how to connect their AI app. Show it to them. Adding
   it to their AI app's settings changes their configuration: ask before you run it or edit
   any settings file for them.
6. `uv run contxt serve` starts the app and prints a sign-in link. That link is the owner's
   key: tell them where to find it, but never paste it into a chat, a log or a file.
7. `uv run contxt check` confirms it all works and names the fix for anything missing. Show
   the person its output.
8. Optional: `uv run contxt models --download` (about 550 MB, local models for matching by
   meaning and for speech). Ask first.
9. Optional: `uv run brain models setup`, the local retrieval engine: its runtime and this
   computer's models, verified against the lock (no GPU is needed; about 14 GB with an NVIDIA
   GPU, about 6 GB without). Ask first, and point `BRAIN_MODEL_HOME` at a drive with room.

## Layout

```
apps/server          the HTTP API, the app's MCP endpoint, the worker and the `contxt` CLI
apps/web             the web app (React, TypeScript, Vite)
packages/core        domain and application services behind one `Workspace` facade
packages/brain       the Brain engine (`brainkit`): routing, governance, files, MCP server
packages/connectors  how each AI app connects (Brain over stdio; app work over HTTP)
brains/              starter Brains: `empty` and four made-up demos
config/templates     worker prompts for the app's AI work
docker/, compose.yaml local and private-server Docker profiles
docs/                setup, architecture, MCP, operations, decisions (ADRs), the Brain
docs/dev/            internal: the plans, the build record and the development handoff
```

A person's own Contxt lives in `brain/` (its own git repository), `data/`, `outputs/` and
`.env`, all ignored by git. Demos made by `contxt demo` live in `demos/`, also ignored.

## Commands

```bash
uv run pytest                                          # Python tests
uv run ruff check .                                    # lint
uv run ruff format --check apps packages/core packages/connectors
uv run mypy                                            # types
npm test                                               # web tests
npm run typecheck                                      # web types
npm run build                                          # the web app the server serves
```

All of them pass before a change is done. CI runs the same, plus the core on PostgreSQL
(`CONTXT_TEST_DATABASE_URL`) and a Docker smoke test.

## Rules

- The code is source-available under PolyForm Shield 1.0.0 ([LICENSE](LICENSE)). Keep the
  `Required Notice:` line at the top of LICENSE, and accept no outside contributions until a
  contributor agreement exists ([LICENSING.md](LICENSING.md)).
- Never commit `brain/`, `data/`, `outputs/`, `demos/` or `.env`. They hold a person's
  context and their sign-in key.
- Tests never read a person's real settings: the server tests clear every `CONTXT_` and
  `WORKSPACE_` variable. Never run tests with a real `.env` loaded into the environment.
- Product code never names a real organization or person. Demo content in `brains/` is
  invented, and says so in each demo's README.
- The starters are checked by the Brain's own health check in the test suite: edit their
  Markdown in `brains/<name>/vault`, keep `topics.md` lines for new topics, and run the tests.
- `packages/core` imports no web framework, model provider or Brain implementation. Every
  state change goes through `domain/states.py` and emits its event in the same transaction.
  Schema changes ship with a migration.
- Tests first: a behavior change starts with a failing test named for the behavior.
- User-facing text is plain and says what to do next.
- Names: the product is Contxt, its CLI `contxt`, its settings `CONTXT_<NAME>` (the earlier
  `WORKSPACE_<NAME>` still read). The Python packages keep their earlier internal names
  (`workspace_server`, `workspace_core`, `workspace_connectors`, `brainkit`).

## Working with a Brain while you code

If this session has a Contxt Brain connected (an MCP server named `contxt`), call its
`get_task_context` first for each task, as its instructions say. A Brain's own folder holds
generated `CLAUDE.md` and `AGENTS.md` files for agents working inside it; never edit those by
hand.
