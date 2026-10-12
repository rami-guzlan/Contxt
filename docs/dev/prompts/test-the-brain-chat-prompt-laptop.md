You are building one page in Contxt, my local context Brain app: Settings > Test the Brain. On it I run the Brain's tests, watch them run, and see how the Brain is doing and how it works.

## The spec

Read these in full before writing code:
- C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\testing-lab-plan.md: section 10.1 (the page), appendix C.5 (the results contract it reads), appendix B item 9, decision 13 in section 13, and section 3.1 (why the live Brain is never under test). Skim the rest of that plan only as needed: it describes the test suite this page shows.
- C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\brain-logic-plan.md: 10.4 (this page is the report card page it promised), 5.11.9 (the "why" view and the scores in the ledger), 5.11.15 (the machine check).
- C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\knowledge-work-ux-plan.md: skim it for the app's design rules and voice.
- C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\gnomon-system-map.html: the visual language for Watch it work. I love its visuals and its movement: stages left to right, counts flowing, moving dots. Bring that feel to Watch it work in the app's own components and themes, and respect reduced motion.

The plan is the spec. Where it and this message differ, this message wins.

## Where you work

- Your worktree is C:\Users\rguzian\dev\AI-Brain\Contxt-test-the-brain, on branch `test-the-brain`, made from origin/main (dc4b3c0). Its CLAUDE.md and AGENTS.md apply: read AGENTS.md first.
- The branch has no upstream on purpose. When you push, name it: `git push -u origin test-the-brain`. Never push to main or to any other branch.
- Keep a progress file at C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\test-the-brain-progress.md: a checklist per milestone and a dated log. After any compaction, read it first, then this message again.

## Two other chats are working at the same time

- **The build chat** is building the brain logic plan in its own worktree (C:\Users\rguzian\dev\AI-Brain\Contxt-safeguards) as stacked pull requests: steps 2, 3 and 3b are pushed but not merged yet.
- **A Lab chat** is building the test suite itself in a separate private repo (C:\Users\rguzian\dev\AI-Brain\contxt-lab, once it exists). It writes the results contract (C.5) that your page reads.

Neither may be disturbed:
- Never touch the build chat's worktrees (Contxt-safeguards, Contxt-ux, Contxt-dev), its branches, its demo Brain on port 8790, or build-progress.md. You may read them, and `git show origin/<branch>:<path>`, to match names and shapes. Never copy or cherry-pick their code.
- Never write in the Lab repo. To test the page with a Lab, build your own stub Lab as a test fixture (below).
- Keep your changes additive, in new files: a new route module, a new page file and its components, new tests. Touch shared files only to register them (the routes list, the one tab entry in apps/web/src/pages/Settings.tsx), with as few lines as possible. The build chat is also adding Settings tabs (Local models, Alignment), so expect a small merge there.
- Avoid a schema change. Mark a Watch it work request as a test through a field the ledger already has: the Brain's request log has a `client` column, so use a reserved client value, and leave those rows out of usage counts and evals. If a migration turns out to be unavoidable, number it after the highest on main and on every pushed branch (`git ls-tree -r --name-only origin/<branch>`), and say so in the pull request.
- Whenever origin/main moves, merge it into your branch, and wire up what just became available.

## Main does not have the build chat's steps yet

Build every part against a readiness check. A part that needs a build step not yet on main says in plain words what it waits for, for example "Waits for the retrieval engine (build step 3b)". When that step merges, it lights up, and only the adapter changes.

Already on main, so use them now:
- `brain check`;
- `brainkit/evaluate.py` and `safeguards_eval.py`;
- "See the difference" in apps/server/src/workspace_server/routes/proof.py, which answers one request with and without the Brain;
- Activity's request rows.

Not on main yet:
- step 2's `brain eval` and `brain report`;
- 3b's per-layer scores, "why" view, machine check and Local models settings;
- the Lab's results.

## Milestones (commit each one)

1. **The contract and the runner** (server).
   - Typed models for C.5 and a validator. Refuse an unknown `contract` version, with a clear message.
   - A stub Lab under the tests' fixtures: a `lab.contract.json` and a tiny runner script that writes `status.json`, `progress.jsonl` and `runs/<run>/summary.json` and `cases.jsonl`, with one case of each kind.
   - Routes for:
     - the status;
     - the runs, a run and its cases;
     - starting and cancelling a run;
     - the live progress;
     - connecting and disconnecting a Lab by its folder, stored in this app's settings on this machine.
   - Starting the runner:
     - the executable and argument list from the contract, no shell, from the Lab's folder;
     - only the run kinds the contract lists;
     - one run at a time, honoring the Lab's run lock;
     - child processes cleaned up on cancel and on server stop.
   - **Security, each with a test named for the behavior:**
     - The runner gets only an allowlisted environment: `PATH`, `SYSTEMROOT`, `TEMP`, `TMP`, `USERPROFILE`, plus the contract's `env_allow`. A test sets `CONTXT_` and `WORKSPACE_` variables in the server and shows the child sees none of them. This is the known trap: tests run with the live storage settings loaded write to the live store.
     - The runner path resolves inside the Lab folder. Any `..` or absolute escape is refused.
     - Only the owner can see or use any of it.
     - The page writes nothing but starting and cancelling runs: no approvals, gates or labels.
2. **Built-in checks**, for when no Lab is connected. Every Contxt user can test their own Brain with what main has (`brain check`, the evals above, See the difference), written into the same contract shape in the app's own data folder. `brain eval`, `brain report` and the machine check join when they merge.
3. **The page**, as one new tab in Settings, "Test the Brain", with the seven tabs in 10.1:
   - Overview;
   - Run, streaming live, with cancel, and a second press for paid runs;
   - Gates, read only;
   - Cases, one view per kind, with a table view for the rest;
   - Watch it work;
   - This computer;
   - History, comparing any two runs.

   User-facing text is plain and says what to do next, like the rest of the app ("Catch up", "Moving in").
4. **Watch it work.** A case or a typed request, drawn stage by stage with its counts in and out and its time, in the System Map's visual language.
   - Until 3b merges, draw the stages main can show and mark the rest as waiting.
   - A typed request runs read only, with the test marker.
5. **Finish.**
   - Docs at docs/test-the-brain.md: what the page does, and the contract any runner can follow.
   - Every check in AGENTS.md's Commands passes.
   - Screens in light and dark, and at phone width, saved to C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\test-the-brain-screens\.
   - Then push and open one pull request against main. Say in it what works now and what waits for which build step.
   - I merge by hand after CI. There is no auto-merge; never poll CI or schedule checks. Do not update my live app: tell me when it is ready.

## Running it while you build

- Run the app from your worktree only, with its own `brain/` and `data/`. Use a demo Brain (`uv run contxt demo` or a starter), never my live Brain.
- Before you serve, run `uv run contxt check` and confirm every path it shows is inside your worktree, not C:\Users\rguzian\dev\AI-Brain\ai-brain or ...\workspace-data. If the CLI reaches for another home, stop and tell me.
- Serve on port 8792. Check that it is free first, and stop every server you start.
- The serve command prints a sign-in link, which is the owner's key. Use it only to open the app in your browser pane; never write it into chat, a log or a file.

## Hard rules: things that have gone wrong before

1. Never touch my live app or live Brain:
   - the checkout C:\Users\rguzian\dev\AI-Brain\Contxt and its .env;
   - port 8787;
   - C:\Users\rguzian\dev\AI-Brain\ai-brain\vault;
   - C:\Users\rguzian\dev\AI-Brain\workspace-data.
2. Never load any .env into a shell you run tests from. AGENTS.md says the server tests clear `CONTXT_` and `WORKSPACE_` variables; keep it that way for your tests.
3. PowerShell here is 5.1: no `&&`. Use `;`, or `if ($?) { ... }`.
4. In Bash, never `cd` into an added session folder such as AI-Brain\outputs. It moves the whole session's working folder. Use absolute paths, and if it happens, run `Set-Location` back in PowerShell.
5. Use `python`, never `python3`. Never pass Git Bash paths (/c/...) to Python.
6. `uv sync` can fail on the antivirus launcher race: run it again. Company TLS inspection needs `uv --native-tls` and `truststore` for Python. If npm fails on TLS, tell me; never turn certificate checks off.
7. Before starting a long-lived server from a tool shell, strip the CLAUDE*, ANTHROPIC* and MCP_* variables from its environment.
8. Never start anything hidden or at login. The antivirus stops it, and never try to get around the antivirus.
9. A guard blocks curl with POST, PUT, DELETE or -d, `rm -rf`, and shutdown words. Do not work around it: call the API from Python or from the page, and delete with Remove-Item inside your worktree only.
10. Never commit `brain/`, `data/`, `outputs/`, `demos/` or `.env`. Product code names no organization or person, and demo content stays invented.
11. Delivered text (UI copy, docs, the pull request, messages to me) has no em dashes, no en dashes, and no spaced hyphen used as a dash.
12. Work directly. Use subagents only when a job truly needs one; I'd rather save tokens.
13. Log every message I send you, word for word, in C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\rami-prompts-verbatim.md. Several chats write that file and numbers have collided, so read its last entry first and take the next free number.
14. Report honestly. A part that waits says so. A failing check is shown with its output.

Do not ask me anything until the pull request is open, unless going on would break one of these rules. Start now: read AGENTS.md and the spec, then milestone 1, tests first.
