# Automatic capture

The person should never have to ask for something to be remembered, and nothing reaches the
brain's long-term memory unless the governance policy agrees. Capture is four steps, and only
the last one writes anything live.

```
notice    capture.py flags durable statements in a message      (never writes)
propose   the agent calls propose_note / propose_skill / add_file (writes a proposal)
stage     uploaded files wait in vault/.brain/staging/<id>/      (not in git)
decide    policy applies own-scope notes and skills at once;
          everything shared, and every file, waits for the owner  (the only live write)
```

## 1. Notice

`brainkit/capture.py` is a deterministic detector. It reads a message sentence by sentence
and flags the ones that state something that will still matter later:

| Kind | Example | Tool the agent is pointed to |
|---|---|---|
| rule | "From now on, always put the event date in the first line." | `propose_note` |
| correction | "Actually, we call them sessions, not webinars." | `propose_note` |
| preference | "I prefer bullet summaries over long paragraphs." | `propose_note` |
| decision | "Lena decided every proposal needs a one-page summary." | `propose_note` |
| memory | "Remember that Jordan is on leave until October 20." | `propose_note` |
| fact | "Our new price for the half-day workshop is $4,500." | `propose_note` |
| procedure | "Here's how we onboard a new freelance partner: ..." | `propose_skill` |
| reference | "Attached is the pdf explaining the vision." | `add_file` |

It leaves alone questions, idioms ("never mind") and instructions tied to the draft at hand
("don't use bullet points in this post", "for now"). Detection only ever produces a nudge, so
it favours precision: on 111 ordinary task requests from this brain's measurement files it
flagged one, a genuine project progress statement.

The nudge reaches the agent twice:

- **In the packet.** `get_task_context` adds a `## Capture` section quoting the flagged
  sentences and naming the tool for each (not for exact note or skill lookups, or Focus
  updates, which are captures already).
- **On the raw message.** In Claude Code, the `UserPromptSubmit` hook
  (`hooks/capture_prompt.py`) adds the same nudge as context before the model sees the
  message. It is silent when nothing is flagged and never fails the prompt. The same hook
  pushes the brain's brief for a message that asks for something, when the brain holds
  something the conversation was not given (ROUTING.md, "Push").

The MCP server's instructions carry the standing instruction: capture as you go, without
being asked; one-off instructions need no capture.

## 2. Propose

| Tool | What it proposes |
|---|---|
| `propose_note` | a rule, fact, preference or decision, with the person's words in `evidence` |
| `propose_skill` | a new procedure, or a change to one: SKILL.md fields, body and files |
| `add_file` | a document (filed as a reference, as Markdown that keeps its headings, slides and pages) or an asset (kept byte for byte), from a path or base64 content, with its card: what it covers, its sections, and which copy it is (`version`, `status`, `dated`). With `project`, it is filed in that project (`project_id` on its card), and a file named like one already there ("v3", "final" and dates set aside) is its new version: written over the old text in place, its card brought up to date, the earlier text kept in git. `replaces` names the file to replace directly. With `kind: prompt`, the person's own prompt is kept word for word in their own scope (`references/prompts/`), found by name and never routed unless a request names it; each file that came with it is filed with `attach_to` naming the prompt's path. The capture policy decides whether it is filed at once (an undo point) or waits |
| `create_focus` | a project: its name, one line on what it is for, and `aliases` (the names the person calls it), so requests that use one bring its state and files |
| `record_focus_update` | project progress: append-only, never a note |

Each call carries the conversation's `session_id`, so every proposal and decision records
where it came from.

## 3. Stage

Files never touch `knowledge/`, `skills/`, `references/`, `assets/` or git history until
they are approved. An upload waits in `vault/.brain/staging/<proposal id>/` with a manifest;
the inbox file holds the reviewable text and the file list. Approval moves the files into
place and commits them; rejection deletes the staging folder.

Before anything is staged, an upload passes these gates:

- relative paths only, no `..`, drive letters or absolute paths;
- a name deny-list: keys, certificates, credentials, environment files, databases, `.git`,
  `.ssh`, `private`, `.brain`;
- a type allowlist (documents, media, fonts, data, and for skills also scripts and templates);
- at most 10 MB per file, 25 MB and 50 files per proposal;
- a content hash, so a file already filed or already waiting is not proposed twice;
- the sensitivity-label check for documents.

## 4. Decide

| Proposal | Applies |
|---|---|
| a note or skill in the proposer's own person scope | at once, logged as `auto-applied` |
| a note or skill in any shared scope | after the owner approves it |
| a document or asset, in any scope | after the owner approves it: a file is not an owner |
| Focus progress | at once, append-only |

The owner decides in the review UI (Inbox tab: file list, document preview, placement
fields) or the CLI (`brain inbox`). See [Governance](GOVERNANCE.md).

## Hygiene

Automatic capture must not bury the owner in proposals:

- **Duplicates.** A proposal whose text matches a waiting proposal or a live note returns the
  existing one instead of adding another. Matching ignores case and punctuation but not
  numbers: "$4,500" and "$3,500" are different facts.
- **A budget per conversation.** `governance.max_proposals_per_session` (default 12) caps
  the proposals and decisions one session can generate; the next call is refused with
  status `limit`.
- **One skill proposal at a time.** A second proposal for a skill that already has one
  waiting points to the first.

## Drop folders and skill folders

Files that arrive outside a conversation are picked up by `sync`:

```json
"sync": {"drop": ["drop"], "skills": ["~/.claude/skills"]}
```

Paths are relative to the repository root. Every file in a drop folder goes through
`add_file` with origin `folder` (filed at once by default, see the capture policy in
[Governance](GOVERNANCE.md)); every skill folder (one with a `SKILL.md`) becomes a `skill.create` or
`skill.update` proposal when its contents change. Sync never moves or deletes anything: it
remembers content hashes in `vault/.brain/sync.json`, so a file is proposed once, and a
refused file is not retried until it changes.

Sync runs at session start (`hooks/session_start.py`), from the UI (Knowledge tab, "Sweep
drop folder"), and from the CLI:

```bash
brain sync --dry-run
brain add-file path/to/brand-guide.pdf --topic brand/visual-identity
brain add-file path/to/brand-guide-v2.md --replaces references/brand-guide.md
brain propose-skill path/to/skill-folder
```

## Verifying it

- `tests/test_capture.py`: detection on durable statements and one-off requests, including
  phrasings from real chats that an earlier version missed.
- `tests/test_uploads.py`: staging, gates, approval and rejection, duplicates, the session
  budget, the packet's Capture section, the hook, and sync.
- `tools/capture_check.py`: an end-to-end check with a real model in the loop. It copies the
  vault to a sandbox, runs scripted conversations through `claude -p` with the hook and the
  MCP server, and checks what each one proposed. It needs a signed-in Claude Code CLI.

```bash
python tools/capture_check.py
python tools/capture_check.py --only standing-rule --keep
```
