"""The whole trustworthy path, with a real model: capture -> distill -> review -> approve ->
an AI asks through the Brain's MCP server -> a cited answer -> revoke, on a scratch home.

    uv run python scripts/journey_check.py --home F:/scratch/home --out F:/scratch/journey

It makes the home from the empty starter (refusing one that exists), starts the app on it,
captures invented sources, has the chosen CLI model distill them, approves what the review
shows without problems, then asks questions through Claude Code connected to the Brain's MCP
server alone (--strict-mcp-config: the person's own Claude settings are not read or changed).
Each answer is JSON with the notes it relied on. Checks cover who said what (an assistant's
suggestion against the owner's decision), current and earlier values, late old evidence,
partial totals with a repeated count, an unknown, a repeated request and a revoked note.

Every first answer and proposal is saved in --out/report.json for independent review: the
checks here are word and citation checks, not a judgment of the answers. The owner token is
read from the home into memory only. The sources are invented.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "server", "src"))

# Invented sources. Dates are the sources' own; the check's clock is irrelevant to them.
SOURCES = {
    "chat-0902": ("Chat with the assistant about the loyalty card", """\
Conversation, September 2, 2026. Dana Okoro (owner, Orchard Lane Bakery) and her AI assistant.

Assistant: For the new loyalty card, I would launch it in mid October, before the holidays.
Dana: No, October is too early, the cards will not be printed.
Dana: We will launch the loyalty card on November 3.
Assistant: Understood. Should it be 10 stamps for a free loaf?
Dana: Yes, 10 stamps for a free loaf. That is decided.
"""),
    "email-0910": ("Email: loyalty launch moves", """\
From: Dana Okoro
Date: September 10, 2026
Subject: Loyalty launch moves

Team, the printer is late, so the loyalty card launch moves from November 3 to November 17.
Everything else stays the same.
"""),
    "signups-0918": ("Loyalty sign-up counts", """\
Notes by Dana Okoro, September 18, 2026.

Loyalty sign-ups so far: Monday, 120 people signed up at the Main Street shop.
Wednesday, another 80 signed up at the Harbor shop.
The Thursday recap listed Main Street's 120 again; it is the same 120, not new people.
We have no count yet from the market stall.
"""),
    "old-0820": ("Old planning note", """\
Planning note, August 20, 2026, Dana Okoro.

Idea for now: launch the loyalty card on November 3. Price of the card not discussed.
"""),
}
FIRST = ["chat-0902", "email-0910", "signups-0918"]
LATE = "old-0820"

QUESTIONS = [
    ("current", "When does the Orchard Lane loyalty card launch?",
     {"all": ["17"], "none": ["october"], "cite": True}),
    ("history", "What was the loyalty card launch date before it moved, and why did it move?",
     {"all": ["3", "print"], "cite": True}),
    ("authority", "Did we adopt the assistant's idea of an October launch for the loyalty card?",
     {"any": ["no", "not adopted", "rejected", "declined"], "cite": True}),
    ("totals", "How many loyalty sign-ups do we have so far, across the shops?",
     {"any": ["200"], "none": ["320"], "cite": True}),
    ("unknown", "What price will the loyalty card cost customers?",
     {"unknown": True}),
]

ASK = """You answer for Dana Okoro of Orchard Lane Bakery. Before you answer, call the tool
mcp__contxt__get_task_context with the question as written, and read any note it lists that you
need with mcp__contxt__get_note. Answer only from what the Brain returns; if it does not say,
say it is not known.

Question: {question}

Reply with JSON only, no other text:
{{"answer": "one or two sentences", "cite": ["the note ids you relied on"], "unknown": false}}
Set "unknown" to true when the Brain does not hold the answer."""


def tool(name: str) -> str:
    """This environment's launcher for `name` (contxt, python), or a CLI on PATH."""
    folder = os.path.join(ROOT, ".venv", "Scripts" if os.name == "nt" else "bin")
    for candidate in (name + ".exe", name):
        if os.path.exists(os.path.join(folder, candidate)):
            return os.path.join(folder, candidate)
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} is not installed here.")
    return found


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


class App:
    def __init__(self, home: str, port: int):
        from workspace_server.settings import Settings
        self.base = f"http://127.0.0.1:{port}"
        self.proc = subprocess.Popen([tool("contxt"), "--home", home, "serve", "--port", str(port),
                                      "--no-open"], stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        token = Settings.from_env(home=home).resolved_owner_token()
        self.http = httpx.Client(base_url=self.base, timeout=120,
                                 headers={"Authorization": f"Bearer {token}"})
        for _ in range(90):
            try:
                if self.http.get("/api/health").status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(2)
        raise SystemExit("The app did not start.")

    def ok(self, response, code=200):
        if response.status_code != code:
            raise SystemExit(f"{response.request.method} {response.request.url.path} -> "
                             f"{response.status_code}: {response.text[:600]}")
        return response.json()

    def close(self):
        self.http.close()
        self.proc.terminate()
        try:
            self.proc.wait(20)
        except subprocess.TimeoutExpired:
            self.proc.kill()


def capture(app: App, key: str) -> str:
    title, text = SOURCES[key]
    found = app.ok(app.http.post("/api/captures", files={
        "file": (f"{key}.txt", text.encode("utf-8"), "text/plain")}, data={"title": title}), 201)
    return found["id"]


def distill(app: App, item_ids: list[str], runner: str) -> dict:
    task = app.ok(app.http.post("/api/brain/distill/requests", json={"item_ids": item_ids}), 201)
    run = app.ok(app.http.post(f"/api/runners/{runner}/runs", json={"task_id": task["id"]}), 201)
    deadline = time.monotonic() + 1200
    while time.monotonic() < deadline:
        found = app.ok(app.http.get(f"/api/runners/runs/{run['id']}"))
        if found["status"] not in ("starting", "running", "queued"):
            return {"task": task["id"], "status": found["status"],
                    "summary": found.get("summary")}
        time.sleep(10)
    raise SystemExit("The distill run did not finish in 20 minutes.")


def proposals_for(app: App, task_id: str) -> list[dict]:
    review = app.ok(app.http.get("/api/brain/review"))
    return [p for p in review.get("proposals") or [] if task_id in json.dumps(p)]


def describe(p: dict) -> dict:
    target = p.get("target") or {}
    analysis = p.get("analysis") or {}
    return {"id": p.get("id"), "title": target.get("title"),
            "kind": target.get("kind") or p.get("kind"), "said_by": target.get("said_by"),
            "as_of": target.get("as_of"), "source": target.get("source"),
            "evidence": target.get("evidence"), "text": p.get("body") or target.get("text"),
            "replaces": [e.get("id") for e in analysis.get("replaces") or []],
            "conflicts": [e.get("id") for e in analysis.get("conflicts") or []],
            "problems": analysis.get("problems")}


def approve(app: App, rows: list[dict]) -> list[str]:
    """Approve what the review shows, as an owner reading it would; its flagged problems stay
    in the report."""
    done = []
    for row in rows:
        out = app.http.post(f"/api/brain/proposals/{row['id']}/decide",
                            json={"approve": True, "reason": "journey check"})
        if out.status_code == 200:
            done.append(row["id"])
    return done


def ask(vault: str, question: str, model: str) -> dict:
    py = tool("python")
    config = {"mcpServers": {"contxt": {"command": py,
                                        "args": ["-m", "brainkit", "--vault", vault, "mcp"]}}}
    folder = tempfile.mkdtemp(prefix="journey-ask-")
    path = os.path.join(folder, "mcp.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle)
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("CLAUDECODE", "CLAUDE_CODE_", "MCP_", "CONTXT_", "BRAIN_"))}
    # The Brain server loads its meaning model before it answers; the account's own
    # claude.ai connectors stay out, so only the Brain's tools are offered.
    env.update({"MCP_TIMEOUT": "60000", "ENABLE_CLAUDEAI_MCP_SERVERS": "false"})
    try:
        done = subprocess.run(
            # The prompt goes on stdin: on Windows the CLI is a batch shim, and an argument
            # loses everything after its first line there.
            [shutil.which("claude") or "claude", "-p", "--model", model,
             "--mcp-config", path, "--strict-mcp-config", "--allowedTools", "mcp__contxt",
             "--output-format", "json"],
            input=ASK.format(question=question), capture_output=True, text=True,
            encoding="utf-8", timeout=600, env=env, cwd=folder)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    raw = done.stdout.strip()
    try:
        result = json.loads(raw).get("result") or ""
    except ValueError:
        result = raw
    start, end = result.find("{"), result.rfind("}")
    try:
        answer = json.loads(result[start:end + 1]) if start >= 0 else {}
    except ValueError:
        answer = {}
    return {"raw": result[:2000], "answer": answer, "error": done.stderr[-500:]
            if done.returncode else ""}


def grade(key: str, expect: dict, reply: dict, live_ids: set) -> dict:
    answer = reply.get("answer") or {}
    text = str(answer.get("answer") or "").lower()
    cites = [str(c) for c in answer.get("cite") or []]
    problems = []
    if not answer:
        problems.append("no JSON answer")
    for word in expect.get("all", []):
        if word.lower() not in text:
            problems.append(f"missing {word!r}")
    if expect.get("any") and not any(w.lower() in text for w in expect["any"]):
        problems.append(f"none of {expect['any']}")
    for word in expect.get("none", []):
        if word.lower() in text:
            problems.append(f"says {word!r}")
    if expect.get("cite"):
        if not cites:
            problems.append("cites nothing")
        bad = [c for c in cites if c not in live_ids]
        if bad:
            problems.append(f"cites unknown ids {bad}")
    if expect.get("unknown") is True and not answer.get("unknown"):
        problems.append("did not say it is not known")
    return {"question": key, "ok": not problems, "problems": problems, "cite": cites,
            "answer": answer.get("answer")}


def live_notes(vault: str) -> dict:
    from brainkit.api import Brain
    brain = Brain(vault, embeddings=False)
    try:
        return {n.id: n for n in brain.state().index.notes.values() if n.live}
    finally:
        brain.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--home", required=True, help="a scratch home to make (must not exist)")
    parser.add_argument("--out", required=True, help="where report.json goes")
    parser.add_argument("--port", type=int, default=8911)
    parser.add_argument("--runner", default="claude", help="the CLI that distills")
    parser.add_argument("--ask-model", default="haiku", help="the model that answers")
    parser.add_argument("--models", help="a folder holding the meaning model, copied in")
    args = parser.parse_args(argv)
    if os.path.exists(args.home):
        raise SystemExit("--home exists: this check only makes a new scratch home.")
    subprocess.run([tool("contxt"), "--home", args.home, "setup", "--brain", "empty", "--offline"],
                   check=True, stdout=subprocess.DEVNULL)
    vault = os.path.join(args.home, "brain", "vault")
    if args.models:
        shutil.copytree(args.models, os.path.join(vault, ".brain", "models"))
    os.makedirs(args.out, exist_ok=True)
    report: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%S"), "checks": {}}
    app = App(args.home, args.port)
    try:
        ids = {key: capture(app, key) for key in FIRST}
        log(f"captured {len(ids)} sources")
        first = distill(app, list(ids.values()), args.runner)
        rows = [describe(p) for p in proposals_for(app, first["task"])]
        report["first_run"] = dict(first, proposals=rows)
        log(f"distill: {first['status']}, {len(rows)} proposals")
        report["approved"] = approve(app, rows)
        # Authority: the assistant's October idea is never recorded as a decision.
        decided = [r for r in rows if "october" in str(r.get("text")).lower()
                   and r.get("kind") in ("decision", "rule") and "not" not in
                   str(r.get("text")).lower()]
        report["checks"]["assistant suggestion not adopted"] = not decided
        # A repeated request over the same sources proposes nothing new.
        again = distill(app, list(ids.values()), args.runner)
        repeats = proposals_for(app, again["task"])
        report["checks"]["repeat request adds nothing"] = not repeats
        report["repeat_run"] = dict(again, proposals=[describe(p) for p in repeats])
        # Late old evidence does not replace the current date.
        late = distill(app, [capture(app, LATE)], args.runner)
        late_rows = [describe(p) for p in proposals_for(app, late["task"])]
        report["late_run"] = dict(late, proposals=late_rows)
        report["approved"] += approve(app, [r for r in late_rows if not r.get("replaces")])
        notes = live_notes(vault)
        current = [n for n in notes.values() if "17" in n.body and "november" in
                   n.body.lower()]
        report["checks"]["late old evidence keeps November 17 current"] = bool(current)
        answers = []
        for key, question, expect in QUESTIONS:
            reply = ask(vault, question, args.ask_model)
            answers.append(dict(grade(key, expect, reply, set(notes)), raw=reply["raw"],
                                error=reply["error"]))
            log(f"asked {key}: {'ok' if answers[-1]['ok'] else answers[-1]['problems']}")
        # Revoke: the sign-up note is retired; the next answer must not use it.
        signups = [n.id for n in notes.values() if "120" in n.body and "80" in n.body]
        if signups:
            app.ok(app.http.post("/api/brain/decisions", json={"decisions": [
                {"action": "archive", "entry_id": i, "reason": "journey check: revoked"}
                for i in signups]}))
            reply = ask(vault, QUESTIONS[3][1], args.ask_model)
            graded = grade("revoked", {"unknown": True, "none": ["200"]}, reply,
                           set(live_notes(vault)))
            answers.append(dict(graded, raw=reply["raw"], error=reply["error"]))
            log(f"asked revoked: {'ok' if graded['ok'] else graded['problems']}")
        report["answers"] = answers
        report["checks"]["answers"] = {a["question"]: a["ok"] for a in answers}
    finally:
        app.close()
    report["passed"] = all(v if isinstance(v, bool) else all(v.values())
                           for v in report["checks"].values())
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False, default=str)
    log(f"checks: {json.dumps(report['checks'])}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
