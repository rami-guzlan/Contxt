# Governance

## The policy

| Change | Needs approval? | Where it goes |
|---|---|---|
| A note in the proposer's own person scope (preferences, personal facts) | no, applies at once | `knowledge/`, logged as `auto-applied` |
| A new Focus in the proposer's own scope | no | `knowledge/projects/<slug>/` |
| Focus progress | no, append-only | `journal/focus/<id>.jsonl` |
| Company or team identity, rules, facts; another person's scope | yes | `inbox/` until the approver decides |
| A skill in the proposer's own scope | no | `skills/<category>/<name>/` |
| A skill in a shared scope | yes | `inbox/`, files staged in `.brain/staging/` |
| A document or asset from the owner (the app or the CLI), the owner's AI in a chat, or a sync folder | no by default (the capture policy below): filed at once as an undo point | `references/` (in a project: `references/projects/<project>/`) with its card in `knowledge/` |
| A document or asset from anyone else, or when the capture policy says `wait` | yes | `inbox/`, files staged in `.brain/staging/` |
| Anything found by scout or filed by intake | yes, always | `inbox/` |
| Review cadences, auto-apply rules, proposal limit, delivery detail kept, default owner | the owner, through `set_policies` (the workspace's Policies page): an undo point | `brain.json`, journal, git |
| Scopes, partitions, budgets, routing policy | owner edits `brain.json` / `routing.json` directly | git |

Change it in `brain.json` under `governance`: `auto_apply_own_scope`, `auto_apply_scopes`
(fnmatch patterns such as `dept:marketing`), `approver`, `approvers`,
`max_proposals_per_session` (default 12), `default_owner`, `review_days`, and `capture`.

**The capture policy** (`governance.capture`, set through `set_policies`) says what the
owner's own captures do, by what is captured and where it came from: `apply` (in at once,
with an undo point) or `wait` (in the review queue). Origins are `app` (the owner, in the
workspace or the CLI), `chat` (the owner's AI, in a conversation) and `folder` (a swept
folder). Defaults: files, facts, decisions and progress apply; rules, preferences,
conventions and changes to existing entries wait when an AI made them. Only what differs from
the defaults is kept in `brain.json`. Anyone else's changes to shared knowledge follow the
scope rules above and wait for the approver. Files use it today; notes follow it next. How proposals arise
without anyone asking, and how uploads are gated and staged, is in
[Automatic capture](CAPTURE.md). Where every entry came from, how it changed and where it
went is in [The context supply chain](SUPPLY_CHAIN.md).

## Reviewing and undoing

The review shows each waiting proposal with what approving it would change: the entries it
replaces or changes (side by side with the proposed text), the ones its proposer says it
contradicts, the live entries it nearly repeats without naming them (the router's own
relevance, flagged as close from 0.75), and other waiting proposals that say much the same
(a word cosine weighted by rarity, from 0.6). Proposals are grouped by the work that made
them, a distillation request for example, so a batch can be approved together; the ones with
something to settle are set apart.

Approving can name more entries the proposal replaces, move it to another topic or retitle
it, or file it in the owner's own words (edited before approving). An entry beside it can be
edited in the same batch, so two pieces that overlap can both stay. The owner can also edit or
remove (archive) any live entry from its page: an edit rewrites it in place and the journal
keeps what it said before; a removed entry leaves every packet and stays as history. The owner
can also put an earlier version back (`restore`), bring an archived entry back
(`unarchive`), and change an entry's owner, review cadence, sensitivity or place (`update`).
Each of these is an undo point.

When a proposal contradicts or nearly repeats an entry and both should stay, the owner can
reconcile them: say which one is current, and a model rewrites the other so the two stand
together without stepping on each other. The workspace runs it as a task (template
`reconcile`), one click with the Claude Code CLI on this computer or through any connected
model. The rewrite comes back as a proposal of its own (a change to the entry, or a new
version of the proposal), shown beside the pair, and approving the pair is one undo point.

Every batch of decisions is an undo point (`.brain/checkpoints/`, runtime state, never
committed). It keeps the bytes every file held before the batch changed it, including the
proposals it removed and their staged uploads. Undo puts exactly those files back and
refuses, naming what changed, when any of them changed since; the journal is never rewound,
it gains a `reverted` record per decision. An undo is itself an undo point, so undoing it
redoes the batch. The newest 200 points are kept. A batch is committed to git once, with
every decision it made in the message.

## Naming and placement

A new note gets a `title` (what it is for, in a few words), a one-line `summary`, and an id
made from the title's content words: "Lena's red lines" becomes `lenas-red-lines`. Its file
is `knowledge/<area>/<topic>/<added>-<id>.md`. A note proposed without a title gets its first
clause as one; without a kind, text that opens with never, always, avoid, must and the like
is a rule, anything else a fact.

Placement is suggested, never forced:

- Proposed without an area and topic, a note goes where it fits best: the topic whose
  description or notes match it most closely.
- Proposed into a topic that does not exist yet, it comes back with the closest existing
  topics ("company/breads is a new topic. Closest existing topics: company/menu (0.45)").
  The agent can re-propose there; the owner sees the same suggestion in the Inbox.
- The owner can change the area, topic or title while approving (the Inbox has the fields;
  the CLI takes `--edit topic=menu`). Changing a live note's area or topic later moves its
  file and keeps its dated name.

A note in a brand-new topic is still found on the next relevant request: routing scores every
note on its own and describes a topic without a topics.md line by what is filed in it.

## Freshness and confidence

Context ages. A note can say how long it stays trustworthy, and the owner keeps it honest:

| Field | Meaning |
|---|---|
| `verified` | the date someone last confirmed it (else when it was approved or added) |
| `review_days` | it becomes stale this many days after `verified` (else the policy's cadence for its area or kind, `governance.review_days`) |
| `review_by` | it becomes stale after this date |
| `confidence` | `confirmed`, `inferred`, `disputed` or `unknown` |
| `stale: true` | marked stale by hand, until verified again |

A stale note is never deleted or hidden. It ranks lower (`stale_factor`, 0.75) and every
packet that carries it says so: "(stale: not verified since 2026-03-01; verify before relying
on it)". A disputed note ranks lower too (`disputed_factor`, 0.85) and is flagged. The health
report lists the stale notes to verify.

Only the approver changes freshness, and each change is logged and committed:
`brain verify <note> [--confidence confirmed]` (verified today, no longer stale) and
`brain mark <note> stale|disputed --reason "..."`. The workspace offers the same actions on
a Brain entry. The older `review_every` field, which counted review cycles in brain-kit v1,
is not read as days.

## Deciding

- UI: `brain serve`, Inbox tab. Check the placement, edit the text if needed, then
  Approve; or Reject with a reason. The Knowledge tab browses by area and topic and edits or
  archives live notes (propose, or "Save and approve").
- CLI: `brain inbox`, `inbox show <id>`, `inbox approve <id> [--edit k=v]
  [--body-file f]`, `inbox reject <id> --reason "..."`.

An update proposal records the hash of the text it changes. If the note was edited since,
approval stops with a conflict and shows the current text, so nothing is overwritten blind.
Approving a note with `supersedes` archives the old one and links them.

## The record

Every outcome appends one line to `journal/decisions.jsonl`: action (`approved`,
`auto-applied`, `rejected`, `edited`, `restored`, `unarchived`, `updated`, `archived`,
`verified`, `marked`, `policy`, `reverted`, `redone`), who, when, the note, and for rejections
the full proposed text and the reason. A change also records the hash of the text it left and
the one it replaced, and of the file it wrote, so each version in git names the decision that
made it. With `git.auto_commit` on, each change is committed with exactly the files it
touched (a staged, unrelated change is never swept in). Nothing is pushed automatically.
Commits carry your git identity; where git has none (a fresh container, a CI runner), they
are made as `AI Brain <brain@localhost>` instead of failing.

## What an AI can and cannot do

The MCP agent profile can read context, search notes in its own words, open procedures,
references and single notes, propose notes, skills and files, record Focus updates and create
a Focus in its own scope. It cannot approve, reject, edit live shared notes, or change who it is acting as. Text
inside a proposal, a note or a document never changes that.
