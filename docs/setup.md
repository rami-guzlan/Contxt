# Setup

The first success: your AI answers a question about your own work from your Brain. This guide
gets you there in about ten minutes.

## 1. Install

You need [git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/) (it brings Python
3.12+), and [Node.js](https://nodejs.org/) 20 or newer to build the web app once.

```bash
git clone https://github.com/rami-guzlan/Contxt.git
cd Contxt
uv sync
npm install
npm run build
```

On Windows, run the same commands in PowerShell, one per line. If `uv sync` stops with
"Failed to update Windows PE resources", antivirus is scanning a file uv just wrote: run it
again until it finishes (each try gets further).

## 2. Make your Brain

```bash
uv run contxt setup
```

This makes three folders inside `Contxt/` and a settings file:

| Folder | What it holds |
| --- | --- |
| `brain/` | Your Brain: Markdown notes, skills, references and projects. A git repository of its own, so every change has a history and an undo. |
| `data/` | The app's database, uploaded files, your sign-in key and backups. |
| `outputs/` | What your AI makes through the app. |
| `.env` | This folder's settings, with paths relative to it. |

Git ignores all four in the Contxt repository: your Brain and your data never end up in it.

`setup` starts from the empty Brain. To start from a demo instead, name it:
`uv run contxt setup --brain programmer`. `uv run contxt starters` lists them all, and
[brains/README.md](../brains/README.md) says what is in each. Setup never overwrites a Brain
that is already there.

To keep a Brain somewhere else (a synced folder, say), give setup another home:
`uv run contxt --home D:\MyContxt setup`, then pass the same `--home` to the other commands.

## 3. Start the app

```bash
uv run contxt serve
```

It prints the address (`http://127.0.0.1:8787`) and your sign-in link. Open the link: it
signs this browser in with a cookie that stays on this computer. The link is your key, so
keep it to yourself. `uv run contxt token` prints it again.

Home offers the **first-time setup**: your name and timezone, your AI apps, what the Brain
should know about you, a first project and its files. It ends at the **guided tour**, which
the **?** at the top right replays at any time.

## 4. Connect your AI apps

```bash
uv run contxt connect
```

prints, for each AI app, exactly what to run or paste, with your paths filled in. Run it for
one app with its name (`claude-code`, `claude-desktop`, `codex`, `cursor`, `other`). The app
shows the same under **Settings, AI apps**.

- **Claude Code**: one command, run once. Every Claude Code session then has your Brain.
- **Claude Desktop**: a block for `claude_desktop_config.json`. Quit Claude Desktop fully and
  open it again.
- **Codex**: a block for `~/.codex/config.toml`. Start a new Codex session.

The connection is a local command beside your Brain folder (MCP over stdio): no account, no
token, and nothing goes anywhere but to the AI app you connect. The app does not need to be
running for your AI apps to use the Brain.

From then on, every chat starts by asking the Brain for the context its request needs
(`get_task_context`), and proposes what it learns: rules and preferences you state, decisions,
progress on your projects, files you share. Projects and files go in at once with an undo
point; rules and preferences wait for you in **Review**.

## 5. Match by meaning, and talk (optional)

```bash
uv run contxt models --download
```

fetches two local models into `brain/vault/.brain/models`, once:

- a small embedding model (BAAI/bge-small-en-v1.5, about 70 MB), so your Brain matches a
  request by what it means, not only the words it uses;
- a speech model (faster-whisper `small.en`, about 480 MB), so talk and recordings turn into
  text on this computer. On a 12-thread laptop CPU, 15 seconds of talk takes about 2 seconds.

Nothing downloads on its own. Without them the Brain matches by words, and talking is off.

## 6. Start a project and add its files

**Projects, New project**: its name, what it is for in a line, and the other names you call
it by. Then **Add a file** on its page: a proposal, a brief, notes from a meeting. Ask about
the project in any chat and your AI gets where it stands and the part of each file the
request is about. **What your AI gets** on the project page shows exactly what it would
receive.

## 7. Let the app run AI work (optional)

A few jobs in the app are work a model does: summing up a recording, finding what to remember
in a note, running a skill. With Claude Code installed and signed in on this computer they show
**Run now**: no schedule, token or extra setup. See [Running the app's AI work](runners.md).

To hand that work to another model, **Settings, AI apps, Connect a model** (or
`uv run contxt add-model NAME PROVIDER`). It shows, once, the model's own token and the exact
MCP settings for its platform. See [MCP](mcp.md).

## Try a demo first

```bash
uv run contxt demo knowledge-company
```

runs a demo Brain in `demos/knowledge-company/`, with its own data and port (8790 and up), and
prints its sign-in link. Your own Brain is never touched. Stop it with Ctrl+C; start it again
with the same command.

## Docker

```bash
cp .env.example .env
docker compose up -d
docker compose exec app contxt token     # prints your sign-in link
```

The app listens on `127.0.0.1:8787` only; its database and files live in the `contxt-data`
volume. To give it a Brain, set `BRAIN_HOST_DIR` in `.env` to a Brain folder (the one that
holds `vault/`), for example one `contxt setup` made.

On Linux, tell the containers who you are first: they write into the folders you mount, and
run as user 10001 unless told otherwise. Set `CONTXT_UID` and `CONTXT_GID` in `.env` to the
output of `id -u` and `id -g`. Docker Desktop on Windows and macOS needs none of this. See
[Operations](operations.md#which-user-the-containers-run-as).

## An earlier workspace

An install from before the app became Contxt keeps everything it held (goals, to-dos,
meetings, project memory, sheets, canvases). **Settings, Workspace, Your earlier workspace**
copies it all out as files and brings its context into the Brain. `uv run contxt
export-legacy` makes the same copy from the command line.
