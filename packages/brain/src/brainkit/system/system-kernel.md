---
id: system-kernel
title: The kernel and startup files
keywords: kernel startup context claude.md agents.md fingerprint standing notes boot regenerate
---
The kernel is the standing context every session starts with: identity, rules and core facts
(standing notes, using their `startup_text`), the action policy and the retrieval contract.
It is rendered for the owner into `CLAUDE.md` and `AGENTS.md` by `brain kernel`, and
rewritten automatically after every governed change. Its fingerprint is printed in the file;
`get_task_context` compares the fingerprint a client passes and includes the current kernel
when the client's copy is stale.
