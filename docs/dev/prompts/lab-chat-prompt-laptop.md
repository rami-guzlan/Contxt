You are building the Gnomon Lab: the test suite and testing environment for Contxt (working name Gnomon), my local context Brain. The full plan is C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\testing-lab-plan.md. Read all of it before anything else, then the companion sections its section 0 lists, and nothing else unless it points you there. The plan is the spec: follow it, and where this message and the plan differ, this message wins.

Another chat (the build chat) is implementing the brain logic plan in the Contxt repo right now, one pull request per step, which I merge by hand. You build the Lab beside it, so each suite lights up as its build step lands. The tests measure whether the Brain makes my agents' work better, more aligned and cheaper, not whether the code runs.

## My part, all of it, up front (plan 3.6)

This message is the one message the plan asks for before Phase 0:
- Section 13: all as recommended.
- My ChatGPT and Claude memory exports go in C:\Users\rguzian\dev\AI-Brain\outputs\contxt\lab-inbox\memories\chatgpt\ and ...\claude\. Copy them into the repo in Phase 5. If the inbox is still empty then, carry on: the memory rows wait for the sitting, and you tell me in the sitting message.
- You may run `claude update` once, in Phase 0, for mods (9.1).

After this, do not ask me anything until the sitting, unless going on would break a rule in plan section 3 or in the rules below. Do not send me labels, gates or reviews one at a time. Fill every queue, run `lab sitting ready`, and message me once with the list, the minutes per row, and the exact steps to start: open a Claude Code session in C:\Users\rguzian\dev\AI-Brain\contxt-lab and run /lab. While I work through it, you may build Phase 7. After the sitting, run everything without me, and batch any top-up into one ask, only for the four triggers in 3.6.

## How to work

- Work directly. Use subagents only when a job truly needs one; I'd rather save tokens.
- Build in the plan's order (section 12), and keep docs/lab-progress.md in the Lab repo: a checklist per phase and a dated log. After any compaction, read it first, then this message again.
- At the end of each phase: run its checks and `lab doctor` (the canary check), commit, push `lab-v1`, and update the progress file.
- Report honestly. A suite that cannot run yet says what it waits for. A number with a wide interval says so. A failure is shown with its output.
- Delivered text (docs, pane labels, reports, the dashboard, messages to me) has no em dashes, no en dashes, and no spaced hyphen used as a dash.

## Your session

- This session starts in my live Brain's folder. Its instructions make you call get_task_context first. Do that, and use the live Brain only for that normal read. Never propose notes, record outputs or write anything to the live Brain from Lab work.
- The Lab lives in its own new private repo at C:\Users\rguzian\dev\AI-Brain\contxt-lab (decision 1). Once Phase 0 creates it, ask the app to add it as a session folder. Work there with absolute paths.
- Never commit anything in the live Brain's repo. Its working tree has other chats' uncommitted changes; leave them alone.

## Hard rules: things that have gone wrong before

The live Brain and the build chat:
1. Never touch the live Brain except through `lab snapshot`'s read-only opens. The live Brain is:
   - the vault at C:\Users\rguzian\dev\AI-Brain\ai-brain\vault, and its .brain\ folder;
   - C:\Users\rguzian\dev\AI-Brain\workspace-data;
   - the checkout C:\Users\rguzian\dev\AI-Brain\Contxt and its .env;
   - port 8787;
   - the `contxt` and `brain` connectors, for anything but the read above.
2. Never load Contxt\.env, and never run Contxt's tests or selftest with its storage mode loaded: that writes to the live store.
3. Never touch the build chat's worktrees (Contxt-safeguards, Contxt-ux, Contxt-dev), its branches, its demo Brain on port 8790, or build-progress.md. Read build-progress.md for status; never write it.
4. Your engine is your own clone at C:\Users\rguzian\dev\AI-Brain\Contxt-lab-engine, moved only with `lab engine use <ref>`. Never edit Contxt. Anything you need from the engine goes on plan appendix B, in the progress file, for me to forward.
5. Check where the build is at each phase boundary, never on a timer:
   - read build-progress.md;
   - run `gh pr list --repo rami-guzlan/Contxt`;
   - when a step's pull request is open, run `lab compare refs` against main and put the summary in the progress file for me to attach;
   - after it merges, move your clone to origin/main and run the fast suites.

   Never poll CI or schedule checks.

This Windows laptop:
6. PowerShell here is 5.1: no `&&`. Use `;`, or `if ($?) { ... }`.
7. In Bash, never `cd` into an added session folder (for example AI-Brain\outputs). It moves the whole session's working folder. Use absolute paths. If it happens anyway, run `Set-Location` back in PowerShell.
8. Use `python`, never `python3` (that is the Store Python). Never pass Git Bash paths (/c/...) to Python. Write files with the Write tool or with a script that writes LF line endings, not with PowerShell here-strings piped into files.
9. `uv sync` can fail once on the antivirus launcher race: retry it. TLS inspection needs `truststore` in Python and `uv --native-tls`. Model downloads may hit the same inspection.
10. Before starting any long-lived server from a tool shell, strip the CLAUDE*, ANTHROPIC* and MCP_* variables from its environment. Check that the port is free, and stop every server you start.
11. Never start anything hidden or at login. The antivirus stops it, and never try to get around the antivirus.
12. A guard blocks curl with POST, PUT, DELETE or -d, `rm -rf`, and shutdown words. Do not work around it. Call the Lab app's API from Python, and delete with Remove-Item, only inside the Lab repo.
13. This laptop also runs my live app and the build chat's tests. Run heavy jobs (model downloads, offline reranker pooling, outcome runs) one at a time.

Data, GitHub and artifacts:
14. Real content from my live Brain lives only in the private contxt-lab repo, behind the secret scan:
    - never in the Contxt repo;
    - never on the dashboard, beyond ids, numbers and short titles I approved;
    - Lab code names no organization and no person;
    - roundtable material never appears in shared output (rules-attribution-101).
15. Never print a sign-in link, an owner key or a token, the Lab's own included.
16. Git:
    - push only `lab-v1`, and open one pull request at the end;
    - the repo allows no auto-merge, and I merge by hand;
    - creating the private repo and pushing `lab-v1` are covered by decisions 1, 2 and 12;
    - anything else outward-facing or irreversible needs my yes first.
17. The dashboard is a private artifact (Phase 4). If a publish is refused because a newer version exists, read the saved version it hands you in full, merge your changes onto it, and publish again. Never force.
18. Every paid run checks its cost cap first (decision 7), and plugin eval runs pass --max-cost-usd.

Facts to check, not trust:
19. The local model field is weeks old. Before pinning a model, recheck its card. Known so far:
    - Kev ships as LoRA adapters plus a pointer head on Qwen3.5 Base, for PyTorch or MLX only, with no GGUF or ONNX;
    - Qwen3-Reranker-0.6B and Qwen3.5-4B are Apache-2.0;
    - the Claude Code CLI here was 2.1.272; mods need 2.1.287 or later (desktop 2.1.286), and `claude plugin eval` needs 2.1.269. After `claude update`, mods may need a new session.
20. If `claude plugin eval` or mods are unavailable on my account, use the plan's fallbacks (6.3, 9.6) and say so in the progress file. Do not stop.

Shared files other chats also write:
21. Log every message I send you, word for word, in C:\Users\rguzian\dev\AI-Brain\outputs\contxt\build\rami-prompts-verbatim.md. Several chats write that file, and numbers have collided, so read its last entry first and take the next free number.
22. Keep the memory note contxt-testing-lab-plan current at each phase. Other chats edit MEMORY.md at the same time, so re-read it right before editing and change only your own line.

Start now: read the plan, call get_task_context, then begin Phase 0.
