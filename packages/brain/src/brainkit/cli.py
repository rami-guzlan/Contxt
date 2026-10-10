#!/usr/bin/env python3
"""brain: operate an AI Brain vault from the command line (`brain`, or `python -m brainkit`).

    brain status                      one-screen state
    brain context "<request>"         the packet a model would get (--explain)
    brain check                       validate the vault and startup files
    brain kernel                      rewrite CLAUDE.md and AGENTS.md
    brain inbox [show|approve|reject] review pending proposals
    brain focus [list|show|update|create]
    brain propose / remember          add knowledge through governance
    brain search | note | topic | topics | skill | reference
    brain serve                       local review UI and JSON API
    brain mcp                         MCP server on stdio (what .mcp.json runs)
    brain bench [--holdout]           context usefulness + behavior checks
    brain sync [--dry-run]            propose what is new in drop and skill folders
    brain verify <note> | mark <note> stale|disputed --reason "..."
    brain add-file <file>             propose a document or asset for review
    brain propose-skill <folder>      propose a skill folder for review
    brain scout <folder>              propose knowledge found in documents
    brain intake <file>               file a source document under references/

Global options: --vault PATH (default ./vault or $BRAIN_VAULT), --as SCOPE (act as a
different principal), --json (print structured data instead of text).
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _emit(result, as_json=False) -> int:
    if as_json:
        print(json.dumps(result.data, indent=1, ensure_ascii=False, default=str))
    else:
        print(result.text.rstrip())
    return 1 if result.is_error else 0


def _pairs(values) -> dict:
    out = {}
    for item in values or []:
        key, sep, value = str(item).partition("=")
        if sep:
            out[key.strip()] = value.strip()
    return out


def build_parser():
    parser = argparse.ArgumentParser(prog="brain", description=__doc__.split("\n")[0])
    parser.add_argument("--vault", default=None)
    parser.add_argument("--as", dest="principal", default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-embeddings", action="store_true")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status")
    p = sub.add_parser("models", help="local model status; --download fetches missing ones")
    p.add_argument("--download", action="store_true",
                   help="download the embedding model into vault/.brain/models")
    p.add_argument("--reranker", action="store_true",
                   help="with --download, also the reranker (off unless routing.json "
                        "sets rerank_weight)")
    p = sub.add_parser("context")
    p.add_argument("request", nargs="+")
    p.add_argument("--session")
    p.add_argument("--fresh", action="store_true")
    p.add_argument("--focus")
    p.add_argument("--task-type", choices=["knowledge", "workflow", "combined"])
    p.add_argument("--partition")
    p.add_argument("--via", help="parent scope to inherit through, for multi-team people")
    p.add_argument("--explain", action="store_true")
    p.add_argument("--no-record", action="store_true")
    p.add_argument("--packet-only", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--strict", action="store_true")
    p = sub.add_parser("kernel")
    p.add_argument("--print", action="store_true", dest="print_only")

    p = sub.add_parser("inbox")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "show", "approve", "reject"])
    p.add_argument("id", nargs="?")
    p.add_argument("--edit", action="append", help="key=value override when approving")
    p.add_argument("--body-file")
    p.add_argument("--reason", default="")

    p = sub.add_parser("focus")
    p.add_argument("action", nargs="?", default="list",
                   choices=["list", "show", "update", "create"])
    p.add_argument("name", nargs="?")
    p.add_argument("--summary")
    p.add_argument("--set", action="append", help="changed field, e.g. next='send draft'")
    p.add_argument("--evidence", default="")
    p.add_argument("--status")

    p = sub.add_parser("propose")
    p.add_argument("text", nargs="+")
    p.add_argument("--area", help="where it is filed, e.g. brand (placement is suggested "
                   "when area and topic are omitted)")
    p.add_argument("--layer", help=argparse.SUPPRESS)
    p.add_argument("--topic")
    p.add_argument("--title", help="what the note is for, in a few words")
    p.add_argument("--summary", help="one line saying what it covers")
    p.add_argument("--kind", choices=["fact", "rule", "identity", "state"])
    p.add_argument("--scope")
    p.add_argument("--load", choices=["standing", "domain", "on-demand"],
                   help="default: standing for a rule in your own scope, else on-demand; "
                   "domain makes it a must-hold")
    p.add_argument("--applies-to", help="must-hold: areas, area/topic pairs or project ids, "
                   "comma-separated")
    p.add_argument("--triggers", help="must-hold: words that bring its domain into play, "
                   "comma-separated")
    p.add_argument("--must-text", help="must-hold: the rule in one line")
    p.add_argument("--critical", action="store_true",
                   help="must-hold: also show its line in every session's startup context")
    p.add_argument("--as-of", help="the day a changing value was true (YYYY-MM-DD)")
    p.add_argument("--valid-until", help="the last day it holds (YYYY-MM-DD)")
    p.add_argument("--evidence", default="")
    p.add_argument("--source", default="")
    p.add_argument("--supersedes")
    p.add_argument("--target", help="existing note id to change")
    p = sub.add_parser("remember")
    p.add_argument("text", nargs="+")
    p.add_argument("--scope")

    p = sub.add_parser("search")
    p.add_argument("query", nargs="+")
    p.add_argument("--limit", type=int, default=12)
    p.add_argument("--archived", action="store_true")
    p = sub.add_parser("note")
    p.add_argument("id")
    p = sub.add_parser("topic")
    p.add_argument("route_key")
    sub.add_parser("topics")
    p = sub.add_parser("skill")
    p.add_argument("name")
    p = sub.add_parser("reference")
    p.add_argument("path")

    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    sub.add_parser("mcp")
    p = sub.add_parser("bench")
    p.add_argument("filter", nargs="?")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--holdout", action="store_true", help="show held-out case detail")

    p = sub.add_parser("scout")
    p.add_argument("folder")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--scope")
    p.add_argument("--limit", type=int, default=25)
    p = sub.add_parser("intake")
    p.add_argument("file")
    p.add_argument("--title")
    p.add_argument("--topic", help="area/topic for the pointer note")
    p = sub.add_parser("add-file", help="propose a document or asset (staged until approved)")
    p.add_argument("file")
    p.add_argument("--title")
    p.add_argument("--description", default="")
    p.add_argument("--purpose", choices=["reference", "asset"])
    p.add_argument("--topic", help="area/topic for the pointer note")
    p.add_argument("--replaces", help="a filed reference or asset this is a new version of")
    p = sub.add_parser("propose-skill", help="propose a skill folder (SKILL.md plus files)")
    p.add_argument("folder")
    p.add_argument("--category")
    p.add_argument("--target", help="existing skill to change")
    p = sub.add_parser("verify", help="confirm a note is still true today (the owner)")
    p.add_argument("note")
    p.add_argument("--confidence", choices=["confirmed", "inferred", "disputed", "unknown"])
    p = sub.add_parser("mark", help="mark a note stale or disputed, with a reason (the owner)")
    p.add_argument("note")
    p.add_argument("state", choices=["stale", "disputed"])
    p.add_argument("--reason", required=True)
    p = sub.add_parser("sync", help="propose what is new in the drop and skill folders")
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("report", help="what context cost by day and line, and brief quality")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--claude-code", nargs="?", const="", default=None, metavar="FOLDER",
                   help="read Claude Code's transcripts for exact figures (token counts only)")
    p.add_argument("--model", help="price estimated figures at this model's rates")
    p.add_argument("--no-quality", action="store_true", help="skip the eval runs")
    p = sub.add_parser("replay", help="rebuild logged briefs and show what changed")
    p.add_argument("packets", nargs="*", help="packet ids (default: the newest --recent)")
    p.add_argument("--recent", type=int, default=20)
    p.add_argument("--note", help="the newest packets that carried this note")
    p.add_argument("--at", help="against the vault at a git commit or ref")
    p.add_argument("--with", dest="proposal", help="against the vault with a proposal applied")
    p = sub.add_parser("eval", help="your labeled real requests (kept in .brain/eval)")
    p.add_argument("action", choices=["status", "sample", "run", "label"])
    p.add_argument("case", nargs="?")
    p.add_argument("--n", type=int, default=80)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--holdout", action="store_true")
    for name in ("needed", "useful", "noise", "missing"):
        p.add_argument(f"--{name}", default="", help="note ids, comma-separated")

    return parser


GLOBAL_FLAGS = {"--json": False, "--no-embeddings": False, "--vault": True, "--as": True}


def _hoist_globals(argv):
    """Let global options appear anywhere: `brain context "x" --json` works too."""
    front, rest, skip = [], [], False
    for index, item in enumerate(argv):
        if skip:
            skip = False
            continue
        name = item.split("=", 1)[0]
        if name in GLOBAL_FLAGS:
            front.append(item)
            if GLOBAL_FLAGS[name] and "=" not in item and index + 1 < len(argv):
                front.append(argv[index + 1])
                skip = True
            continue
        rest.append(item)
    return front + rest


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    parser = build_parser()
    args = parser.parse_args(_hoist_globals(list(sys.argv[1:] if argv is None else argv)))
    command = args.command or "status"

    if command == "mcp":
        from brainkit import mcp_server
        if args.vault:
            os.environ["BRAIN_VAULT"] = args.vault
        if args.principal:
            os.environ["BRAIN_PRINCIPAL"] = args.principal
        mcp_server.main()
        return 0

    from brainkit.api import Brain
    brain = Brain(args.vault, principal=args.principal,
                  embeddings=False if args.no_embeddings else None)

    if command == "models":
        rows = []
        if brain.embedder is not None:
            if args.download and not brain.embedder.present():
                print(f"Downloading {brain.embedder.model_name} into vault/.brain/models ...")
                brain.embedder.download()
            rows.append(("embeddings", brain.embedder.status()))
        if brain.reranker is not None:
            if args.download and args.reranker and not brain.reranker.present():
                print(f"Downloading {brain.reranker.model_name} into vault/.brain/models ...")
                brain.reranker.download()
            rows.append(("reranker", brain.reranker.status()))
        for name, status in rows:
            state = ("ready" if status.get("available") or status.get("downloaded")
                     else status.get("reason") or "unavailable")
            print(f"{name:11s} {status['model']}: {state}")
        if not rows:
            print("Models are off (--no-embeddings or BRAIN_RERANK=0).")
        return 0
    if command == "status":
        from brainkit import health
        print(health.status_line(brain))
        pending = brain.inbox()
        print(pending.text.splitlines()[0])
        focus = brain.focus_list()
        active = [r for r in focus.data.get("focuses", []) if r["active"]]
        print(f"{len(active)} active Focus item(s)")
        check = brain.health()
        print(f"health: {len(check.data['problems'])} problem(s), "
              f"{len(check.data['warnings'])} warning(s)")
        return 0
    if command == "context":
        res = brain.context(" ".join(args.request), session_id=args.session, fresh=args.fresh,
                            focus=args.focus, task_type=args.task_type,
                            partition=args.partition, via=args.via, explain=args.explain,
                            record=not args.no_record)
        if args.explain and not args.json:
            print(res.text.rstrip())
            print("\n## Routing trace\n")
            print(json.dumps(res.data.get("trace"), indent=1, default=str))
            return 1 if res.is_error else 0
        if args.packet_only and not args.json:
            text = res.text.split("# Task context", 1)[-1]
            print(text.strip())
            return 0
        return _emit(res, args.json)
    if command == "check":
        from brainkit import health
        return _emit(health.report(brain, strict=args.strict), args.json)
    if command == "kernel":
        if args.print_only:
            return _emit(brain.kernel(), args.json)
        return _emit(brain.write_kernel(), args.json)
    if command == "inbox":
        if args.action == "list":
            return _emit(brain.inbox(), args.json)
        if not args.id:
            parser.error("inbox show|approve|reject needs a proposal id")
        if args.action == "show":
            rows = {r["id"]: r for r in brain.inbox().data.get("proposals", [])}
            row = rows.get(args.id)
            if row is None:
                print(f"No pending proposal {args.id}.")
                return 1
            print(json.dumps({k: v for k, v in row.items() if k != "body"}, indent=1,
                             default=str))
            print("\n" + row["body"])
            if row.get("current_body"):
                print("\n--- current text ---\n" + row["current_body"])
            return 0
        if args.action == "approve":
            body = None
            if args.body_file:
                with open(args.body_file, encoding="utf-8") as handle:
                    body = handle.read()
            return _emit(brain.approve(args.id, actor=args.principal,
                                       edits=_pairs(args.edit), body=body), args.json)
        return _emit(brain.reject(args.id, args.reason, actor=args.principal), args.json)
    if command == "focus":
        if args.action == "list":
            return _emit(brain.focus_list(status=args.status), args.json)
        if not args.name:
            parser.error("focus show|update|create needs a name")
        if args.action == "show":
            return _emit(brain.focus_get(args.name), args.json)
        if args.action == "update":
            if not args.summary:
                parser.error("focus update needs --summary")
            return _emit(brain.focus_update(args.name, args.summary, _pairs(args.set),
                                            evidence=args.evidence), args.json)
        if not args.summary:
            parser.error("focus create needs --summary")
        return _emit(brain.focus_create(args.name, args.summary,
                                        status=args.status or "active"), args.json)
    if command == "propose":
        return _emit(brain.propose(area=args.area or args.layer, topic=args.topic,
                                   title=args.title, summary=args.summary,
                                   note_kind=args.kind, text=" ".join(args.text),
                                   scope=args.scope, load=args.load, evidence=args.evidence,
                                   source=args.source, supersedes=args.supersedes,
                                   target_id=args.target, applies_to=args.applies_to,
                                   triggers=args.triggers, must_text=args.must_text,
                                   critical=True if args.critical else None,
                                   as_of=args.as_of, valid_until=args.valid_until),
                     args.json)
    if command == "remember":
        return _emit(brain.remember(" ".join(args.text), scope=args.scope), args.json)
    if command == "search":
        return _emit(brain.search(" ".join(args.query), limit=args.limit,
                                  include_archived=args.archived), args.json)
    if command == "note":
        return _emit(brain.note(args.id, include_archived=True), args.json)
    if command == "topic":
        return _emit(brain.topic(args.route_key), args.json)
    if command == "topics":
        return _emit(brain.topics(), args.json)
    if command == "skill":
        return _emit(brain.skill(args.name), args.json)
    if command == "reference":
        return _emit(brain.reference(args.path), args.json)
    if command == "serve":
        from brainkit import http_server
        return http_server.serve(brain, port=args.port, open_browser=not args.no_browser)
    if command == "bench":
        from brainkit import bench, evaluate
        failed = False
        if os.path.exists(os.path.join(brain.vault.root, "eval.json")) and not args.filter:
            usefulness = evaluate.run(brain)
            failed = bool(usefulness["failures"])
            if args.json:
                print(json.dumps({k: v for k, v in usefulness.items() if k != "rows"}, indent=1))
            else:
                print("Context usefulness (eval.json): does the packet carry the notes the "
                      "task needs?")
                print(evaluate.report(usefulness, show_holdout_detail=args.holdout))
                print()
        result = bench.run(brain, verbose=args.verbose, only=args.filter)
        failed = failed or bool(result["failures"])
        if args.json:
            print(json.dumps(result, indent=1))
        else:
            print(f"Behavior checks (benchmark.json): {result['cases']} cases, embeddings "
                  f"{'on' if result['semantic'] else 'off'}")
            for name, score in result["scores"].items():
                print(f"  {name:12s} recall {score['recall']:.3f}  skill/reference precision "
                      f"{score['precision']:.3f}")
            print(f"  latency p50 {result['latency']['p50_ms']} ms, "
                  f"p95 {result['latency']['p95_ms']} ms")
            for line in result["failures"]:
                print("  FAIL " + line)
        return 1 if failed else 0
    if command == "scout":
        from brainkit import importers
        return _emit(importers.scout(brain, args.folder, dry_run=args.dry_run,
                                     scope=args.scope, limit=args.limit), args.json)
    if command == "intake":
        from brainkit import importers
        return _emit(importers.intake(brain, args.file, title=args.title, topic=args.topic),
                     args.json)
    if command == "add-file":
        return _emit(brain.add_file(source_path=args.file, title=args.title,
                                    description=args.description, purpose=args.purpose,
                                    topic=args.topic, replaces=args.replaces,
                                    source=f"owner: {args.file}"), args.json)
    if command == "propose-skill":
        from brainkit import sync as sync_mod
        return _emit(sync_mod.propose_folder(brain, args.folder, category=args.category,
                                             target=args.target), args.json)
    if command == "sync":
        return _emit(brain.sync(dry_run=args.dry_run), args.json)
    if command == "verify":
        return _emit(brain.verify(args.note, confidence=args.confidence), args.json)
    if command == "mark":
        return _emit(brain.mark(args.note, args.state, reason=args.reason), args.json)
    if command == "report":
        from brainkit import costs, report
        folder = args.claude_code
        if folder == "":
            folder = costs.default_transcripts()
        found = report.card(brain, days=args.days, transcripts=folder or None, model=args.model,
                            quality=not args.no_quality)
        if args.json:
            print(json.dumps(found, indent=1, ensure_ascii=False, default=str))
        else:
            print(report.render(found).rstrip())
        return 0
    if command == "replay":
        from brainkit import replay
        packets = args.packets or replay.recent_packets(brain, item=args.note,
                                                        limit=args.recent)
        try:
            found = replay.replay(brain, packets, at=args.at, proposal=args.proposal)
        except ValueError as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(found, indent=1, ensure_ascii=False, default=str))
            return 0
        print(f"Replayed {found['replayed']} brief(s) {found['against']} in "
              f"{found['seconds']} s: {found['changed']} changed.")
        for row in found["rows"]:
            if row.get("error"):
                print(f"- {row['packet_id']}: {row['error']}")
                continue
            d = row["diff"]
            if d["same"]:
                continue
            print(f"- {row['packet_id']} {row['request'][:70]!r}")
            for key in ("notes", "must_holds", "sections"):
                if d[key]["entered"]:
                    print(f"    + {key}: {', '.join(d[key]['entered'])}")
                if d[key]["left"]:
                    print(f"    - {key}: {', '.join(d[key]['left'])}")
            if d["notes"]["moved"]:
                print(f"    ~ moved: {', '.join(d['notes']['moved'])}")
            print(f"    tokens {d['tokens']['before']} -> {d['tokens']['after']}")
        return 0
    if command == "eval":
        from brainkit import evalset
        if args.action == "status":
            print(json.dumps(evalset.status(brain), indent=1))
            return 0
        if args.action == "sample":
            print(json.dumps(evalset.sample(brain, args.n, days=args.days), indent=1))
            return 0
        if args.action == "label":
            if not args.case:
                parser.error("eval label needs a case id or packet id")
            ids = {name: [i.strip() for i in getattr(args, name).split(",") if i.strip()]
                   for name in ("needed", "useful", "noise", "missing")}
            try:
                case = evalset.label(brain, args.case, **ids)
            except (KeyError, ValueError) as exc:
                print(f"Not labeled: {exc}")
                return 1
            print(json.dumps(case, indent=1, ensure_ascii=False))
            return 0
        from brainkit import evaluate
        result = evalset.run(brain, holdout=True if args.holdout else None)
        if not result.get("cases") and "all" not in result:
            print("No labeled cases yet: `brain eval sample`, then label them.")
            return 1
        print(evaluate.report(result))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
