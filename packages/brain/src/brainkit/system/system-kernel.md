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

The kernel also carries the MUST-HOLD INDEX: the domains that have must-holds (notes loaded
`domain`), each with a few words on when it comes up and its must-holds' titles and ids, so a
model knows to ask for a brief (or open those notes) before any task in them. Up to three
must-holds marked `critical` show their one line in full instead, for models that cannot ask
for a brief. The index lists only domains with must-holds and points at `topics.md` for the
rest; it is regenerated with the kernel, so marking a must-hold, retitling one or adding an
area changes the fingerprint in the same undo point.
