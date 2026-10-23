"""Agents: roles written like a job description, kept in the Brain.

An agent is `agents/<name>/AGENT.md`. Its front matter is the role: a line saying what it does,
what it is responsible for, the goals it serves and the projects it works on, what it points to
(skills, Library documents, Brain areas and topics, recent meetings), what it never does, where
its work goes and in what shape, how it runs, and whether what it makes waits for review. Its
body is the operating prompt the owner saved (written with a model's help in the app, read and
edited by the owner before saving).

POINT, DON'T ATTACH. An agent names what it needs and never holds copies. `assemble` resolves
the names to what each is now (a skill's one line, a document's title, a project's state), so
an agent never works from a stale copy, and names what no longer resolves (a deleted skill, a
moved document) so the owner can fix the pointer. Its brief for a task is the Brain's packet
for that task, fetched when the task starts.

GOVERNED. Saving is the owner's change: applied at once as one undo point and one commit, with
every version in git (`versions`). Archiving keeps the file (status: archived) and hides the
agent from listings. An agent's scope says who may use it, as a skill's does (the team edition).
"""
from __future__ import annotations

import os
import re

from . import frontmatter as fm
from . import util
from .scopes import Scopes

FOLDER = "agents"
NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
LIST_FIELDS = ("responsibilities", "goals", "projects", "skills", "library", "context",
               "boundaries")
OUTPUTS = ("outputs", "workspace", "proposals")
RUNNERS = ("claude", "codex", "any")  # or ollama:<model>, a local model by name
LOCAL = re.compile(r"^ollama:[A-Za-z0-9._:/-]{1,80}$")
ORDER = ("name", "role", "responsibilities", "goals", "projects", "skills", "library", "context",
         "meetings_days", "boundaries", "output", "output_shape", "runner", "review", "scope",
         "status")
DEFAULT_BOUNDARIES = (
    "Never publish, send or post anything: leave drafts for the owner.",
    "Never change the Brain directly: propose a change and say why.",
)
MAX_BODY = 30_000
MAX_ITEMS = 20
MAX_LINE = 300
MAX_MEETING_DAYS = 90
WORK_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin", "work")
WORK_SKILLS = ("agent-builder", "prompt-improver")


def _result(message, data=None, is_error=False):
    from .api import Result
    return Result(message, data or {}, is_error)


def relpath(name: str) -> str:
    return f"{FOLDER}/{name}/AGENT.md"


def _names(brain) -> list[str]:
    root = brain.vault.path(FOLDER)
    if not os.path.isdir(root):
        return []
    return sorted(n for n in os.listdir(root)
                  if NAME.match(n) and os.path.isfile(os.path.join(root, n, "AGENT.md")))


def _read(brain, name: str):
    full = brain.vault.path(FOLDER, name, "AGENT.md")
    if not os.path.isfile(full):
        return None
    meta, body, _errors = fm.parse(util.read_text(full))
    return meta, body


def _int(value, default=0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _shape(name: str, meta: dict, body: str) -> dict:
    """An agent as the app and the tools see it."""
    out = {
        "name": name,
        "role": str(meta.get("role") or ""),
        "meetings_days": _int(meta.get("meetings_days")),
        "output": str(meta.get("output") or "outputs"),
        "output_shape": str(meta.get("output_shape") or ""),
        "runner": str(meta.get("runner") or "claude"),
        "review": fm.as_bool(meta.get("review")) if "review" in meta else True,
        "scope": str(meta.get("scope") or ""),
        "status": str(meta.get("status") or "active"),
        "prompt": str(body or "").strip(),
        "path": relpath(name),
    }
    for key in LIST_FIELDS:
        out[key] = [str(x) for x in fm.as_list(meta.get(key)) if str(x).strip()]
    return out


def _visible(meta: dict, chain, partitions) -> bool:
    scope = str(meta.get("scope") or "").strip()
    return not scope or Scopes.admits(scope, None, chain, partitions)


def list_agents(brain, chain, partitions, *, archived=False) -> list[dict]:
    """The agents this caller may see, by name; archived ones only when asked for."""
    out = []
    for name in _names(brain):
        found = _read(brain, name)
        if found is None or not _visible(found[0], chain, partitions):
            continue
        agent = _shape(name, *found)
        if agent["status"] == "archived" and not archived:
            continue
        out.append(agent)
    return out


def get(brain, name, chain, partitions) -> dict | None:
    wanted = str(name or "").strip().lower()
    if not NAME.match(wanted):
        return None
    found = _read(brain, wanted)
    if found is None or not _visible(found[0], chain, partitions):
        return None
    return _shape(wanted, *found)


def check(st, fields: dict) -> tuple[dict, list[str]]:
    """The form's fields, cleaned, and what is wrong with them. A pointer to something that
    does not exist yet is not wrong: `assemble` says it does not resolve."""
    problems: list[str] = []
    meta: dict = {}
    role = " ".join(str(fields.get("role") or "").split())
    if not role:
        problems.append("say in a line what it does (role)")
    meta["role"] = role[:MAX_LINE]
    for key in LIST_FIELDS:
        items = [" ".join(str(x).split())[:MAX_LINE] for x in fm.as_list(fields.get(key))
                 if str(x).strip()]
        if len(items) > MAX_ITEMS:
            problems.append(f"{key}: at most {MAX_ITEMS}")
        if items:
            meta[key] = list(dict.fromkeys(items))[:MAX_ITEMS]
    if not meta.get("boundaries"):
        meta["boundaries"] = list(DEFAULT_BOUNDARIES)
    days = _int(fields.get("meetings_days"), -1) if fields.get("meetings_days") not in (
        None, "") else 0
    if not 0 <= days <= MAX_MEETING_DAYS:
        problems.append(f"meetings_days is a number of days from 0 to {MAX_MEETING_DAYS}")
    elif days:
        meta["meetings_days"] = days
    output = str(fields.get("output") or "outputs").strip()
    if output not in OUTPUTS:
        problems.append(f"output is one of {', '.join(OUTPUTS)}")
    meta["output"] = output
    shape = " ".join(str(fields.get("output_shape") or "").split())
    if shape:
        meta["output_shape"] = shape[:500]
    runner = str(fields.get("runner") or "claude").strip()
    if runner not in RUNNERS and not LOCAL.match(runner):
        problems.append("runner is claude, codex, any, or ollama:<model>")
    meta["runner"] = runner
    meta["review"] = bool(fm.as_bool(fields.get("review"))) if "review" in fields else True
    scope = str(fields.get("scope") or "").strip()
    if scope:
        if not st.scopes.exists(scope):
            problems.append(f"scope {scope!r} is not declared in brain.json")
        meta["scope"] = scope
    return meta, problems


def save(brain, name, fields, prompt, *, actor=None, label=None):
    """Create or change an agent: the owner's change, applied at once as one undo point."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    wanted = str(name or "").strip().lower()
    if not NAME.match(wanted):
        return _result("An agent's name is lowercase words joined by hyphens, such as "
                       "content-strategist.", {"status": "invalid"}, True)
    st = brain.state()
    meta, problems = check(st, dict(fields or {}))
    body = str(prompt or "").strip()
    if len(body) > MAX_BODY:
        problems.append(f"the prompt is at most {MAX_BODY:,} characters")
    if problems:
        return _result("Not saved: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    found = _read(brain, wanted)
    verb = "Changed" if found else "Made"
    message = str(label or f"{verb} the agent {wanted}")[:200]
    text = fm.dump({"name": wanted, **meta}, body + "\n" if body else "", order=ORDER)
    return _write(brain, wanted, text, who=who, message=message,
                  action="edited" if found else "approved", verb=verb)


def archive(brain, name, *, actor=None):
    """Hide an agent: its file stays (status: archived), with an undo point."""
    from . import governance
    who, refusal = governance._require_approver(brain, actor)
    if refusal:
        return refusal
    wanted = str(name or "").strip().lower()
    found = _read(brain, wanted) if NAME.match(wanted) else None
    if found is None:
        return _result(f"No agent named {wanted!r}.", {"status": "missing"}, True)
    meta, body = found
    if str(meta.get("status") or "") == "archived":
        return _result(f"The agent {wanted} is already archived.", {"status": "unchanged"})
    text = fm.dump(dict(meta, status="archived"), body, order=ORDER)
    return _write(brain, wanted, text, who=who, message=f"Archived the agent {wanted}",
                  action="archived", verb="Archived")


def _write(brain, name, text, *, who, message, action, verb):
    from . import checkpoints
    full = brain.vault.path(FOLDER, name, "AGENT.md")
    with checkpoints.batch(brain, actor=who, label=message, source={"agent": name}) as batch:
        with brain.deferring() as deferred:
            deferred.message = message
            brain.vault.touch(full)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            util.atomic_write(full, text)
            brain.vault.append_decision({"at": util.now_iso(), "action": f"agent_{action}",
                                         "by": who, "agent": name, "path": relpath(name)})
            brain.after_write([full], message)
            batch.decisions.append({"action": action, "id": relpath(name),
                                    "title": f"Agent {name}"})
    return _result(f"{verb} the agent {name}.", {
        "status": "saved", "name": name, "path": relpath(name),
        "checkpoint": batch.checkpoint, "commit": (deferred.outcome or {}).get("commit")})


def versions(brain, name, *, limit=30, with_text=False) -> list[dict] | None:
    """Every saved version of an agent, newest first, from git."""
    from . import history
    wanted = str(name or "").strip().lower()
    if not NAME.match(wanted) or _read(brain, wanted) is None:
        return None
    return history.file_versions(brain, relpath(wanted), limit=limit, with_text=with_text)


def _first_sentence(text: str, limit=160) -> str:
    found = re.match(r"(.+?[.!?])(\s|$)", " ".join(str(text or "").split()))
    return util.excerpt(found.group(1) if found else str(text or ""), limit)


def resolve(brain, agent: dict, chain, partitions) -> dict:
    """What each of the agent's pointers is now, and which no longer resolve."""
    st = brain.state()
    index = st.index
    skills = []
    for name in agent["skills"]:
        skill = index.skills.get(name.lstrip("/"))
        seen = skill is not None and Scopes.admits(skill.scope, skill.partition, chain,
                                                   partitions)
        skills.append({"name": name.lstrip("/"), "missing": not seen,
                       "description": _first_sentence(skill.description) if seen else ""})
    library = []
    for path in agent["library"]:
        here = path in index.references
        library.append({"path": path, "missing": not here,
                        "title": index.file_title(path) if here else path})
    areas = set(st.config.areas or {})
    context = []
    for key in agent["context"]:
        known = key in index.topics or key in areas or any(
            str(t).startswith(f"{key}/") for t in index.topics)
        context.append({"key": key, "missing": not known})
    projects = []
    for wanted in agent["projects"]:
        focus = index.focuses.get(wanted) or next(
            (f for f in index.focuses.values()
             if util.normalize(wanted) in {util.normalize(v) for v in [f.slug, f.title]}), None)
        if focus is None or not Scopes.admits(focus.note.scope, focus.note.partition, chain,
                                              partitions):
            projects.append({"id": wanted, "title": wanted, "missing": True})
            continue
        state = focus.current()
        projects.append({"id": focus.id, "title": focus.title, "missing": False,
                         "status": state.get("status"), "current": state.get("current"),
                         "next": state.get("next")})
    broken = ([f"/{s['name']}" for s in skills if s["missing"]]
              + [d["path"] for d in library if d["missing"]]
              + [c["key"] for c in context if c["missing"]]
              + [p["id"] for p in projects if p["missing"]])
    return {"skills": skills, "library": library, "context": context, "projects": projects,
            "broken": broken}


OUTPUT_WORDS = {
    "outputs": "Save what you make as the result of the task; it lands in the owner's outputs "
               "folder and waits for their look.",
    "workspace": "What you make goes back to the owner's Workspace as a draft for them to "
                 "read and edit.",
    "proposals": "What you learn that should last goes to the Brain as proposals, each with "
                 "its reason; nothing changes until the owner says yes.",
}


def assemble(brain, agent: dict, resolved: dict) -> str:
    """The agent's role as a model gets it: who it is, its operating prompt, what it points
    to as each is now, its boundaries and where its work goes. The brief for a task is added
    when the task starts."""
    lines = [f"# You are working as {agent['name']}", ""]
    if agent["role"]:
        lines += [agent["role"], ""]
    if agent["prompt"]:
        lines += [agent["prompt"], ""]
    if agent["responsibilities"]:
        lines += ["## What you are responsible for", ""]
        lines += [f"- {r}" for r in agent["responsibilities"]] + [""]
    if agent["goals"]:
        lines += ["## The goals your work serves", ""]
        lines += [f"- {g}" for g in agent["goals"]] + [""]
    pointers = []
    live_skills = [s for s in resolved["skills"] if not s["missing"]]
    if live_skills:
        pointers.append("Skills to follow (open each in full with skills_get before you use "
                        "it): " + "; ".join(
                            f"/{s['name']}" + (f" ({s['description']})" if s["description"]
                                               else "") for s in live_skills) + ".")
    live_docs = [d for d in resolved["library"] if not d["missing"]]
    if live_docs:
        pointers.append("Library documents to read whole (files_open): " + "; ".join(
            f"{d['title']} ({d['path']})" for d in live_docs) + ".")
    live_context = [c["key"] for c in resolved["context"] if not c["missing"]]
    if live_context:
        pointers.append("Your context in the Brain: " + ", ".join(live_context) + ". The "
                        "brief for each task brings what fits from there; notes_search "
                        "finds more.")
    for project in resolved["projects"]:
        if project["missing"]:
            continue
        state = "; ".join(f"{k}: {util.excerpt(str(v), 160)}" for k, v in (
            ("status", project.get("status")), ("where it stands", project.get("current")),
            ("next", project.get("next"))) if v)
        pointers.append(f"Project {project['title']} ({project['id']})"
                        + (f", as it stands now: {state}." if state else "."))
    if agent["meetings_days"]:
        pointers.append(f"Recent meetings: what was recorded in the last "
                        f"{agent['meetings_days']} days for your projects, when the task "
                        "pins it.")
    if pointers:
        lines += ["## What you point to (read the current versions; never rely on a copy)",
                  ""] + [f"- {p}" for p in pointers] + [""]
    if resolved["broken"]:
        lines += ["Some pointers no longer resolve: " + ", ".join(resolved["broken"])
                  + ". Say so in your result instead of guessing.", ""]
    lines += ["## What you never do", ""]
    lines += [f"- {b}" for b in agent["boundaries"] or DEFAULT_BOUNDARIES] + [""]
    lines += ["## Where your work goes", "", OUTPUT_WORDS.get(agent["output"],
                                                              OUTPUT_WORDS["outputs"])]
    if agent["output_shape"]:
        lines += ["", f"Its shape: {agent['output_shape']}"]
    if agent["review"]:
        lines += ["", "The owner reviews what you make before anything is used."]
    return "\n".join(lines).strip() + "\n"


def work_skill_text(brain, name: str) -> str | None:
    """A procedure Work follows with a model (writing an agent's prompt, improving one): the
    brain's own skill of that name, else the one the engine ships."""
    wanted = str(name or "").strip().lstrip("/")
    if wanted not in WORK_SKILLS:
        return None
    own = brain.state().index.skills.get(wanted) if brain is not None else None
    if own is not None:
        return own.body
    path = os.path.join(WORK_FOLDER, wanted, "SKILL.md")
    if not os.path.isfile(path):
        return None
    _meta, body, _errors = fm.parse(util.read_text(path))
    return body
