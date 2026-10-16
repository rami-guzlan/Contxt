"""A stand-in for the Codex and Gemini CLIs in tests. Its first argument says which it is (the
resolver passes it); asked for one answer, the answer is a report of exactly how it was
started: its arguments, its folder and the prompt it read on stdin. Each also prints what the
real one prints beside its answer (Codex a header, Gemini a credentials line), which the
workspace must leave out.

FAKE_CLI_MODE is ok (default) or fail (exits with an error on stderr).
"""

import json
import os
import sys

kind, args = sys.argv[1], sys.argv[2:]
if args[:1] == ["--version"]:
    print("codex-cli 0.9.9" if kind == "codex" else "0.9.9")
    sys.exit(0)
if args[:2] == ["login", "status"]:
    print("Logged in using ChatGPT")
    sys.exit(0)
prompt = sys.stdin.read()
if os.environ.get("FAKE_CLI_MODE") == "fail":
    print("quota exceeded for this account", file=sys.stderr)
    sys.exit(2)
report = json.dumps({"argv": args, "cwd": os.getcwd(), "prompt": prompt})
if kind == "codex":
    print("OpenAI Codex v0.9.9 (research preview)\n--------\nworkdir: " + os.getcwd())
    with open(args[args.index("--output-last-message") + 1], "w", encoding="utf-8") as handle:
        handle.write(report)
    print("tokens used: 120")
else:
    print("Loaded cached credentials.")
    print(report)
