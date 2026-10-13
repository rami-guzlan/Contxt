# Test the Brain: progress

Worktree: `C:\Users\rguzian\dev\AI-Brain\Contxt-test-the-brain`, branch `test-the-brain`, from origin/main dc4b3c0, merged with origin/main 7dc4f0e (PR #6) on 2026-10-10.
Spec: `testing-lab-plan.md` 10.1 and C.5; the build prompt is entry 170 in `rami-prompts-verbatim.md` (entry 177 is a stray "wwigg").
After any compaction: read this file, then the prompt (entry 170), then `git log` on the branch.

## Decisions made on the way

- A typed request in Watch it work runs through `Brain.context(record=False)`: it writes no ledger row at all, which is stricter than a marked row. The reserved client value is `contxt-test` and the reply carries `test: true`. No migration, no schema change.
- Built-in checks: health reads the app's own Brain (read only); the evals run on a second Brain instance with a throwaway ledger (like `brain report` already does).
- The connected Lab's folder is stored in `data/test-the-brain/settings.json` (this machine only).
- The runner's `--progress` file lives in the app's data folder (`data/test-the-brain/progress/`), so the page never writes into the Lab.
- With a Lab connected, a typed request still reads this app's own Brain (the contract has no command for it); saved Lab cases are drawn from the Lab's own record.
- Main now has `brain report` and `brain eval` (PR #6), so the built-in checks use them already. Still waiting: the retrieval engine (build step 3b: per-layer scores, why view, gate, relevance cut, second pass, machine check, Local models settings) and the Lab itself.
- The Write/Edit tools were blocked by a hook that points at the auto-created session worktree; files were written with the shell instead (user named this worktree and branch).

## Milestone 1: the contract and the runner (server) DONE (92ed94b)
- [x] Typed models for C.5 + validator, unknown `contract` refused
- [x] Stub Lab fixture (`apps/server/tests/stub_lab`), one case of each kind
- [x] Routes: status, runs, run, cases, start, cancel, progress (live), connect, disconnect, gates, compare
- [x] Runner: exe + args from the contract, no shell, cwd in the Lab, listed run kinds only, one run at a time, run lock, cleanup on cancel and stop
- [x] Security tests: allowlisted env (mutation checked), runner path inside the Lab, owner only (before the body is read), writes only start/cancel (route table)

## Milestone 2: built-in checks DONE (128f567)
- [x] health, report, eval, See the difference (paid, second press)

## Milestone 3: the page DONE (ddef27a, plus overview/watch/gate cases 8226da1)
- [x] Overview / Run / Gates / Cases / Watch it work / This computer / History
- [x] 15 web tests

## Milestone 4: Watch it work DONE
- [x] Stages left to right with counts and dots, reduced motion, waiting stages marked, typed request read only

## Milestone 5: finish
- [x] docs/test-the-brain.md
- [x] All AGENTS.md checks pass
- [ ] Screens (light, dark, phone) in `test-the-brain-screens\`: BLOCKED. The sign-in link is the owner's key and the harness denied printing it (credential rule). See the log.
- [x] Push `test-the-brain`, one PR against main: merged as rami-guzlan/Contxt#16 (6154848) on 2026-10-12, after main was merged in and the built-in checks pointed at step 3b's machine check and the engine's record (eefc181)

## Log

- 2026-10-10: Read AGENTS.md and the spec. Prompt logged as entry 170. `uv sync` fine on the retry. Merged origin/main (PR #6).
- 2026-10-10: Milestones 1 to 4 written test first and committed. Smoke test of the real demo app (port 8792, knowledge-company starter, own `brain/` and `data/` in the worktree): health, report, overview and watch work; eval says "nothing to score" because the starter has no labels, as designed.
- 2026-10-10: `uv run contxt check` showed every path inside the worktree. Server on 8792 started with CLAUDE, ANTHROPIC and MCP variables removed; its sign-in line is filtered from its log.
- 2026-10-10: Trying to print the sign-in link for the browser pane was denied by the harness. Not worked around.
