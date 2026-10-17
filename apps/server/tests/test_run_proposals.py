"""What AI work the app runs proposes passes the same door as a chat: its quotes must come
from what the run read, it has a cap on how many it makes, and what a file it made only
repeats from the brief behind that file is refused (the circular-evidence rule)."""

from workspace_core.services import brain as brain_service

RULES = "Clients approve every deliverable in writing before we invoice."


def claimed(model, make_task, runtime, owner_note=None, **fields):
    """A run of AI work, claimed by the model, reading `owner_note` (a capture) when given."""
    task = make_task(model.actor_id, **fields)
    if owner_note is not None:
        ws = runtime.ws
        ws.tasks.pin(ws.owner(), task["id"], ref_type="context_item", ref_id=owner_note["id"])
    claim = model.tool("claim_task", task_id=task["id"])["structuredContent"]
    return claim["run"]["id"], claim["packet"]


def proposed(reply):
    assert not reply.get("isError"), reply
    return reply["structuredContent"]["proposal"]["proposal_id"]


def proposal(owner, proposal_id):
    """A waiting proposal's fields, and the problems its review card names."""
    row = next(p for p in owner.ok(owner.get("/api/brain/proposals")) if p["id"] == proposal_id)
    review = owner.ok(owner.get("/api/brain/review"))
    card = next(r for r in review["proposals"] if r["id"] == proposal_id)
    return row["target"], card["analysis"]["problems"]


def test_a_runs_quote_must_come_from_what_the_run_read(owner, model, make_task, runtime, note):
    run_id, packet = claimed(model, make_task, runtime, note)
    assert "async reviews on Fridays" in packet["inputs"][0]["text"]
    heard = proposed(
        model.tool(
            "propose_brain_entry",
            run_id=run_id,
            title="Async reviews",
            statement="Clients review asynchronously, on Fridays.",
            kind="preference",
            evidence='The note says "Clients prefer async reviews on Fridays."',
        )
    )
    made_up = proposed(
        model.tool(
            "propose_brain_entry",
            run_id=run_id,
            title="Weekly calls",
            statement="Clients want a weekly call.",
            kind="preference",
            evidence='The note says "Clients want a call every Monday at nine."',
        )
    )
    target, problems = proposal(owner, heard)
    assert target.get("confidence") != "inferred" and not target.get("unheard_quote")
    target, problems = proposal(owner, made_up)
    assert target["confidence"] == "inferred"
    assert target["unheard_quote"] == "Clients want a call every Monday at nine."
    assert any("not in what that work read" in p for p in problems), problems


def test_a_run_has_a_cap_on_what_it_proposes(owner, model, make_task, runtime, monkeypatch):
    monkeypatch.setattr(brain_service, "RUN_PROPOSAL_LIMIT", 2)
    run_id, _packet = claimed(model, make_task, runtime)
    for n in range(2):
        made = model.tool(
            "propose_brain_entry",
            run_id=run_id,
            title=f"Fact {n}",
            statement=f"The studio has {n + 3} designers.",
            kind="fact",
            evidence="The team page",
        )
        assert not made.get("isError"), made
    refused = model.tool(
        "propose_brain_entry",
        run_id=run_id,
        title="One more",
        statement="The studio opened in 2015.",
        kind="fact",
        evidence="The about page",
    )
    assert refused.get("isError")
    assert "has made 2 proposals, its limit is 2" in refused["content"][0]["text"]


def test_what_an_ai_made_file_only_repeats_from_its_brief_is_refused(
    owner, model, make_task, runtime
):
    # A run is handed the Brain's entry on how long projects run, and makes a page from it.
    run_id, packet = claimed(
        model,
        make_task,
        runtime,
        title="Write the services page",
        purpose="Say what the studio offers and how long web design projects run",
        instructions="Draft the services page from what the studio offers.",
    )
    given = {e["id"] for e in packet["brain"]["entries"]}
    assert "facts-services-002" in given, given
    entry = owner.ok(owner.get("/api/brain/entries/facts-services-002"))
    ws = runtime.ws
    page = ws.artifacts.create(
        ws.actors.authenticate(model.connection["token"]),
        type="document",
        title="Services page",
        content=f"# Services\n\n{entry['text']}\n",
        run_id=run_id,
    )
    model.tool("complete_task", run_id=run_id, summary="Done.")
    # Later, something proposes what that page says, in near the same words, citing the page.
    echo = model.tool(
        "propose_brain_entry",
        title="Project length",
        statement="As our services page says, " + entry["text"],
        kind="fact",
        evidence="The services page",
        sources=[f"artifact:{page.artifact.id}"],
    )
    assert echo.get("isError"), echo
    assert "circular-evidence rule" in echo["content"][0]["text"]
