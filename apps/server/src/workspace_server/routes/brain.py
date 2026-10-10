"""The Brain over REST: browse it, read and add its files, follow its projects, review what
waits, and ask a model to find what to remember."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Query, Response, UploadFile

from workspace_core.domain.records import Task
from workspace_core.errors import NotFound, ValidationFailed
from workspace_core.services.brain import MAX_FILE

from ..deps import WS, Who
from ..movein_files import UploadReader
from ..schemas import (
    BrainDecisionIn,
    BrainProjectIn,
    BuiltinSkillsIn,
    CatchUpItemIn,
    DecisionsIn,
    DistillRequestIn,
    DistillSettingsIn,
    GapIn,
    GoalsIn,
    LocalModelsIn,
    MarkIn,
    MergeIn,
    MoveInIn,
    PoliciesIn,
    ProjectUpdateIn,
    ProposalIn,
    ReconcileIn,
    ReplayIn,
    RequestLabelsIn,
    VerifyIn,
)

router = APIRouter(prefix="/api/brain")
MAX_MOVE_IN_FILES = 8  # at a time, as many as Moving in reads
MAX_MOVE_IN_UPLOAD = 100 * 1024 * 1024  # one file or zip


@router.get("/status")
def status(who: Who, ws: WS) -> dict[str, Any]:
    return ws.brain.status(who)


@router.get("/catalog")
def catalog(who: Who, ws: WS) -> dict[str, Any]:
    """Every entry the Brain holds, with its areas and topics: browse it without searching."""
    return asdict(ws.brain.catalog(who))


@router.get("/search")
def search(q: str, who: Who, ws: WS, limit: int = 10) -> list[dict[str, Any]]:
    return [asdict(h) for h in ws.brain.search(who, q, limit)]


@router.get("/entries/{entry_id}")
def entry(entry_id: str, who: Who, ws: WS) -> dict[str, Any]:
    found = ws.brain.entry(who, entry_id)
    if found is None:
        raise NotFound(f"No Brain entry {entry_id}.")
    return asdict(found)


@router.get("/entries/{entry_id}/history")
def history(entry_id: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    return ws.brain.history(who, entry_id)


@router.post("/entries/{entry_id}/verify")
def verify(entry_id: str, body: VerifyIn, who: Who, ws: WS) -> dict[str, Any]:
    """Confirm an entry is still true today: it stops being stale."""
    return asdict(ws.brain.verify(who, entry_id, confidence=body.confidence))


@router.post("/entries/{entry_id}/mark")
def mark(entry_id: str, body: MarkIn, who: Who, ws: WS) -> dict[str, Any]:
    """Mark an entry stale (it needs an update) or disputed, saying why; it stays, ranked
    lower and flagged in packets."""
    return asdict(ws.brain.mark(who, entry_id, body.state, reason=body.reason))


# ------------------------------------------------------------------------- supply chain


@router.get("/inventory")
def inventory(who: Who, ws: WS) -> list[dict[str, Any]]:
    """Everything the Brain holds, as one table: entries (live and archived), skills and filed
    documents, each with its owner, origin, checks, sensitivity, changes and use."""
    return ws.brain.inventory(who)


@router.get("/entries/{entry_id}/details")
def entry_details(entry_id: str, who: Who, ws: WS) -> dict[str, Any]:
    """One entry's row in the inventory."""
    return ws.brain.entry_details(who, entry_id)


@router.get("/entries/{entry_id}/versions")
def versions(entry_id: str, who: Who, ws: WS, text: bool = False) -> list[dict[str, Any]]:
    """Every version of an entry, newest first, each with who made it and why."""
    return ws.brain.versions(who, entry_id, with_text=text)


@router.get("/entries/{entry_id}/versions/{ref}")
def version(entry_id: str, ref: str, who: Who, ws: WS) -> dict[str, Any]:
    return ws.brain.version(who, entry_id, ref)


@router.get("/entries/{entry_id}/use")
def use(entry_id: str, who: Who, ws: WS, days: int = 90) -> dict[str, Any]:
    """Where an entry went: by day, in total, and each recent handout."""
    return ws.brain.use(who, entry_id, days=days)


@router.get("/activity")
def activity(
    who: Who,
    ws: WS,
    entry: str | None = None,
    since: str | None = None,
    until: str | None = None,
    action: Annotated[list[str] | None, Query()] = None,
    by: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Every governed event, newest first, filtered by entry, time, action and who."""
    return ws.brain.activity(
        who, entry_id=entry, since=since, until=until, actions=action, by=by, limit=limit
    )


@router.get("/flow")
def flow(who: Who, ws: WS, days: int = 7) -> dict[str, Any]:
    """The supply chain over `days`: came in, decided, waiting, handed out, stock health."""
    return ws.brain.flow(who, days=days)


@router.get("/gaps")
def gaps(who: Who, ws: WS, days: int = 30) -> list[dict[str, Any]]:
    """Requests the Brain served poorly: nothing matched, or routing missed an entry."""
    return ws.brain.gaps(who, days=days)


@router.post("/gaps/dismiss", status_code=204)
def dismiss_gap(body: GapIn, who: Who, ws: WS) -> Response:
    ws.brain.dismiss_gap(who, body.key)
    return Response(status_code=204)


@router.get("/policies")
def policies(who: Who, ws: WS) -> dict[str, Any]:
    """How the Brain is governed: review cadences, what applies without review, limits."""
    return ws.brain.policies(who)


@router.put("/policies")
def set_policies(body: PoliciesIn, who: Who, ws: WS) -> dict[str, Any]:
    """Change how the Brain is governed: one undo point."""
    return ws.brain.set_policies(who, body.changes())


# ------------------------------------------------------------------------- files


@router.get("/attention")
def attention(who: Who, ws: WS) -> dict[str, Any]:
    """Clashes, near twins, text that does not belong in an entry, entries to re-check, and
    how many conversations each entry went to this week."""
    return ws.brain.attention(who)


@router.get("/files")
def files(who: Who, ws: WS) -> dict[str, Any]:
    """Reference documents, assets and skills, each with what points models to it."""
    return asdict(ws.brain.files(who))


@router.get("/files/content")
def file_content(path: str, who: Who, ws: WS, original: bool = False) -> Response:
    """A file's bytes, always as a download: the Brain's files never run in this origin."""
    found = ws.brain.file_content(who, path, original=original)
    return Response(
        found.data,
        media_type=found.mime,
        headers={
            "Content-Disposition": disposition(found.filename),
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cache-Control": "private, no-cache",
        },
    )


@router.post("/files", status_code=201)
async def add_file(
    who: Who,
    ws: WS,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    topic: Annotated[str, Form()] = "",
    project: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """File a document or asset in the Brain, in a project when one is named: at once with
    an undo point, or waiting for review, as the Brain's capture policy says."""
    data = await file.read(MAX_FILE + 1)  # enough to know it is too large
    result = ws.brain.add_file(
        who,
        filename=file.filename or "",
        data=data,
        title=title,
        description=description,
        topic=topic or None,
        project=project or None,
        status=status or None,
    )
    return asdict(result)


@router.get("/projects")
def projects(who: Who, ws: WS) -> list[dict[str, Any]]:
    """The work the Brain follows across conversations, active first."""
    return [asdict(p) for p in ws.brain.projects(who)]


@router.post("/projects", status_code=201)
def create_project(body: BrainProjectIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(
        ws.brain.create_project(
            who,
            name=body.name,
            summary=body.summary,
            aliases=body.aliases,
            objective=body.objective,
            goals=body.goals,
        )
    )


@router.get("/projects/{project_id}")
def project(project_id: str, who: Who, ws: WS) -> dict[str, Any]:
    """One project in full: its brief, where it stands, its progress newest first, its files
    and the notes filed with it."""
    return ws.brain.project(who, project_id)


@router.post("/projects/{project_id}/updates", status_code=201)
def update_project(project_id: str, body: ProjectUpdateIn, who: Who, ws: WS) -> dict[str, Any]:
    """Record progress: one line on what happened, and what changed in where it stands."""
    return ws.brain.project_update(who, project_id, summary=body.summary, changes=body.state)


@router.get("/preview")
def preview(
    who: Who,
    ws: WS,
    request: Annotated[str, Query(max_length=4000)],
    project: str = "",
) -> dict[str, Any]:
    """What an AI would be handed for this request, and why each piece is there. Nothing is
    recorded: a preview is not a conversation."""
    return ws.brain.preview(who, request, project=project or None)


@router.get("/skills/{name}")
def skill(name: str, who: Who, ws: WS) -> dict[str, Any]:
    """A procedure in full, with the files in its folder."""
    document = ws.brain.skill(who, name)
    if document is None:
        raise NotFound(f"No Brain skill {name}.")
    listed = next((s for s in ws.brain.files(who).skills if s.name == document.name), None)
    about = asdict(listed) if listed else {"files": []}
    return {**about, **asdict(document)}


# ------------------------------------------------------------------------- governance


@router.get("/proposals")
def proposals(who: Who, ws: WS) -> list[dict[str, Any]]:
    return ws.brain.proposals(who)


@router.post("/proposals", status_code=201)
def propose(body: ProposalIn, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.brain.propose(who, **body.model_dump()))


@router.post("/proposals/{proposal_id}/decide")
def decide(proposal_id: str, body: BrainDecisionIn, who: Who, ws: WS) -> dict[str, Any]:
    """Approve or reject a Brain proposal: a human release gate, with its own undo point."""
    return dict(ws.brain.decide(who, proposal_id, approve=body.approve, reason=body.reason))


@router.get("/review")
def review(who: Who, ws: WS) -> dict[str, Any]:
    """Everything waiting, in batches by the work that proposed it, each proposal with what
    approving it would replace, contradict or repeat."""
    return asdict(ws.brain.review(who))


@router.post("/decisions")
def decisions(body: DecisionsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Approve, reject and archive at once, saved as one undo point."""
    return ws.brain.decide_many(
        who,
        [d.model_dump(exclude_none=True) for d in body.decisions],
        label=body.label,
        source=body.source,
    )


@router.get("/checkpoints")
def checkpoints(who: Who, ws: WS, limit: int = 50) -> list[dict[str, Any]]:
    """Undo points, newest first, each saying whether it can still be undone."""
    return ws.brain.checkpoints(who, limit=limit)


@router.post("/checkpoints/{checkpoint_id}/undo")
def undo(checkpoint_id: str, who: Who, ws: WS) -> dict[str, Any]:
    """Put back what one batch of decisions changed (refused when something changed since)."""
    return ws.brain.undo(who, checkpoint_id)


@router.post("/merge", status_code=201)
def merge(body: MergeIn, who: Who, ws: WS) -> Task:
    """Two entries say the same thing: a model writes the one that should stand (its
    suggestion waits for the person to compare it with both)."""
    return ws.distill.merge(who, **body.model_dump())


# ------------------------------------------------------------------------- keeping up


@router.get("/models")
def models(who: Who, ws: WS) -> dict[str, Any]:
    """The local model that matches by meaning: here, being fetched, or not yet."""
    return ws.brain.models(who)


@router.post("/models/download", status_code=202)
def download_models(who: Who, ws: WS) -> dict[str, Any]:
    """Fetch the matching model (about 70 MB, once): the owner's call, never automatic."""
    return ws.brain.download_models(who)


@router.get("/local-models")
def local_models(who: Who, ws: WS) -> dict[str, Any]:
    """This computer's local models: the machine and its setup, each role's model and the
    pinned options, and whether the retrieval engine runs in full or in fallback."""
    return ws.brain.local_models(who)


@router.post("/local-models")
def act_local_models(body: LocalModelsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Check this computer again, make a pinned model the default for its role, download,
    remove or time one, or turn Claude Code on or off for the knowledge agent."""
    return ws.brain.act_local_models(who, body.action, body.name, body.on)


@router.get("/catch-up")
def catch_up(who: Who, ws: WS) -> dict[str, Any]:
    """What waits, as a plan: the recap, the health score, what was handled, the decisions,
    the quick groups, this week's upkeep and offers to decide once, with a time estimate."""
    return ws.catch_up.plan(who)


@router.post("/catch-up/seen")
def catch_up_seen(who: Who, ws: WS) -> dict[str, Any]:
    """The person caught up: the next recap starts from now."""
    return ws.catch_up.seen(who)


@router.post("/catch-up/snooze")
def catch_up_snooze(body: CatchUpItemIn, who: Who, ws: WS) -> dict[str, Any]:
    """Later: hide an item for a few days."""
    return ws.catch_up.snooze(who, body.key, days=body.days or 3)


@router.post("/catch-up/dismiss")
def catch_up_dismiss(body: CatchUpItemIn, who: Who, ws: WS) -> dict[str, Any]:
    """Set an item aside, for good or for some days."""
    return ws.catch_up.dismiss(who, body.key, days=body.days)


@router.get("/requests")
def requests(
    who: Who, ws: WS, limit: int = 50, before: str | None = None, app: str | None = None
) -> dict[str, Any]:
    """What each AI asked, what it got and why, and what it saved, newest first; `before`
    names the last request shown, for the next page."""
    return ws.brain.requests(who, limit=limit, before=before, client=app)


@router.get("/requests/{packet_id}")
def request(packet_id: str, who: Who, ws: WS) -> dict[str, Any]:
    """One request in full: what it got, the exact text it was handed, and the startup
    context when that went with it."""
    return ws.brain.request(who, packet_id)


@router.put("/requests/{packet_id}/labels")
def label_request(packet_id: str, body: RequestLabelsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Say which notes a logged request needed, which helped, which were noise and which it
    should have had: it joins your private eval set, kept beside the Brain."""
    return ws.brain.label_request(who, packet_id, body.model_dump())


@router.get("/report")
def report(
    who: Who, ws: WS, days: int = 7, claude_code: bool = False, quality: bool = True
) -> dict[str, Any]:
    """The report card: what context cost by day and line, brief sizes by request type and
    how well briefs carry what a task needs."""
    return ws.brain.report(who, days=days, claude_code=claude_code, quality=quality)


@router.post("/replay")
def replay(body: ReplayIn, who: Who, ws: WS) -> dict[str, Any]:
    """Rebuild logged briefs against the Brain now, at a git ref, or with a waiting proposal
    applied in a copy, and say what would change. Nothing is recorded or changed."""
    return ws.brain.replay(who, body.packets, at=body.at, proposal=body.proposal)


@router.get("/eval")
def eval_status(who: Who, ws: WS) -> dict[str, Any]:
    """How many of your requests are in the private eval set, and how many are labeled."""
    return ws.brain.eval_status(who)


@router.get("/weekly")
def weekly(who: Who, ws: WS, weeks: int = 8) -> list[dict[str, Any]]:
    """Conversations the Brain served in each of the last weeks, oldest first."""
    return ws.brain.weekly(who, weeks=weeks)


@router.get("/goals")
def goals(who: Who, ws: WS) -> dict[str, Any]:
    """The questions about what the Brain is for, and the owner's answers."""
    return ws.brain.goals(who)


@router.put("/goals")
def set_goals(body: GoalsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Say what the Brain is for: one undo point."""
    return ws.brain.set_goals(who, body.answers)


@router.get("/builtin-skills")
def builtin_skills(who: Who, ws: WS) -> dict[str, Any]:
    """The skills every Brain comes with, and whether this one has each."""
    return ws.brain.builtin_skills(who)


@router.post("/builtin-skills")
def add_builtin_skills(body: BuiltinSkillsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Add the built-in skills the Brain is missing, as one undo point."""
    return ws.brain.add_builtin_skills(who, body.names)


@router.post("/move-in/preview")
def move_in_preview(body: MoveInIn, who: Who, ws: WS) -> dict[str, Any]:
    """What the Brain makes of what an AI app already knows, stage by stage; nothing is
    written."""
    return ws.move_in.preview(who, [s.model_dump() for s in body.sources])


@router.post("/move-in/files")
def move_in_files(who: Who, files: Annotated[list[UploadFile], File()]) -> dict[str, Any]:
    """Read files for Moving in, any type, zips included: one source per file that reads (to
    preview like a paste), and what could not be read, and why. Nothing is kept. (A plain
    function: reading a long PDF runs in a worker thread, never on the event loop.)"""
    who.require("brain.read")
    if len(files) > MAX_MOVE_IN_FILES:
        raise ValidationFailed(f"Bring at most {MAX_MOVE_IN_FILES} files at a time.")
    read = []
    for upload in files:
        data = upload.file.read(MAX_MOVE_IN_UPLOAD + 1)
        if len(data) > MAX_MOVE_IN_UPLOAD:
            raise ValidationFailed(
                f"{upload.filename or 'A file'} is over "
                f"{MAX_MOVE_IN_UPLOAD // (1024 * 1024)} MB: bring in a smaller part of it."
            )
        read.append((upload.filename or "file", data))
    return UploadReader().read(read)


@router.post("/move-in", status_code=201)
def move_in(body: MoveInIn, who: Who, ws: WS) -> dict[str, Any]:
    """Propose the ideas worth keeping; they wait in Catch up."""
    return ws.move_in.keep(who, [s.model_dump() for s in body.sources], ids=body.ids)


@router.post("/reconcile", status_code=201)
def reconcile(body: ReconcileIn, who: Who, ws: WS) -> Task:
    """A proposal and an entry step on each other: the person says which one is current, and
    a model rewrites the other so both can stand (its suggestion waits in the review)."""
    return ws.distill.reconcile(who, **body.model_dump())


# ------------------------------------------------------------------------- AI work


@router.get("/distill/requests")
def distill_requests(
    who: Who, ws: WS, item_id: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """Requests to find what to remember (for one note, when named), newest first."""
    return [asdict(r) for r in ws.distill.requests(who, item_id=item_id, limit=limit)]


@router.post("/distill/requests", status_code=201)
def request_distillation(body: DistillRequestIn, who: Who, ws: WS) -> Task:
    """Ask a model to find what will last in these notes, as proposals for the Brain."""
    return ws.distill.request(who, **body.model_dump())


@router.get("/distill/settings")
def distill_settings(who: Who, ws: WS) -> dict[str, Any]:
    return ws.distill.settings(who)


@router.put("/distill/settings")
def configure_distillation(body: DistillSettingsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Which model does the AI work the app starts; null leaves it to the only one connected."""
    return ws.distill.configure(who, **body.model_dump(exclude_unset=True))


def disposition(filename: str) -> str:
    """An attachment header that survives quotes and non-ASCII names."""
    plain = filename.encode("ascii", "replace").decode("ascii").replace('"', "'")
    plain = plain.replace("\\", "_").replace("\r", " ").replace("\n", " ")
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"
