# Contributing

Thank you for helping. Until the contributor agreement exists (see [LICENSING.md](LICENSING.md)),
outside pull requests cannot be merged; issues and discussion are welcome.

## Setup

```bash
uv sync                        # Python 3.12+ workspace with dev tools
npm install                    # web app (apps/web), Node.js 20.19+
uv run pytest                  # Python tests
npm test --workspace apps/web  # web tests, Node.js 22.12+ (Vitest's own minimum)
```

On Windows, if `uv sync` fails with "Failed to update Windows PE resources", security software
is blocking the console-script launchers uv writes into the temp folder; run it from
PowerShell, or point `TMP`/`TEMP` at a folder inside the repository.

## How we work

- **Tests first.** A behavior change starts with a failing test that describes it in plain
  words (`test_an_expired_lease_frees_the_task_and_fences_the_old_run`). Fix the code, not the
  test, unless the test was wrong.
- **The core stays pure.** `packages/core` imports no web framework, model provider or Brain
  implementation. Adapters (REST, MCP, CLI, worker) call the `Workspace` facade and translate;
  they never hold business rules. What the core needs from outside is a protocol in `ports.py`.
- **Every state change is one transaction with its event.** Use `Tx.update` (optimistic
  concurrency) and `Tx.emit`; never write a status without going through the state machines
  in `domain/states.py`.
- **Identity comes from the credential.** Service methods take the authenticated `Principal`
  first; never accept an actor id from a client as the actor.
- **Schema changes ship with a migration.** Edit `db/schema.py`, then generate a revision
  (`uv run python -m workspace_core.db.revise "what changed"`) and review it by hand. A test
  fails if the migrations and the schema disagree.
- **Quality gates.** `uv run ruff check .`, `uv run ruff format --check apps packages/core
  packages/connectors`, `uv run mypy`, `npm run typecheck` and every test pass before a merge.
  CI runs the same commands.
- **Starter Brains are content, checked like code.** Edit the Markdown in `brains/<name>/vault`;
  the test suite runs the Brain's health check on every starter. Demo content is invented and
  never names a real organization or person.

## Writing

Code comments and docs explain why, in plain sentences. User-facing messages say what
happened and what to do next ("Assign the task to a model or person first."), never just
an error code.
