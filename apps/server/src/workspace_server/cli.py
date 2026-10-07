"""contxt: set up, run and connect Contxt.

    contxt setup [--brain STARTER]  make this folder's Brain, data and outputs (once)
    contxt serve                    the app on 127.0.0.1:8787, with its worker
    contxt connect [CLIENT]         connect an AI app to your Brain: claude-code,
                                    claude-desktop, codex, cursor or other
    contxt demo STARTER             try a demo Brain, in demos/STARTER on a port of its own
    contxt starters                 the starter Brains: empty, and the demos
    contxt check                    is this Contxt ready? what to fix, one line each
    contxt web [--download]         the web app: is it built (--download fetches this version's)
    contxt models [--download]      the local models for matching by meaning and for speech
    contxt token                    print the owner sign-in link (--new: a fresh random token)
    contxt status                   one-screen state
    contxt add-model NAME PROVIDER  give a model its own token for the app's AI work
    contxt worker [--once]          lease expiry and due-task scheduling, in a loop
    contxt mcp --url URL            stdio bridge to the app's /mcp (token in CONTXT_TOKEN)
    contxt migrate [--preview]      apply (or show) pending database migrations
    contxt backup [OUT]             one archive: database, files, manifest (--with-brain)
    contxt restore ARCHIVE          into an empty data directory
    contxt export-legacy            the earlier workspace's goals, to-dos, meetings... as files
    contxt speech [--download]      speech to text: is the model here (--download fetches it)

Settings come from the environment and the home's `.env` (see .env.example). The home is the
current folder, or the one --home names.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

from workspace_connectors.providers import BRAIN_CLIENTS, PROVIDERS, brain_setup, mcp_setup
from workspace_core.backup import backup, restore
from workspace_core.db import migrate
from workspace_core.db.engine import Database, sqlite_url

from . import doctor, homes, webapp
from .settings import Settings, new_token


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="contxt", description=__doc__.split("\n")[0])
    parser.add_argument("--home", help="the Contxt folder to use (default: this one)")
    parser.add_argument("--env-file", default=".env")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("setup", help="make this folder's Brain, data and outputs")
    p.add_argument("--brain", default="empty", help="the starter Brain (see: contxt starters)")
    p.add_argument("--name", help="what to call it (default: the starter's name)")
    p.add_argument("--port", type=int, help="the app's port (default: 8787, or the next free one)")
    p.add_argument("--models", action="store_true", help="also download the local models")
    p = sub.add_parser("demo", help="try a demo Brain on a port of its own")
    p.add_argument("starter")
    p.add_argument("--port", type=int)
    p.add_argument("--host")
    p.add_argument("--no-worker", action="store_true")
    sub.add_parser("starters", help="the starter Brains")
    p = sub.add_parser("connect", help="connect an AI app to your Brain")
    p.add_argument("client", nargs="?", choices=sorted(BRAIN_CLIENTS))
    p = sub.add_parser("models", help="the local models (--download fetches what is missing)")
    p.add_argument("--download", action="store_true")
    sub.add_parser("check", help="is this Contxt ready? what to fix")
    p = sub.add_parser("web", help="the web app (--download fetches this version's build)")
    p.add_argument("--download", action="store_true")
    p = sub.add_parser("serve")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.add_argument("--no-worker", action="store_true")
    p = sub.add_parser("worker")
    p.add_argument("--once", action="store_true")
    p = sub.add_parser("mcp")
    p.add_argument("--url", help="the server's /mcp URL (default: from settings)")
    p.add_argument("--token-env", default="CONTXT_TOKEN")
    p = sub.add_parser("add-model", help="give a model its own token for the app's AI work")
    p.add_argument("name")
    p.add_argument("provider", choices=sorted(PROVIDERS))
    p.add_argument("--project", action="append", dest="projects")
    p = sub.add_parser("token")
    p.add_argument("--new", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("migrate")
    p.add_argument("--preview", action="store_true")
    p = sub.add_parser("backup")
    p.add_argument("out", nargs="?")
    p.add_argument("--with-brain", action="store_true")
    p = sub.add_parser("speech")
    p.add_argument("--download", action="store_true")
    p = sub.add_parser("restore")
    p.add_argument("archive")
    p.add_argument("--brain-dir")
    p = sub.add_parser("export-legacy")
    p.add_argument("--out", help="the folder to write (default: a new one under the exports)")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass
    args = _parser().parse_args(argv)
    command = args.command or "status"
    if command == "token" and args.new:
        print(new_token())
        return 0
    try:
        if command == "setup":
            return _setup(args)
        if command == "starters":
            return _starters()
        if command == "demo":
            return _demo(args)
    except homes.HomeError as error:
        print(error, file=sys.stderr)
        return 1
    settings = Settings.from_env(args.env_file, home=args.home)
    if command == "connect":
        return _connect(settings, args.client)
    if command == "models":
        return _models(settings, download=args.download)
    if command == "check":
        return _check(settings)
    if command == "web":
        return _web(settings, download=args.download)
    if command == "mcp":
        from .mcp import bridge

        token = os.environ.get(args.token_env) or os.environ.get("WORKSPACE_TOKEN")
        if not token:
            print(f"Set {args.token_env} to this connection's token.", file=sys.stderr)
            return 2
        return bridge.run(args.url or settings.base_url + "/mcp", token)
    if command == "migrate":
        db = Database(
            settings.database_url or sqlite_url(os.path.join(settings.data_dir, "workspace.sqlite"))
        )
        try:
            if args.preview:
                print(migrate.pending(db) or "No pending migrations.")
                print(migrate.preview_sql(db))
                return 0
            report = migrate.upgrade(db, backup_dir=os.path.join(settings.data_dir, "backups"))
            print(
                f"{report.before or 'empty'} -> {report.after}"
                if report.changed
                else f"Up to date at {report.after}."
            )
            if report.backup:
                print(f"Backup before migrating: {report.backup}")
        finally:
            db.close()
        return 0
    if command == "restore":
        result = restore(
            args.archive,
            settings.data_dir,
            database_url=settings.database_url,
            brain_dir=args.brain_dir,
        )
        print(json.dumps({k: v for k, v in result.items() if k != "manifest"}, indent=1))
        return 0

    from .app import open_runtime

    runtime = open_runtime(settings)
    ws = runtime.ws
    try:
        if command == "serve":
            return _serve(runtime, args)
        if command == "worker":
            from .worker import Worker

            worker = Worker(ws, settings.worker_interval)
            if args.once:
                tick = worker.tick()
                print(f"expired {tick.expired}, came due {tick.woke}")
                return 0
            print(f"Worker running every {worker.interval:.0f}s. Ctrl+C to stop.")
            try:
                worker.run()
            except KeyboardInterrupt:
                pass
            return 0
        if command == "add-model":
            connection = ws.actors.connect_model(
                ws.owner(), name=args.name, provider=args.provider, projects=args.projects
            )
            setup = mcp_setup(args.provider, url=settings.base_url, token=connection.token)
            print(f"Connected {connection.actor.name} ({connection.actor.id}).")
            print(f"Token (shown once): {connection.token}\n")
            print(f"Put this in {setup['file']}:\n{setup['config']}")
            if setup.get("command"):
                print(f"\nOr run:\n{setup['command']}")
            print("\nWorker prompt for its scheduled check:\n")
            print(runtime.templates.worker_prompt(connection.actor.name, ws.info().name))
            return 0
        if command == "token":
            print(f"Sign in: {settings.base_url}/auth/login?token={runtime.owner_token}")
            return 0
        if command == "status":
            info, counts = ws.info(), ws.counts(ws.owner())
            work = ", ".join(f"{n} {s}" for s, n in sorted(counts["ai_work"].items())) or "none"
            print(f"{info.name} ({info.timezone}), data in {os.path.abspath(settings.data_dir)}")
            print(f"AI work: {work}; waiting for your review: {counts['brain_proposals']}")
            print(f"brain: {ws.rt.brain.status().get('name') or 'none configured'}")
            return 0
        if command == "backup":
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            out = args.out or os.path.join(settings.data_dir, "backups", f"workspace-{stamp}.zip")
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            manifest = backup(
                ws, out, brain_vault=settings.brain_vault if args.with_brain else None
            )
            print(
                f"Backed up {sum(manifest['tables'].values())} records and "
                f"{manifest['objects']['count']} files to {out}"
            )
            return 0
        if command == "export-legacy":
            from .routes.legacy import export_dir

            exports = settings.exports_dir or os.path.join(settings.data_dir, "exports")
            out = args.out or export_dir(exports, datetime.now(UTC))
            made = ws.legacy.export(ws.owner(), out)
            print(f"Wrote {made['files']} files to {made['dir']}")
            return 0
        if command == "speech":
            speech = runtime.speech
            if args.download and not speech.present():
                print(f"Downloading {speech.model} (about {speech.status()['about_mb']} MB) ...")
                speech.download()
            state = speech.status()
            where = speech.models_dir
            if state["error"]:
                print(state["error"])
            elif not state["installed"]:
                print("Speech to text is not installed: run uv sync.")
            elif state["present"]:
                print(f"Speech to text is ready: {speech.model} in {where}.")
            else:
                print(f"No speech model in {where}. Run: contxt speech --download")
            return 0 if state["ready"] else 1
    finally:
        if command != "serve":
            runtime.close()
    return 2


def _serve(runtime: object, args: argparse.Namespace) -> int:
    import uvicorn

    from .app import Runtime, create_app
    from .digests import DigestWorker
    from .speech import TranscriptionWorker
    from .worker import Worker

    assert isinstance(runtime, Runtime)
    settings = runtime.settings
    runtime.runners.sweep()  # credentials of runs a stopped server left behind
    host, port = args.host or settings.host, args.port or settings.port
    settings.host, settings.port = host, port
    worker = None if args.no_worker else Worker(runtime.ws, settings.worker_interval)
    transcriber = None if args.no_worker else TranscriptionWorker(runtime.ws, runtime.speech)
    digester = None if args.no_worker else DigestWorker(runtime.ws, runtime.runners)
    if worker:
        worker.start()
    if transcriber:
        transcriber.start()
    if digester:
        digester.start()
    print(f"Contxt on {settings.base_url}")
    print(f"Sign in: {settings.base_url}/auth/login?token={runtime.owner_token}")
    print(f"The app's MCP endpoint, for the AI work it starts: {settings.base_url}/mcp")
    if settings.brain_vault:
        print("Connect an AI app to your Brain: uv run contxt connect")
    if not webapp.built(webapp.location(settings.web_dist)):
        print("The web app is not built yet: uv run contxt web --download")
    try:
        uvicorn.run(
            create_app(runtime=runtime),
            host=host,
            port=port,
            log_level="info",
            proxy_headers=settings.trust_proxy,
            forwarded_allow_ips="*" if settings.trust_proxy else None,
        )
    finally:
        if worker:
            worker.stop()
        if transcriber:
            transcriber.stop()
        if digester:
            digester.stop()
    return 0


def _home(args: argparse.Namespace) -> str:
    return os.path.abspath(args.home or os.getcwd())


def _setup(args: argparse.Namespace) -> int:
    home = _home(args)
    starter = homes.find_starter(args.brain)
    made = homes.create_home(home, starter, port=args.port or homes.free_port(8787), name=args.name)
    print(f"Made a Brain from the {starter.id} starter ({starter.name}) in {made['brain']}")
    print(f"The app's data goes in {made['data']} and what your AI makes in {made['outputs']}.")
    print(f"Settings: {made['env']}\n")
    settings = Settings.from_env(home=home)
    if args.models:
        _models(settings, download=True)
    command = "uv run contxt" + (f' --home "{home}"' if args.home else "")
    print("Next:")
    if not webapp.built(webapp.location(settings.web_dist)):
        print(f"  {command} web --download   get the web app (or: npm install, npm run build)")
    print(f"  {command} serve      start the app (it prints your sign-in link)")
    print(f"  {command} connect    connect Claude Code, Claude Desktop, Codex or another AI app")
    if not args.models:
        print(f"  {command} models --download   match by meaning and transcribe speech, offline")
    print(f"  {command} check      see that everything works")
    return 0


def _starters() -> int:
    found = homes.starters()
    if not found:
        raise homes.HomeError("No starter Brains found: run Contxt from its repository folder.")
    width = max(len(s.id) for s in found)
    for starter in found:
        print(f"{starter.id.ljust(width)}  {starter.name}: {starter.description}")
    print("\nStart yours: uv run contxt setup --brain <starter>")
    print("Try one first: uv run contxt demo <starter>")
    return 0


def _demo(args: argparse.Namespace) -> int:
    starter = homes.find_starter(args.starter)
    root = homes.repository_root() or os.getcwd()
    home = os.path.join(root, "demos", starter.id)
    if not homes.has_brain(home):
        port = args.port or homes.free_port()
        homes.create_home(home, starter, port=port, name=f"{starter.name} (demo)")
        print(f"Made the {starter.id} demo in {home}")
    settings = Settings.from_env(home=home)
    from .app import open_runtime

    return _serve(open_runtime(settings), args)


def _connect(settings: Settings, client: str | None) -> int:
    if not settings.brain_vault:
        print("There is no Brain here yet. Make one first: uv run contxt setup", file=sys.stderr)
        return 1
    vault = os.path.abspath(settings.brain_vault)
    for name in [client] if client else list(BRAIN_CLIENTS):
        setup = brain_setup(name, python=sys.executable, vault=vault)
        print(f"== {setup['label']}")
        if setup.get("command"):
            print(setup["command"])
        else:
            print(f"In {setup['file']}:\n{setup['config']}")
        print(setup["note"] + "\n")
    return 0


def _check(settings: Settings) -> int:
    from workspace_core import __version__

    env = os.path.abspath(".env")
    print(f"Contxt {__version__}" + (f", settings from {env}" if os.path.isfile(env) else ""))
    checks = doctor.run(settings)
    print(doctor.render(checks))
    return 1 if any(c.state == doctor.FAIL for c in checks) else 0


def _web(settings: Settings, *, download: bool) -> int:
    where = webapp.location(settings.web_dist)
    if not download:
        if webapp.built(where):
            print(f"The web app is built: {where}")
            return 0
        print("The web app is not built yet. Get this version's build with:")
        print("  uv run contxt web --download")
        print("or build it yourself with Node.js 20+: npm install, then npm run build")
        return 1
    if not where:
        print("Set CONTXT_WEB_DIST to the folder the web app should go in.", file=sys.stderr)
        return 1
    try:
        got = webapp.download(where)
    except webapp.WebAppError as error:
        print(error, file=sys.stderr)
        return 1
    print(
        f"Put the web app of {got['tag']} in {got['target']} ({got['bytes'] // 1024} KB,"
        f" checksum verified). Restart the app if it is running."
    )
    return 0


def _models(settings: Settings, *, download: bool) -> int:
    """The Brain's embedding model (matching by meaning) and the speech model, each local."""
    ready = True
    if settings.brain_vault:
        from brainkit.cli import main as brain_main

        brain_args = ["--vault", settings.brain_vault, "models"]
        ready = brain_main(brain_args + (["--download"] if download else [])) == 0 and ready
    else:
        print("No Brain here yet, so no model for matching by meaning: run contxt setup first.")
    from .speech import Speech

    speech = Speech(settings.speech_models)
    if download and not speech.present():
        print(f"Downloading {speech.model} (about {speech.status()['about_mb']} MB) ...")
        speech.download()
    state = speech.status()
    if state["error"]:
        print(state["error"])
    elif state["present"]:
        print(f"Speech to text is ready: {speech.model} in {speech.models_dir}.")
    else:
        print(f"No speech model in {speech.models_dir}. Run: contxt models --download")
    return 0 if ready and state["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
