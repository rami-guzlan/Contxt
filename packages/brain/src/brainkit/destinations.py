"""Where a distilled piece goes (Release 1 plan, M03): one inbox, five homes.

    note      a long-term note                     (governance.propose_note)
    kept      a rule, preference or fact kept with a project: a note filed in its folder
    sheet     one value in a context sheet: the row's cell, with history
    progress  a progress update in a project's journal
    task      a task in the Tasks sheet, linked to its project

A note or a kept item is an ordinary note proposal. A sheet value, a progress update and a
task are typed proposals in the same inbox (`sheet.write`, `project.progress`,
`task.create`), with the same source reference, statement status and operation id: they
wait like any proposal, and approving one writes it to its home. The owner can move a piece
before keeping it (`edits={"destination": ...}`): it is then kept at the new home, and its
source stays with it.
"""
from __future__ import annotations

from . import governance, statements, util

DESTINATIONS = ("note", "kept", "sheet", "progress", "task")
KINDS = {"sheet": "sheet.write", "progress": "project.progress", "task": "task.create"}
TYPED = set(KINDS.values())
GROUPS = {"rules": "rule", "preferences": "preference", "facts": "fact"}


def _result(message, data=None, is_error=False):
    return governance._result(message, data, is_error)


def _project(brain, name):
    from . import focus
    if not str(name or "").strip():
        return None, _result("Name the project it belongs to.", {"status": "invalid"}, True)
    return focus.resolve(brain, name)


def propose(brain, destination, text, *, principal=None, session_id=None, reason="",
            op_id=None, source_id=None, source_version=None, source_locator=None,
            source_speaker=None, source_excerpt=None, as_of=None, **fields):
    """Propose one piece for one home. `fields` are the home's own: `area`, `topic`, `title`
    and `kind` for a note; `project` and `group` (rules, preferences, facts) for a kept item;
    `sheet`, `row`, `column` and `value` for a sheet; `project` and `next_up` for progress;
    `project`, `due` and `owner` for a task."""
    destination = str(destination or "").strip().lower()
    text = str(text or "").strip()
    cited = dict(source_id=source_id, source_version=source_version,
                 source_locator=source_locator, source_speaker=source_speaker,
                 source_excerpt=source_excerpt)
    if destination not in DESTINATIONS:
        return _result(f"Destination is one of {', '.join(DESTINATIONS)}.",
                       {"status": "invalid"}, True)
    if not text:
        return _result("Say the piece in a sentence.", {"status": "invalid"}, True)
    if destination == "note":
        return governance.propose_note(
            brain, area=fields.get("area"), topic=fields.get("topic"), text=text,
            title=fields.get("title"), note_kind=fields.get("kind"), principal=principal,
            session_id=session_id, reason=reason, op_id=op_id, as_of=as_of,
            force_pending=True, **cited)
    if destination == "kept":
        project, refusal = _project(brain, fields.get("project"))
        if refusal:
            return refusal
        group = str(fields.get("group") or "facts").strip().lower()
        if group not in GROUPS:
            return _result(f"A kept item is one of {', '.join(GROUPS)}.",
                           {"status": "invalid"}, True)
        return governance.propose_note(
            brain, area=project.note.area, topic=project.note.topic, text=text,
            title=fields.get("title"), note_kind=GROUPS[group], principal=principal,
            session_id=session_id, reason=reason, op_id=op_id, as_of=as_of,
            force_pending=True, extra={"project_id": project.id, "kept_group": group},
            **cited)
    problems: list[str] = []
    source = governance.source_fields(*cited.values(), problems)
    if problems:
        return _result("Proposal refused: " + "; ".join(problems) + ".",
                       {"status": "invalid", "problems": problems}, True)
    target, refusal = _target(brain, destination, fields)
    if refusal:
        return refusal
    st = brain.state()
    op_id = str(op_id or "").strip()
    if op_id:
        done = governance.same_operation(st, op_id)
        if done is not None:
            return done
    if as_of:
        found = util.parse_date(as_of)
        if found is None:
            return _result("as_of is a date (YYYY-MM-DD).", {"status": "invalid"}, True)
        target["as_of"] = found.isoformat()
    target.update(source)
    target["statement_status"] = statements.statement_status(
        source.get("source_excerpt") or text)
    target["title"] = str(fields.get("title") or "").strip() or governance.title_from(text)
    if op_id:
        target["op_id"] = op_id
    kind = KINDS[destination]
    who = brain.principal(principal)
    proposal_id = f"{kind.replace('.', '-')}-{util.short_hash(text + util.now_iso(), 6)}"
    header = {"kind": kind, "status": "pending", "created": util.now_iso(), "proposer": who,
              "reason": reason or "", "session": session_id or ""}
    relpath = brain.vault.write_proposal(proposal_id, header, target, text)
    brain.after_write([brain.vault.path(relpath)], f"Propose {kind} {target['title']}")
    return _result(f"Proposed: {label(kind, target)}. It waits for review.",
                   {"status": "pending", "proposal_id": proposal_id, "path": relpath})


def _target(brain, destination, fields):
    """The home of a sheet value, a progress update or a task, checked now."""
    from . import state
    if destination == "sheet":
        sheet_id = str(fields.get("sheet") or "").strip()
        found = state.sheet(brain, sheet_id)
        if found is None:
            return None, _result(f"No sheet {sheet_id!r}.", {"status": "invalid"}, True)
        column = found.column(str(fields.get("column") or ""))
        if column is None or column.computed:
            return None, _result(f"{found.title} has no column {fields.get('column')!r} "
                                 "anyone writes.", {"status": "invalid"}, True)
        row = str(fields.get("row") or "").strip()
        if not row:
            return None, _result(f"Name the row ({found.key}).", {"status": "invalid"}, True)
        value = fields.get("value")
        if value is None or str(value).strip() == "":
            return None, _result("Give the value.", {"status": "invalid"}, True)
        return {"sheet": found.id, "sheet_title": found.title, "row": row,
                "column": column.name, "value": str(value).strip(),
                "new_row": state.find_row(brain, found.id, row) is None}, None
    project, refusal = _project(brain, fields.get("project"))
    if refusal:
        return None, refusal
    target = {"project": project.id, "project_title": project.title}
    if destination == "progress":
        target["next_up"] = " ".join(str(fields.get("next_up") or "").split())[:300]
    else:
        for key in ("due", "owner"):
            if str(fields.get(key) or "").strip():
                target[key] = " ".join(str(fields[key]).split())[:120]
    return target, None


def label(kind, target) -> str:
    """Where a proposal would go, in the app's words: Sheet › Row › Column."""
    if kind == "sheet.write":
        return f"{target.get('sheet_title') or target.get('sheet')} › {target.get('row')} › " \
               f"{target.get('column')}"
    if kind == "project.progress":
        return f"{target.get('project_title') or target.get('project')} › Progress"
    if kind == "task.create":
        return f"{target.get('project_title') or target.get('project')} › Tasks"
    if target.get("kept_group"):
        return f"{target.get('area')}/{target.get('topic')} › Kept with it › " \
               f"{target['kept_group']}"
    return f"{target.get('area') or target.get('layer')}/{target.get('topic')}"


def apply(brain, proposal, *, actor, edits=None, body=None):
    """Keep a typed proposal at its home, or at the one the owner moved it to."""
    edits = dict(edits or {})
    text = proposal.body.strip() if body is None else str(body).strip()
    moved = str(edits.pop("destination", "") or "").strip().lower()
    current = next((d for d, k in KINDS.items() if k == proposal.kind), "note")
    target = dict(proposal.target)
    cited = {k: target.get(k) for k in governance.SOURCE_KEYS}
    if moved and moved != current:
        made = propose(brain, moved, text, principal=actor, reason=f"moved from "
                       f"{label(proposal.kind, target)}", as_of=target.get("as_of"),
                       **cited, **edits)
        if made.is_error:
            return made
        kept = (governance.approve(brain, made.data["proposal_id"], actor=actor)
                if made.data.get("proposal_id") else made)
        if not kept.is_error:
            _close(brain, proposal, actor, f"kept as {moved}: {kept.data.get('id') or ''}")
        return kept
    target.update({k: v for k, v in edits.items() if k in ("value", "row", "column",
                                                           "next_up", "due", "owner")})
    source = "; ".join(str(v) for v in (cited.get("source_id"), cited.get("source_locator"))
                       if v) or "proposal"
    said = "owner" if body is not None and text != proposal.body.strip() else (
        "person" if cited.get("source_speaker") not in (None, "", "unknown") else "agent")
    done = _write(brain, proposal.kind, target, text, actor=actor, said_by=said,
                  source=f"{source} ({proposal.id})")
    if not done.is_error:
        _close(brain, proposal, actor, done.text)
    return done


def _write(brain, kind, target, text, *, actor, said_by, source):
    from . import focus, handoff, state
    if kind == "sheet.write":
        values = {target["column"]: target["value"]}
        if state.find_row(brain, target["sheet"], target["row"]) is None:
            return state.add_row(brain, target["sheet"], target["row"], values, who=actor,
                                 said_by=said_by, source=source)
        return state.write(brain, target["sheet"], target["row"], values, who=actor,
                           said_by=said_by, source=source, as_of=target.get("as_of") or "")
    if kind == "project.progress":
        changes = {"next": target["next_up"]} if target.get("next_up") else None
        return focus.record_update(brain, target["project"], text, changes,
                                   principal=actor, evidence=source)
    spec = {"title": text, "project": target["project"]}
    if target.get("due"):
        spec["due"] = target["due"]
    return handoff.hand_off(brain, new_task=spec, acting_for=actor, reason=source)


def _close(brain, proposal, actor, outcome):
    record = {"at": util.now_iso(), "action": "approved", "by": actor, "proposal": proposal.id,
              "kind": proposal.kind, "outcome": outcome, "target": proposal.target,
              "body": proposal.body, "proposer": proposal.proposer,
              "session": str(proposal.meta.get("session") or ""),
              "created": str(proposal.created or "")}
    decisions = brain.vault.append_decision(record)
    brain.vault.remove_file(proposal.path)
    brain.after_write([brain.vault.path(decisions), brain.vault.path(proposal.path)],
                      f"Keep {proposal.id}")
