---
id: system-kernel
title: The kernel and startup files
keywords: kernel startup context claude.md agents.md fingerprint standing notes boot regenerate layers budget person layer session start hook
---
The kernel is the standing context every session starts with, compiled for one principal in
layers: the company's (the action policy and the company-wide standing notes, using their
`startup_text`), the role's (the standing notes of the scopes between, such as a team) and the
person's (their own standing notes), with one contract line (call `get_task_context` first,
with the fingerprint) and the must-hold index. Each layer has a token budget (brain.json
`kernel.budgets`: 150, 150 and 100 to start, 500 in all), and the health check warns when one
is over. How to work with the brain is in the MCP server's instructions and the tools'
descriptions, and the skill that fits comes with the brief.

`brain kernel` writes the shared part (the contract, the company and role layers, the index)
for the owner: `AGENTS.md` in full and `CLAUDE.md` as a stub that imports it (`@AGENTS.md`),
both rewritten after every governed change, with the fingerprint in their banner. The person's
layer never goes in a shared file: in Claude Code the session-start hook prints it once per
conversation, and otherwise the first brief carries it. `get_task_context` compares the
fingerprint a client passes and includes the current kernel when the client's copy is stale.

The kernel also carries the MUST-HOLD INDEX: the domains that have must-holds (notes loaded
`domain`), each with a few words on when it comes up and its must-holds' titles and ids, so a
model knows to ask for a brief (or open those notes) before any task in them. Up to three
must-holds marked `critical` show their one line in full instead, for models that cannot ask
for a brief. The index lists only domains with must-holds (the brief brings the rest when a
task needs it); it is regenerated with the kernel, so marking a must-hold, retitling one or
adding an area changes the fingerprint in the same undo point.
