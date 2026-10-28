# What Gnomon costs a day

Gnomon spends model tokens on five kinds of work. This page gives what each one cost when it
was measured, what a typical day adds up to, and how to see your own.

All figures are Claude Haiku 5.5 through Claude Code (`--model haiku`), the default for
Gnomon's background work. Its list prices are $0.10 per million input tokens, $0.50 per
million output tokens, $0.01 per million cached tokens read and $0.20 per million written to
the one-hour cache. On a Claude plan, the tokens count against the plan's usage instead of
costing dollars, which is why this page leads with tokens.

## What each piece of work costs

| Work | When | Tokens | Cost | Measured |
|---|---|---|---|---|
| Claude Code itself, headless, no tools | every run Gnomon starts | about 3,900 | $0.0007 | Oct 28, a bare run |
| An answer with the Brain connected | each time an AI app asks the Brain | 29,000 for a two-turn answer | $0.0034 | Oct 28, the entrepreneur demo |
| A Work with AI job or Run now | when you start one | 52,000 for a five-line note | $0.0035 | Oct 28, the entrepreneur demo |
| A connector read through a CLI | each scheduled read | 20,000 to 70,000 | under $0.01 | Oct 27, a first Drive read: 69,000 for 10 items |
| The beat's judge | only when learning per beat (the default learns nightly instead) | about 3,700 a beat with news | under $0.001 | Oct 25, the recorded day |
| The nightly distill | once a night | 23,000 to 28,000 | about $0.003 | Oct 25, the recorded day |
| Reads through n8n, folders and Scout | each beat | none | none | |

What makes up a run's tokens:
- Claude Code's own prompt is about 3,900 tokens when Gnomon starts it: no built-in tools, none
  of your own settings, only the MCP servers the run needs.
- The Brain's tools are about 6,600 tokens: 15 grouped tools and their short introduction. The
  app's own tools, which a job uses, are at most about 7,200.
- A connector's read-only tools are its own size: Drive's were about 20,000.
- Each further turn of a run reads all of that again, from cache. Fewer turns is the biggest
  saving, which is why a job's packet carries its project: before that change, the same note
  took 13 tool calls and 142,000 tokens.

An AI app you use yourself (Claude Code, Claude Desktop, Codex) pays for its own prompt and
tools on every turn. The Brain adds its tools and about 800 tokens of startup and first packet
to each session. Run headless with all of Claude Code's built-in tools and your own settings,
the same two-turn answer came to 105,000 tokens.

## A typical day

A Brain with three connectors read through Claude Code, about 20 AI sessions that ask it, two
Work with AI jobs and the nightly distill:

| Work | How many | Tokens |
|---|---|---|
| Connector reads | 3 connectors, hourly while things change (8 hours), then spaced out to every 4 hours (about 4 more) | 12 reads × 3 × about 45,000 = 1,620,000 |
| Work with AI jobs | 2 | 100,000 |
| The nightly distill | 1 | 25,000 |
| The Brain's share of 20 sessions | startup and first packet | 16,000 |
| **All** | | **about 1.75 million tokens, a few cents on Haiku 5.5** |

Connector reads are most of it. A connector whose reads find nothing new is read less often on
its own: half the time it has been quiet, at most every 4 hours, back to its own cadence when
something new comes in. Read hourly all day, the same three connectors would take about
3.2 million tokens.

## Spending less

- **Read through n8n.** A connector read by an n8n workflow on your computer costs no tokens.
  The Heartbeat card offers it for every app it can draft a workflow for.
- **Read less often.** Set a connector's own cadence (every 4 hours, or daily) in the
  Heartbeat card. Turn off what you don't need.
- **Keep the nightly distill on Haiku.** It is the default. The recorded day passed every
  gate on Haiku.
- **Give a job its project.** Start Work with AI from the project it is about: the packet
  then holds where the project stands, and the run doesn't search for it.

## Your own numbers

- **Before you turn a connector on:** its Test read in the Heartbeat card (or
  `uv run contxt connectors check`) does one real read and shows the items, tokens, time and
  the estimated cost per beat and per day. Nothing is kept.
- **Afterwards:** `uv run contxt report` shows what context cost by day and by line, from the
  ledger every run Gnomon starts writes to. Add `--claude-code` to count Claude Code's own
  transcripts on this computer exactly (counts only).
- **Each job:** the project's timeline shows each Work with AI job's model, tokens and cost.
