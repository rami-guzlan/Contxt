# What Gnomon costs a day

Gnomon spends model tokens on a handful of kinds of work. This page gives what each one cost
when it was measured, what a light, typical and heavy day add up to, and the settings that
change it.

Background work runs on Claude Haiku 5.5 through Claude Code by default (the ingest model,
`--model haiku`). Its list prices are $0.10 per million input tokens, $0.50 per million output
tokens, $0.01 per million cached tokens read and $0.20 per million written to the one-hour
cache. On a Claude plan the tokens count against the plan's usage instead of costing dollars,
so this page gives both.

## What each piece of work costs

Measured on October 28, 2026 on the entrepreneur demo Brain, unless it says otherwise.

| Work | When | Tokens | Cost |
|---|---|---|---|
| Claude Code itself, as Gnomon starts it | in every run below | 3,900 | $0.0007 |
| A beat with no connector due | every beat | 0: no model call | none |
| Reads through n8n, folders and Scout | each beat | 0 | none |
| A beat reading 1 connector, something new | each scheduled read | 20,000 | $0.0018 |
| A beat reading 1 connector, nothing new | each scheduled read | 13,000 | $0.0004 |
| A beat reading 3 connectors at once, something new | each scheduled read | 37,000 | $0.0036 |
| A beat reading 3 connectors at once, nothing new | each scheduled read | 23,000 | $0.0007 |
| The nightly distill, 50 items | once a night | 25,000 | $0.0099 |
| An answer through the Brain, two turns | each time an AI app asks | 29,000 | $0.0034 |
| A Work with AI job or Run now, a five-line note | when you start one | 52,000 | $0.0035 |
| A Test bench run: no Brain, full Brain, custom | when you run one | 12,700 | $0.0013 |
| The side-by-side check of notes that may disagree | in the background, at most 60 pairs a day | 3,400 a call | $0.018 a call |

About the connector rows:
- They were measured with local stand-in connectors of 12 read-only tools each (about 1,700
  tokens of tool definitions). A real connector's tools are their own size, and a read takes
  two or three turns that each read them again from cache. Google Drive's tools were about
  20,000 tokens, and its first real read was 69,000 tokens for 10 items (October 27).
- Reading several connectors in one run is cheaper than reading them one by one: 3 quiet
  connectors took 23,000 tokens together, against 13,000 each apart.
- Each connector's Test read shows its own figure (see "Your own numbers").

About the side-by-side check: it runs on Claude Code's default model, which is Opus 5.5 on a
Claude plan that has it. On the 80 labeled pairs of `scripts/safeguards_eval.py`, Haiku named
the right relation in 69 and Sonnet in 77, against 79 for the saved verdicts. The cheaper
models raised false "disagrees" cards, so the check keeps the stronger model.

What makes up a run's tokens:
- Claude Code's own prompt is about 3,900 tokens when Gnomon starts it: no built-in tools,
  none of your own settings, only the MCP servers the run needs.
- The Brain's tools are about 6,600 tokens: 15 grouped tools and their short introduction. The
  app's own tools, which a job uses, are at most about 7,200.
- Each further turn of a run reads all of that again, from cache. Fewer turns is the biggest
  saving. That is why a job's packet carries its project: before it did, the same note took
  13 tool calls and 142,000 tokens.

An AI app you use yourself (Claude Code, Claude Desktop, Codex) pays for its own prompt and
tools on every turn, as it would without Gnomon. The Brain adds its tools and about 800 tokens
of startup and first packet to each session. Run headless with all of Claude Code's built-in
tools and your own settings, the same two-turn answer came to 105,000 tokens, not 29,000.

## A day

How often connectors are read is most of it. A connector whose reads find nothing new is read
less often on its own: half the time it has been quiet, at most every 4 hours, and back to its
own cadence when something new comes in. A connector read hourly that stays quiet overnight
is read about 12 times a day instead of 24.

| | Light | Typical | Heavy |
|---|---|---|---|
| Connectors read through Claude Code | 1 | 3 | 6 |
| Beats that read them | 10 | 12 | 16 |
| Work with AI jobs | 0 | 2 | 10 |
| Test runs after the distill | 0 | 10 | 20 (the daily cap) |
| Side-by-side check calls | 3 | 10 | 30 |
| **Tokens, Haiku work** | **about 200,000** | **about 600,000** | **about 2 million** |
| **Tokens, the check** | **10,000** | **34,000** | **100,000** |
| **Cost on Haiku 5.5, plus the check on Opus 5.5** | **about $0.07** | **about $0.25** | **about $0.75** |

The token rows use the measured figures above with stand-in connectors. Large real connectors
add their own tools once per turn: three connectors the size of Drive would add about a
million tokens a day to the typical day.

## Settings that change it

- **Read through n8n.** A connector read by an n8n workflow on your computer costs no tokens.
  The Heartbeat card offers it for every app it can draft a workflow for.
- **A connector's own cadence.** Set it to every 4 hours or daily in the Heartbeat card, or
  turn off a connector you don't need. A quiet connector already spaces out its reads.
- **The ingest model.** The distill, the judge and the world drafts run on it: Haiku by
  default, which passed every gate of the recorded day.
- **Side-by-side checks.** The Brain's policy `model_checks` (on by default) turns the
  background check off. Checks 1 and 2, by words and figures, still run, and cost nothing.
- **The Test bench after a distill.** At most 20 test runs a day, graded on Haiku. A test
  whose packet has not changed keeps its last answer instead of running again.
- **Start a job from its project.** Its packet then holds where the project stands, so the
  run doesn't search for it.

## Your own numbers

- **Before you turn a connector on:** its Test read in the Heartbeat card (or
  `uv run contxt connectors check`) does one real read and shows the items, tokens, time and
  the estimated cost per beat and per day. Nothing is kept.
- **Afterwards:** `uv run contxt report` shows what context cost by day and by line, from the
  ledger that every run Gnomon starts writes to. Add `--claude-code` to count Claude Code's
  own transcripts on this computer exactly (counts only).
- **Each job:** the project's timeline shows each Work with AI job's model, tokens and cost.
