# Automatic capture

The person should never have to ask for something to be remembered, and nothing reaches the
brain's long-term memory unless the governance policy agrees. Capture is four steps, and only
the last one writes anything live.

```
notice    capture.py flags durable statements in a message      (never writes)
propose   the agent calls notes_propose / skills_propose_change / files_upload (writes a proposal)
stage     uploaded files wait in vault/.brain/staging/<id>/      (not in git)
decide    policy applies own-scope notes and skills, the owner's
          files and what the preset lets in at once, each as an
          undo point; everything else waits for the owner        (the only live write)
```

## 1. Notice

`brainkit/capture.py` is a deterministic detector. It reads a message sentence by sentence
and flags the ones that state something that will still matter later:

| Kind | Example | Tool the agent is pointed to |
|---|---|---|
| rule | "From now on, always put the event date in the first line." | `notes_propose` |
| correction | "Actually, we call them sessions, not webinars." | `notes_propose` |
| preference | "I prefer bullet summaries over long paragraphs." | `notes_propose` |
| decision | "Lena decided every proposal needs a one-page summary." | `notes_propose` |
| memory | "Remember that Jordan is on leave until October 20." | `notes_propose` |
| fact | "Our new price for the half-day workshop is $4,500." | `notes_propose` |
| procedure | "Here's how we onboard a new freelance partner: ..." | `skills_propose_change` |
| reference | "Attached is the pdf explaining the vision." | `files_upload` |

It leaves alone questions, idioms ("never mind") and instructions tied to the draft at hand
("don't use bullet points in this post", "for now"). Detection only ever produces a nudge, so
it favours precision: on 111 ordinary task requests from this brain's measurement files it
flagged one, a genuine project progress statement.

The nudge reaches the agent twice:

- **In the packet.** `gnomon_get_context` adds a `## Capture` section quoting the flagged
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
| `notes_propose` | a rule, fact, preference or decision, with the person's words in `evidence` |
| `skills_propose_change` | a new procedure, or a change to one: SKILL.md fields, body and files |
| `files_upload` | a document (filed as a reference, as Markdown that keeps its headings, slides and pages) or an asset (kept byte for byte), from a path or base64 content, with its card: what it covers, its sections, and which copy it is (`version`, `status`, `dated`). With `project`, it is filed in that project (`project_id` on its card), and a file named like one already there ("v3", "final" and dates set aside) is its new version: written over the old text in place, its card brought up to date, the earlier text kept in git. `replaces` names the file to replace directly. With `kind: prompt`, the person's own prompt is kept word for word in their own scope (`references/prompts/`), found by name and never routed unless a request names it; each file that came with it is filed with `attach_to` naming the prompt's path. The capture policy decides whether it is filed at once (an undo point) or waits |
| `projects_create` | a project: its name, one line on what it is for, and `aliases` (the names the person calls it), so requests that use one bring its state and files |
| `projects_propose_progress` | project progress: append-only, never a note |

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
| a note or skill in the proposer's own person scope | at once, logged as `auto-applied` (not under the regulated preset) |
| a note from the owner's AI in a chat, in a shared scope | by the capture policy: under personal, facts, decisions and progress at once; otherwise after the owner approves it |
| any other note or skill in a shared scope | after the owner approves it |
| the owner's document or asset (the app, a chat, the CLI, a swept folder) | at once, as an undo point; from a chat, the CLI or a folder it waits under regulated |
| anyone else's document or asset | after the owner approves it: a file is not an owner |
| what the app's AI work proposes (Find what to remember, Moving in, the knowledge agent) | after the owner approves it |
| Focus progress | at once, append-only |

The preset is `governance.preset` in brain.json: careful when none is set. The capture policy
and its conditions are in [Governance](GOVERNANCE.md).

The owner decides in the review UI (Inbox tab: file list, document preview, placement
fields) or the CLI (`brain inbox`). See [Governance](GOVERNANCE.md).

## At the door (brain-logic plan 7.1)

- **Who said it** is recorded on every new statement (`said_by`): the proposer's word when it
  gives one (a distilling model names it per statement), else where it came from: Moving in
  brings the owner's own words (instruction files and pastes are the owner's; a model's reading
  of an exported history is the owner's AI's), a file is a document, a meeting another person,
  a run an agent; else how it came: the owner in the app, the owner's AI in a chat, a document
  from a swept folder.
- **An instruction found inside content** (a document, someone else in a meeting, a synced
  system) is kept as what it is, "The document says: ...", never as a rule. The review card
  says where it came from; the owner can still make it a rule. This is the gap memory
  injection works through.
- **Evidence must be real**: a quote an AI attributes to the person is checked against the
  requests the ledger logged in that conversation (the last 200); a quote in what the app's AI
  work proposes (Find what to remember, say) is checked against what its run read, the
  inputs stored on the run. A quote that is not there marks the statement inferred, and it
  waits, with a card line saying so.
- **The circular-evidence rule**: a statement that only repeats a note from the brief an output
  was made from cannot be promoted from that output. In a chat, `outputs_save` links the file
  to its conversation (cite it as `output:<path>` in `source`); a file the app's AI work made
  links to its run; the ledger keeps what either was handed.

## Before a model reads (brain-logic plan 7.2)

- **Hash dedupe**: a capture whose text another capture already brought in and a model read,
  or that the Brain holds word for word, makes no model call; two captures with the same text
  in one request are read once. Asking again about the same capture still reads it.
- **The pre-pass** (code, free): split by speakers, headings or slides; drop boilerplate
  (recording notices, sign-offs, footers); find dates, figures and names, which the run's
  packet lists first; find sensitive spans (emails, phone numbers, card, account and ID
  numbers).
- **Redaction**: those spans are replaced (`[email]`, `[phone]`, ...) in what a cloud model
  reads of a capture in the app's AI work, on under the careful and regulated presets, off
  under personal unless turned on (`governance.redact_cloud`, a switch in Approval). The
  person always sees the text as written. Briefs from the Brain and filed documents are not
  redacted: what is filed was already let in.
- **Triage**, off until it is measured: a cheaper model (Claude Code, a local model or Ollama,
  chosen beside the model for AI work) names the parts worth distilling; only those reach the
  distilling model, and a capture with none makes no distillation call. Under a redacting
  preset a cloud model triages redacted text.
- **Distillation** proposes a statement that contradicts the Brain whether or not it serves a
  goal, and says who said each one.
- **What was left out** stays searchable (Capture, "Left out when reading"), each item scored
  again against the goals and active projects as they stand, so one left out for serving no
  goal is marked once a goal it fits appears.

## Hygiene

Automatic capture must not bury the owner in proposals:

- **Duplicates.** A proposal whose text matches a waiting proposal or a live note returns the
  existing one instead of adding another. Matching ignores case and punctuation but not
  numbers: "$4,500" and "$3,500" are different facts.
- **A budget per conversation.** `governance.max_proposals_per_session` (default 12) caps
  the proposals and decisions one session can generate; the next call is refused with
  status `limit`. A run of the app's AI work has its own cap of 40 proposals (it may read up
  to 20 captures); the next is refused with what to do instead. Moving in and bringing in the
  earlier workspace are the owner's own batches, with no cap, and everything they propose
  waits for review.
- **One skill proposal at a time.** A second proposal for a skill that already has one
  waiting points to the first.

## Drop folders and skill folders

Files that arrive outside a conversation are picked up by `sync`:

```json
"sync": {"drop": ["drop"], "skills": ["~/.claude/skills"]}
```

Paths are relative to the repository root. Every file in a drop folder goes through
`files_upload` with origin `folder` (filed at once by default, see the capture policy in
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
- `tests/test_presets.py` and `tests/test_ingestion.py`: what each preset lets in, and the
  checks at the door.

An end-to-end check with a real model in the loop (scripted conversations through `claude -p`
with the hook and the MCP server) lived in the earlier brain-kit repository and is not part of
this one yet.
