# The context supply chain

Context moves through a brain the way goods move through a supply chain. Each stage is
recorded, so any entry can be traced back to where it came from and forward to where it went.

| Stage | What it covers | Recorded in |
|---|---|---|
| Sources | conversations, files and drop folders, notes, AI work, a person | `origin` on the entry, `source` and `evidence` |
| Intake | proposals waiting for review | `inbox/`, with proposer, conversation and time |
| Review | approve, edit, reject, with the review checks | `journal/decisions.jsonl`, git, undo points |
| Stock | live entries, skills, filed documents | the files; owner, cadence, sensitivity in front matter |
| Delivery | packets, opened entries, skills, references | the session ledger (`.brain/sessions.sqlite`) |
| Use | conversations and AI work an entry went to | the session ledger, by day and in detail |
| Feedback | verify, mark stale or disputed, gaps | the journal; gaps from the ledger |
| Retirement | archive, merge, supersede | the journal and git |

Nothing here changes routing. It records what routing and governance already do, and gives
the owner the tools to act on it.

## What an entry carries

In its front matter (governed, in git):

| Field | Meaning |
|---|---|
| `origin` | where it came from, `<kind>:<reference>`: `conversation:<session>`, `file:<path>`, `meeting:<id>`, `output:<id>`, `work:<run>`, `doc:<id>` |
| `owner` | who answers for it (a scope such as `person:alex`); else `governance.default_owner`, else the approver |
| `review_days`, `review_by` | its own review cadence or date (else the policy's, below) |
| `classification` | `public`, `internal` (default), `confidential` or `restricted` |
| `revised` | when its text last changed (a new title or place does not count) |

A proposal made in a conversation records that conversation as its origin. Older entries say
where they came from only in free text (`source`); the inventory reads their origin from it
(`inventory.origin_of`), so nothing is rewritten.

## Versions and putting one back (`history.py`)

Every version of an entry comes from git: each commit that changed its file, followed through
renames, so an entry moved to another topic keeps its past. A working copy not committed yet
(a hand edit, or `git.auto_commit` off) is the newest version. Without git, the versions are
the file and the earlier texts the journal kept.

Each journal record of a change now carries the hash of the file it left (`file_hash`) and of
the text (`hash`, `previous_hash`), so every version names the decision that made it: who,
when, why, which proposal and which undo point.

The owner can, each as a decision with an undo point (`governance.decide`):

- `restore` an earlier version: its text, title, summary, kind and load come back; its place,
  owner and checks stay as they are now;
- `unarchive` an archived or merged entry (whatever replaced it stays live; the result says
  so);
- `update` its details: owner, review cadence or date, classification, area and topic (a move
  takes its file along);
- `verify` and `mark` it, so a bulk check is one undo point too.

## Use (`sessions.py`)

Every handout is counted by day in `usage_daily`: how many conversations got the item, and
how (in a packet, opened afterwards, or in AI work the workspace ran). The counts are never
pruned. The detail behind them, each delivery with the version handed out, why routing picked
it (its placement and the words it shares with the request) and the request itself, is kept
for `sessions.retention_days` (90 by default).

AI work the app runs (finding what to remember in a note, reconciling a clash) is counted
under the session `work:<run id>` (`Brain.record_use`), and the entry's Use names that work.

## Gaps

`Brain.gaps(days)` lists the requests the brain served poorly:

- **nothing**: a packet that brought no entry (with the entries it named as closest, if any);
- **searched**: an entry a conversation opened that none of its packets brought or listed, so
  the AI found it some other way. That is a routing miss: the entry's title or summary lacks
  the words people ask with.

A gap that does not matter (an off-topic question) can be dismissed.

## Flow

`Brain.flow(days)` sums up the period: what came in, what was approved or rejected, what
waits (and the oldest wait), the conversations and AI work served, the entries and tokens
handed out, the packets that brought nothing, and the stock's health (live entries, due for a
check, disputed, unused for 60 days, the tokens standing entries cost every conversation).

## Policy

`Brain.policies()` reads, and `Brain.set_policies(changes)` changes (owner only, one undo
point, journal action `policy`), these settings in `brain.json`:

| Setting | Where | Default |
|---|---|---|
| `review_days` | `governance.review_days`, by area or kind (`{"state": 30}`); between an entry's area and kind the shorter wins; an entry's own `review_days` wins over both | none |
| `default_owner` | `governance.default_owner` | the approver |
| `auto_apply_own_scope`, `auto_apply_scopes` | `governance` | true, none |
| `max_proposals_per_session` | `governance` | 12 |
| `retention_days` | `sessions.retention_days` | 90 |

Setting a cadence makes entries due once they pass it, and a due entry ranks lower until it is
verified again: nothing becomes due until a cadence is set.

## Built for more people later

Every entry has an owner and every event names who did it. An entry that needs an update is
marked so, with what to check (`mark`, state stale), and stays flagged until someone confirms
or changes it; approvers live in policy. Accounts for other people, approvers per area and
notifications come later; none of them needs the record to change.
