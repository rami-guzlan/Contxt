#!/usr/bin/env python3
"""Hooks that keep a run the app starts on its contract (Claude Code reads them from a
run-scoped settings file the app passes with `--settings`).

    python -m brainkit.hooks.run scope  --contract <path>    PreToolUse
    python -m brainkit.hooks.run anchor --contract <path>    PostToolUse
    python -m brainkit.hooks.run gate   --contract <path>    Stop

THE CONTRACT, written by the app when the run starts: the objective, the checks the run must
pass, the must-holds of the task's domains (each with its line and trigger words), the run's
scope (the one folder it may touch, when it works with files) and its budget (tool calls and
minutes). Each hook appends what it did to the contract's event file; the app reads that into
the run's record when the run ends.

SCOPE, before each tool call: a call past the step budget is refused, except the calls that
finish the run; a file outside the run's folder is refused; a shell command the guard
patterns name (patterns.txt) is refused.

ANCHOR, after each tool call: every `every` calls the contract comes back as context, and as
soon as a tool's input or output uses a must-hold's trigger, that must-hold's line comes back.

GATE, when the run would stop: if the finishing call never came (complete_task, or a blocker
through append_task_event), the run is sent back once with what is missing; the second time it
may stop, and its record says the check failed.

A hook that cannot read its contract does nothing: it never breaks a run.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

# The calls that end a run's work: it finished, or it said why it cannot.
FINISH = ("complete_task", "append_task_event")
FILE_TOOLS = ("Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
REPEAT = 4  # a must-hold's line comes back at most once in this many tool calls


def _short(tool) -> str:
    """"mcp__contxt-app__complete_task" is complete_task."""
    return str(tool or "").rsplit("__", 1)[-1]


def _state(contract) -> dict:
    try:
        with open(contract["state"], encoding="utf-8") as handle:
            found = json.load(handle)
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _save(contract, state) -> None:
    path = contract.get("state")
    if not path:
        return
    from brainkit import util  # light: the hook stays quick

    temporary = f"{path}.{os.getpid()}.tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    util.replace(temporary, path)


def _log(contract, **record) -> None:
    path = contract.get("events")
    if not path:
        return
    record["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _patterns() -> list[str]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "patterns.txt")
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.strip() for line in handle
                    if line.strip() and not line.lstrip().startswith("#")]
    except OSError:
        return []


def _inside(path: str, folder: str) -> bool:
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(folder, path))
    root = os.path.realpath(folder)
    try:
        return os.path.commonpath([full, root]) == root
    except ValueError:  # another drive
        return False


def refusal(contract, steps: int, tool: str, args: dict) -> str | None:
    """Why this tool call is out of the run's contract, or None."""
    budget = int((contract.get("budget") or {}).get("steps") or 0)
    if budget and steps > budget and _short(tool) not in FINISH:
        return (f"The run's budget of {budget} tool calls is used. Finish now: call "
                "complete_task with a one-line summary of what is done, or append_task_event "
                "with a blocker.")
    folder = (contract.get("scope") or {}).get("folder")
    path = str(args.get("file_path") or args.get("path") or args.get("notebook_path") or "")
    if folder and path and tool in FILE_TOOLS and not _inside(path, folder):
        return f"{path} is outside this run's folder: work only in {folder}."
    if tool in SHELL_TOOLS:
        command = str(args.get("command") or "")
        for pattern in _patterns():
            try:
                if re.search(pattern, command):
                    return ("That command needs a person's approval, so a run never makes it "
                            f"({pattern}).")
            except re.error:
                continue
    return None


def scope(contract, payload) -> dict | None:
    state = _state(contract)
    tool = str(payload.get("tool_name") or "")
    state["steps"] = int(state.get("steps") or 0) + 1
    state.setdefault("tools", []).append(_short(tool))
    _save(contract, state)
    why = refusal(contract, state["steps"], tool, payload.get("tool_input") or {})
    if not why:
        return None
    _log(contract, event="blocked", tool=_short(tool), why=why, step=state["steps"])
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": why}}


def _mentions(text: str, trigger: str) -> bool:
    words = [re.escape(w) for w in str(trigger or "").lower().split()]
    return bool(words) and re.search(r"\b" + r"\s+".join(words) + r"\w*", text) is not None


def digest(contract, step: int | None = None) -> str:
    """The contract in a few lines: what the run is for, what must hold, how to finish."""
    head = "Run contract" + (f", after {step} tool calls" if step else "")
    lines = [f"{head}: {contract.get('objective') or 'the task you claimed'}"]
    lines += [f"- {check}" for check in contract.get("checks") or []]
    lines += [f"- Must hold: {item['line']} (`{item['id']}`)"
              for item in contract.get("must_holds") or []]
    budget = contract.get("budget") or {}
    if budget.get("steps") or budget.get("minutes"):
        lines.append(f"- Budget: at most {budget.get('steps')} tool calls and "
                     f"{budget.get('minutes')} minutes.")
    return "\n".join(lines)


def anchor(contract, payload) -> dict | None:
    state = _state(contract)
    step = int(state.get("steps") or 0)
    seen = (json.dumps(payload.get("tool_input") or {}, ensure_ascii=False) + " "
            + json.dumps(payload.get("tool_response") or "", ensure_ascii=False)[:20000]).lower()
    anchored = state.setdefault("anchored", {})
    lines = []
    for item in contract.get("must_holds") or []:
        hit = next((t for t in item.get("triggers") or [] if _mentions(seen, t)), None)
        if hit and step - int(anchored.get(item["id"], -REPEAT)) >= REPEAT:
            anchored[item["id"]] = step
            lines.append(f"Must hold here ({hit}): {item['line']} (`{item['id']}`)")
            _log(contract, event="anchor", why=f"must-hold {item['id']}", step=step)
    every = int(contract.get("every") or 0)
    if every and step and step % every == 0:
        lines.append(digest(contract, step))
        _log(contract, event="anchor", why="cadence", step=step)
    _save(contract, state)
    if not lines:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n".join(lines)}}


def gate(contract, payload) -> dict | None:
    used = set(_state(contract).get("tools") or [])
    missing = [check["check"] for check in contract.get("finish") or []
               if not set(check.get("any") or []) & used]
    if missing and not payload.get("stop_hook_active"):
        _log(contract, event="gate", passed=False, missing=missing, sent_back=True)
        return {"decision": "block",
                "reason": "Before you stop, the run's contract asks for this: "
                          + "; ".join(missing) + "."}
    _log(contract, event="gate", passed=not missing, missing=missing, sent_back=False)
    return None


MODES = {"scope": scope, "anchor": anchor, "gate": gate}


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    mode = args[0] if args else ""
    path = args[args.index("--contract") + 1] if "--contract" in args[:-1] else ""
    try:
        payload = json.load(sys.stdin)
    except (ValueError, OSError):
        payload = {}
    try:
        with open(path, encoding="utf-8") as handle:
            contract = json.load(handle)
        out = MODES[mode](contract, payload if isinstance(payload, dict) else {})
    except Exception:  # no contract, a full disk, a bad mode: the run goes on
        return 0
    if out:
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
