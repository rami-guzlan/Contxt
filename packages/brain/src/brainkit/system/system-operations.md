---
id: system-operations
title: Operating commands
keywords: commands cli check health bench benchmark evaluation serve ui scout intake migrate reorganize kernel
---
`brain status` one-screen state. `check` validates the vault (front matter, ids,
areas, scopes, loads, pins, stale reviews). `context "<request>"` shows a packet (`--explain`
adds the routing trace). `propose "<text>" --area A --topic T --title "..."` proposes a note
(omit area and topic to have them suggested). `inbox` lists, approves (with `--edit
topic=...` to move it) and rejects proposals. `focus` lists, shows and updates Focus items.
`serve` starts the local review UI and JSON API. `bench` runs the context usefulness
evaluation and the behavior checks. `scout <folder>` proposes knowledge found in documents;
`intake <file>` files a source document under references/. `kernel` rewrites AGENTS.md and
the CLAUDE.md stub that imports it. `models` shows the local embedding and reranker models (`--download` fetches
the optional reranker; nothing downloads on its own). `test` runs the engine tests. `tools/reorganize.py` moves an older layer-layout
vault to areas.
