# Architecture

## Two zones

| Zone | Where | Changes by |
|---|---|---|
| Engine | `packages/brain` (`src/brainkit`, `tests`) | code review; must keep tests, the usefulness evaluation and the behavior checks green |
| Content | `vault/` | governance: proposals, owner decisions, append-only journals |

The engine never names an organization, product or person. Everything specific to this brain
(scopes, topics, routing cues, skills, budgets, the action policy) is vault data, so the
same engine runs a marketing brain, a design studio (see `tests/fixture.py`) or a personal
workspace.

## Modules

```
api.py          Brain: the one API every adapter calls; freshness; kernel writes; git commits
config.py       brain.json, topics.md, routing.json, aliases.json, skill categories
vault.py        read the vault into a Snapshot (cached per file); write notes, proposals, journals
model.py        Note (area/topic, kind, title, summary), Focus, FocusUpdate, Skill, Reference
scopes.py       scope chains and sealed partitions; admission
index.py        in-memory BM25 over notes, skills and topic descriptions; cached embeddings
router.py       request signals, intents, Focus naming, note-first selection, skills -> Route
packets.py      budgets, session deduplication, rendering -> Packet
engine.py       the local retrieval engine: gate, wide find, relevance cut, second pass, link
                loop, fit; the audit of every decision; fallback
modellock.py    the pinned local models (models.lock.json), verified file by file
modelservice.py the local model service on 127.0.0.1: each model loaded once, shared
models_client.py finding and trusting the service; the rerank and System One adapters
kernel.py       standing context compiled per principal in layers; AGENTS.md, CLAUDE.md stub
sessions.py     SQLite session ledger: packets and deliveries per conversation; daily use
                counts kept for good; gaps (requests served poorly)
governance.py   proposals, policy, approve, reject, supersede, edit, restore, unarchive,
                update, verify, mark, decision log, budgets
checkpoints.py  undo points: a batch of decisions taken back as a unit
history.py      an entry's versions (from git) and the governed events that made them
inventory.py    the stock as one table: details, origin, owner, changes and use
review.py       what approving a proposal would change; twins and misplaced text
capture.py      notice durable statements in a message; the Capture nudge
uploads.py      skill and file proposals: gates, staging, apply, discard
sync.py         drop folders and skill folders -> proposals, once per content hash
focus.py        Focus lookup, append-only updates, creation
health.py       vault validation and status
importers.py    scout (folder to pending proposals) and intake (document to reference)
systemdocs.py   engine documentation delivered for questions about the brain itself
mcp_server.py   MCP over stdio (agent and full tool profiles)
http_server.py  loopback JSON API and the review UI in ui/index.html
evaluate.py     context usefulness: must/useful/noise notes per request, held-out cases
bench.py        behavior checks: the kind of packet each request gets
runtime.py      engine version and code hash, so a long-lived server knows it is stale
gitops.py       commit exactly the files a governed change touched
```

## A request, end to end

```
gnomon_get_context(request, session_id)
  -> Brain.state()          fingerprint the vault from directory listings (~40 ms, once
                            per request); rebuild Snapshot + Index if anything changed
  -> Brain.caller()         scope chain for the principal, partition chain if one is active
  -> Router.route()         signals -> exact / portfolio / system / named Focus / standard
                            standard: skill candidates -> declared domains -> every
                            admitted note scored on its own, plus topic, domain, fit and
                            freshness evidence -> house style, intents, caveats ->
                            selection, related list, or lean
  -> packets.build()        Focus and pins, house style, selected notes within the budget,
                            session dedup, render with titles
  -> kernel.compile()       the shared part when the client's fingerprint is stale; the
                            person's layer once per conversation
  -> Ledger.record()        packet and deliveries, for dedup and follow-up continuity
```

## State and storage

| What | Where | Durable | In git |
|---|---|---|---|
| Notes, skills, references | `vault/knowledge`, `vault/skills`, `vault/references` | yes | yes |
| Pending proposals | `vault/inbox/*.md` | yes | yes |
| Focus progress | `vault/journal/focus/*.jsonl` (append-only) | yes | yes |
| Governance decisions | `vault/journal/decisions.jsonl` (append-only) | yes | yes |
| Session receipts | `vault/journal/sessions/*.md` | yes | yes |
| Session ledger | `vault/.brain/sessions.sqlite` | pruned after retention | no |
| Embedding vectors, model files | `vault/.brain/` | cache | no |
| Uploads waiting for review | `vault/.brain/staging/<proposal id>/` | until decided | no |
| Sync memory (content hashes) | `vault/.brain/sync.json` | yes | no |
| Index | memory only | rebuilt on change | no |

Deleting `vault/.brain/` loses deduplication history, cached vectors, the files of
pending uploads (their inbox entries then fail to apply and can be rejected) and sync
memory (sync proposes the drop folders again), nothing else.

## Invariants

1. Files are the truth and git is the history. There is exactly one writer per file kind:
   governance writes notes and the decision log, `focus.py` appends journals, the kernel
   writer owns CLAUDE.md and AGENTS.md.
2. Admission before relevance. Scope, status and partition filter candidates before any
   score is computed; no score can widen access.
3. An AI proposes and a human approves. The MCP surface has no approve or reject tool, and
   approval requires the configured approver principal. Capture detection only nudges; it
   never writes.
4. Journals and the decision log are append-only.
5. Every packet is explainable (`--explain`, the UI's Context tab).
6. Nothing is silently omitted: a body is withheld only when the same session already holds
   the same text, and the packet says so. What the budget cannot carry is named instead: a
   note under "Did not fit", a part of a file under "Also in your files".
7. Where a note is filed never decides whether it can be found: every admitted note is scored
   on its own, so new knowledge in a new topic is used on the next relevant request.
