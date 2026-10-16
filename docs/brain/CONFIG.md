# Configuration

Everything below lives in the vault. The engine supplies a default for every key.

## brain.json

```json
{
  "schema": 1,
  "name": "Northwind Studio Brain",
  "description": "One line shown under the kernel title.",
  "owner": "person:alex",
  "structure": {
    "scope_levels": [
      {"kind": "company", "prefix": "", "container": ""},
      {"kind": "team", "prefix": "team:", "container": "teams"},
      {"kind": "person", "prefix": "person:", "container": "people", "principal": true}
    ],
    "partition_kinds": [{"kind": "client", "prefix": "client:", "container": "clients"}],
    "areas": {
      "company":   {"label": "Company",   "order": 1, "description": "who we are, what we offer"},
      "customers": {"label": "Customers", "order": 2},
      "brand":     {"label": "Brand",     "order": 3},
      "people":    {"label": "People",    "order": 8},
      "projects":  {"label": "Projects",  "order": 9},
      "topics":    {"label": "Topics",    "order": 10}
    },
    "kinds": {
      "identity": {"order": 1, "heading": "Identity"},
      "rule":     {"order": 2, "heading": "Rules", "constraint": true},
      "fact":     {"order": 3, "heading": "Core facts"},
      "state":    {"order": 4, "heading": "Current state"},
      "focus":    {"order": 5, "heading": "Focus"}
    },
    "focus": {"area": "projects"}
  },
  "scopes": {
    "company": {"label": "Northwind"},
    "team:design": {"parent": "company"},
    "person:alex": {"parent": "team:design", "role": "Owner"}
  },
  "partitions": {"client:acme": {"owner": "person:alex"}},
  "budgets": {"kernel_tokens": 6000, "note_tokens": {"micro": 900, "standard": 2400,
              "deep": 3400, "followup": 350}, "skill_allowance": 600, "portfolio_tokens": 1200},
  "governance": {"preset": "careful", "approver": "person:alex", "auto_apply_own_scope": true,
                 "auto_apply_scopes": [], "max_proposals_per_session": 12,
                 "default_owner": "person:alex", "review_days": {"state": 30}},
  "sync": {"drop": ["drop"], "skills": []},
  "kernel": {"action_policy": "...", "extra": ["one more working rule"],
             "files": ["CLAUDE.md", "AGENTS.md"],
             "budgets": {"company": 150, "role": 150, "person": 100, "total": 500}},
  "hooks": {"push": "words"},
  "engine": {"cuts": {"gate": 0.5, "relevance": 0.5, "adds": 0.5, "contradicts": 0.7,
                      "current": 0.5, "domain": 0.5},
             "fitted": {"date": null, "eval_run": null, "models": {}},
             "floor": 0.15, "ceiling": 300, "rounds": 3},
  "sessions": {"retention_days": 90},
  "git": {"auto_commit": true}
}
```

- **Areas** are where notes are filed: the parts of the work you run (company, customers,
  brand, marketing, sales, operations), the people you work with, the projects in flight, and
  topics for reference knowledge that fits no single area. A new brain gets that set by
  default; a brain that declares its own areas has exactly those (keep `topics`: it is where
  a note goes when nothing names a better place).
- **Kinds** are how a note is used, wherever it is filed. The kernel groups standing notes by
  kind; a kind with `constraint: true` renders as "Required constraints" in packets.
- **The kernel** is compiled for a principal in layers: the company's (the action policy and
  company-wide standing notes), the role's (the scopes between, such as a team) and the
  person's (their own standing notes), with a contract line and the must-hold index. `budgets`
  sets each layer's token target (the health check warns when one is over; `kernel_tokens`
  stays the hard ceiling). `files` are written with the shared part only: AGENTS.md in full
  and CLAUDE.md as a stub that imports it (`@AGENTS.md`). The person's layer never goes in a
  file: Claude Code's session-start hook prints it, and otherwise the first brief carries it.
- **The retrieval engine** (`engine`): the cuts its gate, reranker and decision model's
  answers are held to, with the date, eval run and models they were fitted on (until then the
  values above are starting points; cuts fitted for other models give way to these defaults); the loose meaning floor of its find step; the ceiling that only
  protects speed; the link loop's rounds (three at most). `enabled: false` keeps a Brain on the
  fallback even with a model service; `layers` and `scorer` are how the comparison of setups
  runs. It runs only with a verified local model service (ROUTING.md).
- **Hooks**: `push` is how Claude Code's prompt hook sends a brief before the model asks:
  `words` (the default, about a second), `meaning` (the router exactly as `get_task_context`
  runs it, a few seconds while the model loads) or `off`.
- **Focus**: a note of kind `focus` is a project's live state. `create_focus` gives each new
  one its own folder under `focus.area`.
- `owner` is the default principal (override per process with `BRAIN_PRINCIPAL`).
- `scopes` is the inheritance tree. `alt_parents` lets a person belong to a second team; pick
  one per call with `via`.
- `auto_apply_scopes` takes fnmatch patterns, for example `"person:*"`.
- `max_proposals_per_session` caps what one conversation can propose (default 12).
- `default_owner` answers for entries that name no `owner` (default: the approver).
- `review_days` sets how often entries are re-checked, by area or kind; an entry's own
  `review_days` wins, and between its area and kind the shorter cadence does. Empty by default:
  nothing becomes due until a cadence is set.
- `sessions.retention_days` is how long the detail of each handout (request, version, why it
  was picked) is kept; daily use counts are kept for good. See
  [The context supply chain](SUPPLY_CHAIN.md).
- `sync` lists drop folders and skill folders, relative to the repository root (`~` is
  expanded); session start proposes what is new in them. See [Automatic capture](CAPTURE.md).

Older vaults declare `layers` (identity, rules, facts, state) instead of `areas`, and a
`focus` of `{"layer": "state", "topic": "focus"}`. They keep working unchanged: a layer
implies the kind of its notes. `tools/reorganize.py` moves such a vault to areas.

## topics.md

One line per topic: `area/topic: what it covers, in the words a request would use`. The
router matches requests against these lines as well as against the notes, and the health
check flags topics that have notes but no line. A project folder needs no line: its Focus
describes it.

## routing.json

| Key | Meaning |
|---|---|
| `topics` | per-topic hints: `requires_any` (dampen the topic's notes when none of these words appear), `fit_terms` (small lift when they do), `with_notes` (caveats that travel with every note of the topic) |
| `intents` | declarative rules for a kind of request; see [Routing](ROUTING.md) |
| `house_style_notes` | the core writing rules, in priority order, delivered first for every writing task |
| `house_style_topics` | the rest of the house style, delivered by relevance after the core list |
| `permission_topics` | where the standing rules that answer "may I publish" live |
| `system_skill`, `artifact_terms`, `system_phrases` | procedure for deep brain work; extra artifact and system vocabulary |
| `phrases` | multiword terms read as one word on notes and requests alike, `{"statement of work": "sow"}`; "call to action" as "cta" is built in |
| `policy` | threshold overrides (see `router.Policy`), including `rerank_weight` to switch the optional reranker on |

## Notes

`vault/knowledge/<area>/<topic>/<added>-<id>.md`. The folder says where it is filed, the file
name says when it arrived and what it is for:

```markdown
---
id: lenas-red-lines                 # what the note is for; made from the title
title: Lena's red lines
summary: No hard sells in community content, no unapproved client claims, ...
area: people
topic: lena
kind: fact                           # identity | rule | fact | decision | procedure | state | goal | focus
scope: company                       # who may see it; lives here, not in the path
status: approved                     # approved | archived (pending notes live in inbox/)
load: on-demand                      # standing notes go in the kernel
startup_text: One line for the kernel (standing notes).
added: 2026-07-23
partition: client:acme               # optional, seals the note to one client
review_by: 2027-01-01                # optional, the health check flags it when past
said_by: owner                       # optional: owner | owner-ai | person | document | system | agent
subtype: preference                  # a rule's: convention | preference
supersedes: none
source: where it came from
evidence: why it is true
---
One durable idea.
```

Old ids keep working through `aliases.json` (`{"old-id": "new-id"}`).

**One statement model** (`statements.py`, brain-logic plan 6). Every note is a statement of one
kind: identity, rule (a convention or a preference is a rule of that subtype), fact, decision,
procedure, value (filed as `state`), project (filed as `focus`) or goal. The note kinds, the
capture types the presets govern, what the workspace, distillation and the knowledge agent
propose, and the MCP and command-line choices all come from it; older words keep reading, and no
note is rewritten. Read from what a note already records, unless it says:

- **who said it** (`said_by`): from its origin (a conversation is the owner's AI, a meeting
  another person, a file a document, a run an agent);
- **when the Brain learned it** (its approval or `added`) and **when it was last confirmed**
  (`verified`);
- **when to check it again**: `review_by`, else its last check plus its kind's shelf life
  (project 30 days, value 30, goal 90, fact and procedure 180, decision, rule and identity
  365; `"statements": {"shelf_life": {"fact": 90}}` in brain.json changes any of them). The
  updating loop uses it; today's review cadence (`governance.review_days`) is unchanged;
- **its tier**: alignment (rules, identity, goals, must-holds), state (values) or knowledge.

The app's entry API shows these as `statement`. A **goal** note (goals plan 3.1) is loaded
`manual`, so it never changes what a request receives, and carries `level` (purpose, yours,
agent), `serves`, `progress`, `measure`, `due`, `cadence`, `goal_status`, `why`, `started`.

**Brief text** stays in the ledger 90 days under the personal and careful presets and 730 under
regulated, unless `sessions.retention_days` says otherwise.

A Focus is a note of kind `focus` in its own folder, `knowledge/projects/<slug>/`, with
`project`, `project_status`, a `summary` (older ones: `index_line`) and optional
`participants`, `pinned_notes`, `pinned_skills`, `aliases`, `objective` (the output it is
chasing, a sentence or two, about 60 words at most; it opens every brief in the project, the
summary standing in until it has one; a change needs a reason) and `goals` (the goals it
serves). Its progress lives in
`journal/focus/<id>.jsonl`. Notes filed beside it in the same folder (decisions, client
guidance) count as the project's own context whenever the project is named.

## Skills

`vault/skills/<category>/<name>/SKILL.md` with `name`, `description`, `when_to_use`,
`triggers`, `aliases`, `cue_terms`, `artifacts`, `loads` (topic keys and `references/...`
paths), `depends_on`, `quality_gates`, `scope`, and `invocation: explicit` for skills that
only run by name.

## Measurement files

`eval.json` (context usefulness: must, useful and noise notes per request, tuning and
held-out cases, regression floors) and `benchmark.json` (behavior checks). Both are content:
they describe this brain, so they live in the vault. See [Routing](ROUTING.md).

## Environment

| Variable | Meaning |
|---|---|
| `BRAIN_VAULT` | vault path (default `./vault` beside the engine) |
| `BRAIN_PRINCIPAL` | who this process acts as (default `owner`) |
| `BRAIN_EMBEDDINGS=0` | lexical routing only (noticeably weaker recall) |
| `BRAIN_RERANK=0` | never load the reranker, even when `policy.rerank_weight` is set |
| `BRAIN_MCP_PROFILE=full` | add read-only inspection tools to MCP |
| `BRAIN_REPO_ROOT` | where CLAUDE.md and AGENTS.md are written (default: the vault's parent) |
| `BRAIN_MODEL_HOME` | this machine's model home (default `~/.brainkit`): the downloaded local models, `settings.json` (the setup, the person's model choices, what was measured, which Kev steps qualified) and the model service's address |
| `BRAIN_MODELS_LOCK` | another lock file in place of the shipped `models.lock.json` |
| `BRAIN_MODEL_SERVICE=off` | never use a local model service (or a `http://127.0.0.1:<port>` to use that one) |

`brain models` shows the local models; `--download` fetches the optional reranker
into `vault/.brain/models`. Nothing downloads on its own. For the retrieval engine:
`brain models machine` reads this computer and shows its setup, `use <name>` makes a pinned model
the default for its role, `download <name>` and `remove <name>` fetch or drop one (verified
against the lock), `speed` times the models the service runs, `lock` lists every pin and
`serve` runs the service.
