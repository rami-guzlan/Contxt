# Contxt

**One Brain for every AI you use. On your computer, governed by you.**

You tell each AI the same things over and over: who you are, how you want work done, what
you are working on, where each project stands. Contxt keeps all of that in one Brain on your
own computer, and every AI app you connect (Claude Code, Claude Desktop, Codex, Cursor, any
MCP client) reads the part each request needs and saves what it learns, for your approval.

![Contxt home, with a demo Brain](docs/images/home.png)

> Pre-release. The code is not yet licensed for use by others: see [LICENSING.md](LICENSING.md).

## How it works

```
 your work                    your Brain                       every AI app you use
 ---------                    ----------                       --------------------
 what you say, files,   ->    plain Markdown files, in   ->    asks for the context a request
 decisions, progress          folders, every change in         needs, and proposes what it
                              git, on your computer            learns: you approve
```

- **Your Brain is files you own.** Notes, rules, skills, projects and documents are Markdown
  in a folder, with every change kept in git. Any editor can open them; nothing is locked
  in an app or a cloud.
- **Every AI gets the right part.** Each request gets a small, focused packet: the rules that
  always apply, the notes and file sections that request is about, and where the project it
  names stands. Never the whole Brain.
- **Nothing changes without you.** Files, decisions and progress go in at once with an undo
  point. Rules and preferences an AI picks up wait for you in Review.
- **Local by default.** The app runs on `127.0.0.1`. Matching by meaning and speech to text
  run on local models. Nothing leaves your computer except what your AI app sends to its own
  model.

## Quick start

You need [git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/) and
[Node.js](https://nodejs.org/) 20+.

```bash
git clone https://github.com/rami-guzlan/Contxt.git
cd Contxt
uv sync
npm install
npm run build
uv run contxt setup
uv run contxt serve
```

`setup` makes your Brain (from the empty starter) and the folders beside it. `serve` starts
the app on `http://127.0.0.1:8787` and prints your sign-in link. Then connect your AI:

```bash
uv run contxt connect claude-code
```

prints one command. Run it once, and every Claude Code session has your Brain. The same works
for `claude-desktop`, `codex`, `cursor` and `other`, and the app shows it under **Settings, AI
apps**:

![Connecting an AI app to the Brain](docs/images/connect.png)

The full walkthrough, including Windows notes and Docker, is in [docs/setup.md](docs/setup.md).

## Try a demo Brain

```bash
uv run contxt demo knowledge-company
```

Each demo runs from its own folder on its own port, so your Brain is never touched.

| Demo | Who it is for |
| --- | --- |
| `knowledge-company` | Brightmill, a made-up knowledge company, as its one-person marketing team runs it: voice and approval rules, audience research, a webinar series, a podcast, content skills |
| `programmer` | Kai, a made-up backend engineer: machine and stack, code style and git rules, services and deploys, an open source release |
| `entrepreneur` | Riley, a made-up founder: a seed-stage startup and its numbers, a seed round, a past company's lessons, angel checks |
| `personal` | Taylor, a made-up parent: family schedules and an allergy, the house, the budget, training, a trip to Japan |

Everything in the demos is invented. To start your own Brain from one,
`uv run contxt setup --brain programmer`. See [brains/README.md](brains/README.md).

## Where your things live

| Folder | What it holds | In this repository? |
| --- | --- | --- |
| `brain/` | Your Brain: notes, skills, references, projects, as Markdown | No: a git repository of its own, which you can push to a private remote for backup |
| `data/` | The app's database, uploaded files, your sign-in key, backups | No |
| `outputs/` | What your AI makes through the app | No |
| `.env` | This folder's settings | No |

The Brain is files, and the app's bookkeeping is a small SQLite database, on purpose: files
are what every AI tool and editor can read, with a history you can undo, while the app's live
state (recordings waiting for a summary, AI work in progress, sign-in keys) needs a database
that stays consistent when several things change at once. What is worth keeping moves from
the app into the Brain when you approve it.

## The app

| Page | What it is for |
| --- | --- |
| Home | What came in, what waits for you, your Brain at a glance, projects in motion |
| Capture | Talk (hold Space), upload a recording or a file, or write a note: each gets a summary that says how it relates to your Brain, and you pull in what matters |
| Projects | Each project's brief, where it stands, its progress and files, the names your AI knows it by |
| Brain | The map of what it knows, every entry, its files, the history of every change, the questions it could not answer |
| Skills | Procedures your AI follows: run one here and watch what it makes, or improve it in plain words |
| Review | What your AI suggested, in batches, each decision an undo point |
| Settings | Your AI apps, what saves straight in, local models, backups |

![A project: where it stands, its progress, what your AI gets](docs/images/project.png)

![The Brain's map](docs/images/brain.png)

![Skills, each runnable from the app](docs/images/skills.png)

## Local models (optional)

```bash
uv run contxt models --download
```

downloads, once, a small embedding model (about 70 MB) so your Brain matches requests by
meaning, and a speech model (about 480 MB) so talk and recordings become text on your
computer. Without them the Brain matches by words and talking is off.

## Repository

```
apps/server          the app's API, its MCP endpoint, the worker and the contxt command
apps/web             the web app
packages/core        application services behind one facade
packages/brain       the Brain engine: routing, governance, files, its MCP server
packages/connectors  how each AI app connects
brains/              starter Brains: empty and four demos
docs/                setup, architecture, MCP, operations, decisions, the Brain's design
```

For AI coding agents working in this repository: [AGENTS.md](AGENTS.md).

## Documentation

- [Setup](docs/setup.md): install, your Brain, connecting your AI apps, Docker
- [Architecture](docs/architecture.md) and [decisions](docs/adr/)
- [MCP](docs/mcp.md): the Brain's server and the app's endpoint
- [Running the app's AI work](docs/runners.md)
- [Operations](docs/operations.md): backups, upgrades, the private-server profile
- [The Brain](docs/brain/ARCHITECTURE.md): routing, governance, capture, configuration

## Development

```bash
uv run pytest
uv run ruff check .
uv run mypy
npm test
npm run typecheck
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).
