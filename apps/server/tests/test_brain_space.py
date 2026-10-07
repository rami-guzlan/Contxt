"""The Brain over REST as a browsable space, its projects in full, and finding what to
remember in notes, end to end."""

import pytest

from workspace_server.brain_adapter import clean_path, excerpt, mime_of
from workspace_server.worker import Worker

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def entry_ids(owner):
    return {e["id"] for e in owner.ok(owner.get("/api/brain/catalog"))["entries"]}


def test_the_catalog_holds_every_entry_the_owner_can_see(owner):
    catalog = owner.ok(owner.get("/api/brain/catalog"))
    entries = {e["id"]: e for e in catalog["entries"]}
    assert "rules-design-001" in entries  # the owner's team
    assert entries["facts-clients-acme-001"]["partition"] == "client:acme"
    assert "facts-sam-001" not in entries  # another person's private note
    assert "facts-services-000" not in entries  # archived
    assert entries["identity-001"]["standing"] is True
    assert entries["rules-style-003"]["file"] == "references/style-guide.md"
    assert [a["key"] for a in catalog["areas"]] == ["identity", "rules", "facts", "state"]
    rules = next(a for a in catalog["areas"] if a["key"] == "rules")
    style = next(t for t in rules["topics"] if t["key"] == "rules/style")
    assert style["entries"] == 3 and "plain language" in style["description"]


def test_attention_and_topic_names_are_served(owner):
    attention = owner.ok(owner.get("/api/brain/attention"))
    assert set(attention) >= {"clashes", "twins", "flagged", "recheck", "usage"}
    assert "facts-sam-001" not in attention["usage"]  # another person's note stays out
    catalog = owner.ok(owner.get("/api/brain/catalog"))
    facts = next(a for a in catalog["areas"] if a["key"] == "facts")
    assert {t["label"] for t in facts["topics"]} >= {"Services", "Clients"}


def test_an_entry_sealed_to_a_client_still_opens(owner):
    entry = owner.ok(owner.get("/api/brain/entries/facts-clients-acme-001"))
    assert "dark palettes" in entry["text"]


def test_files_are_listed_and_served_safely(owner):
    files = owner.ok(owner.get("/api/brain/files"))
    (reference,) = files["references"]
    assert reference["path"] == "references/style-guide.md"
    assert reference["entry_id"] == "rules-style-003" and reference["size"] > 0
    # described by the entry that sends models to it, not by the document's first line
    assert reference["description"].startswith("Pointer: the full studio style guide")
    (skill,) = files["skills"]
    assert skill["name"] == "brand-sheet" and skill["path"] == "skills/design/brand-sheet"
    assert [f["path"] for f in skill["files"]] == ["skills/design/brand-sheet/SKILL.md"]
    served = owner.get("/api/brain/files/content", params={"path": reference["path"]})
    assert served.status_code == 200 and served.text.startswith("# Studio style guide")
    assert served.headers["content-disposition"].startswith("attachment")
    assert served.headers["x-content-type-options"] == "nosniff"
    for path in (
        "../brain.json",
        "brain.json",
        ".brain/sessions.sqlite",
        "knowledge/rules/style/x.md",
        "references/../brain.json",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "references/missing.md",
    ):
        assert owner.get("/api/brain/files/content", params={"path": path}).status_code == 404


def test_only_paths_inside_the_served_folders_are_accepted():
    assert clean_path("references\\guides\\voice.md") == "references/guides/voice.md"
    assert clean_path("skills/design/brand-sheet/SKILL.md") == "skills/design/brand-sheet/SKILL.md"
    for path in (
        "",
        "references",
        "inbox/proposal.md",
        "knowledge/a.md",
        "references/../brain.json",
        "references/./x.md",
        "references//x.md",
        "assets/.hidden.png",
        "/references/x.md",
        "C:/references/x.md",
    ):
        assert clean_path(path) is None, path


def test_file_types_do_not_depend_on_the_platform():
    assert mime_of("skills/shared/Inter-Bold.TTF") == "font/ttf"
    assert mime_of("assets/brand/hero.webp") == "image/webp"
    assert mime_of("skills/decks/template.pptx").endswith("presentationml.presentation")
    assert mime_of("references/guide.md") == "text/markdown"
    assert mime_of("assets/x.unknownext") == "application/octet-stream"


def test_a_description_is_the_first_line_of_prose_as_plain_text():
    text = (
        "# Voice\n\n> Source: `v.pdf`\n\n**Status:** see [the guide](https://x.test) and `rules`.\n"
    )
    assert excerpt(text) == "Status: see the guide and rules."
    assert excerpt("# Only a heading\n") == ""
    assert excerpt("word " * 60).endswith("…") and len(excerpt("word " * 60)) <= 180


def test_a_skill_opens_with_its_files(owner):
    skill = owner.ok(owner.get("/api/brain/skills/brand-sheet"))
    assert "Gather the palette" in skill["text"]
    assert skill["files"][0]["path"].endswith("SKILL.md")
    assert owner.get("/api/brain/skills/nothing-here").status_code == 404


def test_the_owners_file_is_filed_at_once_and_one_undo_takes_it_out(owner):
    made = owner.ok(
        owner.post(
            "/api/brain/files",
            files={"file": ("palette.png", PNG, "image/png")},
            data={"title": "Studio palette", "description": "The brand colors"},
        ),
        201,
    )
    assert made["status"] == "applied" and made["checkpoint_id"]
    assert owner.ok(owner.get("/api/brain/proposals")) == []
    (asset,) = owner.ok(owner.get("/api/brain/files"))["assets"]
    assert asset["path"].endswith(".png") and asset["title"] == "Studio palette"
    assert asset["entry_id"] in entry_ids(owner)
    served = owner.get("/api/brain/files/content", params={"path": asset["path"]})
    assert served.content == PNG and served.headers["content-type"] == "image/png"
    owner.ok(owner.post(f"/api/brain/checkpoints/{made['checkpoint_id']}/undo"))
    assert owner.ok(owner.get("/api/brain/files"))["assets"] == []


def test_a_file_waits_for_approval_when_the_policy_says_so(owner):
    owner.ok(owner.put("/api/brain/policies", json={"capture": {"file": {"app": "wait"}}}))
    made = owner.ok(
        owner.post(
            "/api/brain/files",
            files={"file": ("palette.png", PNG, "image/png")},
            data={"title": "Studio palette"},
        ),
        201,
    )
    assert made["status"] == "pending"
    (proposal,) = owner.ok(owner.get("/api/brain/proposals"))
    assert proposal["kind"] == "file.add" and proposal["proposer"].startswith("human:Owner")
    assert owner.ok(owner.get("/api/brain/files"))["assets"] == []  # not before approval
    owner.ok(
        owner.post(f"/api/brain/proposals/{made['proposal_id']}/decide", json={"approve": True})
    )
    (asset,) = owner.ok(owner.get("/api/brain/files"))["assets"]
    assert asset["title"] == "Studio palette"


def test_a_document_filed_in_a_project_reaches_what_an_ai_gets(owner, model):
    made = owner.ok(
        owner.post(
            "/api/brain/projects",
            json={
                "name": "Spring launch",
                "summary": "The spring campaign proposals for the studio.",
                "aliases": ["the spring campaign"],
            },
        ),
        201,
    )
    assert made["aliases"] == ["the spring campaign"] and made["files"] == 0
    text = (
        b"# Spring campaign proposal\n\n## Podcast sponsorship\n\nSponsor two episodes of the"
        b" Design Matters podcast. Budget: 900 dollars.\n\n## Timeline\n\nMarch to May.\n"
    )
    filed = owner.ok(
        owner.post(
            "/api/brain/files",
            files={"file": ("Spring campaign proposal v2.md", text, "text/markdown")},
            data={"project": made["id"], "status": "sent"},
        ),
        201,
    )
    assert filed["status"] == "applied" and filed["version"] == 2
    assert filed["project"] == made["id"] and filed["sections"] == 2
    reference = next(r for r in owner.ok(owner.get("/api/brain/files"))["references"] if r["work"])
    assert reference["project"] == made["id"] and reference["project_title"] == "Spring launch"
    assert (reference["version"], reference["file_status"], reference["sections"]) == (
        2,
        "sent",
        2,
    )
    (project,) = [p for p in owner.ok(owner.get("/api/brain/projects")) if p["id"] == made["id"]]
    assert project["files"] == 1
    shown = owner.ok(
        owner.get(
            "/api/brain/preview",
            params={"request": "What budget did we set for the podcast sponsorship?"},
        )
    )
    assert shown["sections"][0]["label"] == "Podcast sponsorship"
    assert "Design Matters" in shown["text"]
    # Starting a project changes the Brain at once: a person's call, not a model's.
    denied = model.post("/api/brain/projects", json={"name": "Model work", "summary": "x"})
    assert denied.status_code == 403


def test_an_added_document_keeps_its_original(owner):
    text = b"# Pricing bands\n\nSmall sites start at a fixed fee; larger ones are scoped."
    made = owner.ok(
        owner.post("/api/brain/files", files={"file": ("pricing.md", text, "text/markdown")}),
        201,
    )
    assert made["status"] == "applied"
    reference = next(
        r
        for r in owner.ok(owner.get("/api/brain/files"))["references"]
        if r["original"] == "pricing.md"
    )
    original = owner.get(
        "/api/brain/files/content", params={"path": reference["path"], "original": "true"}
    )
    assert original.content == text and "pricing.md" in original.headers["content-disposition"]


def test_files_the_brain_cannot_take_are_refused(owner):
    for name in ("setup.exe", ".env"):
        response = owner.post("/api/brain/files", files={"file": (name, b"x", "text/plain")})
        assert response.status_code == 422, response.text


def test_an_entry_shows_who_verified_it(owner):
    owner.ok(owner.post("/api/brain/entries/rules-style-001/verify", json={}))
    (latest, *_) = owner.ok(owner.get("/api/brain/entries/rules-style-001/history"))
    assert latest["action"] == "verified" and latest["by"] == "person:alex"


def test_a_model_reads_the_brain_but_never_decides(owner, model):
    assert model.ok(model.get("/api/brain/catalog"))["entries"]
    made = model.ok(
        model.post(
            "/api/brain/files",
            files={"file": ("notes.md", b"# Notes\n\nMeeting.", "text/markdown")},
        ),
        201,
    )
    refused = model.post(
        f"/api/brain/proposals/{made['proposal_id']}/decide", json={"approve": True}
    )
    assert refused.status_code == 403


@pytest.fixture
def working_notes(owner):
    return [
        owner.ok(
            owner.post(
                "/api/notes", json={"title": "Launch timing", "body": "Sites launch on Tuesdays."}
            ),
            201,
        ),
        owner.ok(
            owner.post("/api/notes", json={"title": "Case studies", "body": "Lead with outcomes."}),
            201,
        ),
    ]


def test_finding_what_to_remember_runs_from_notes_to_the_brain(owner, model, working_notes):
    task = owner.ok(
        owner.post(
            "/api/brain/distill/requests",
            json={
                "item_ids": [n["id"] for n in working_notes],
                "guidance": "Only what clients should hear.",
            },
        ),
        201,
    )
    assert task["assignee_id"] == model.actor_id and task["template"] == "distill"
    assert task["title"] == "Find what to remember in 2 notes"

    claimed = model.tool("claim_task", task_id=task["id"])
    brief = claimed["content"][0]["text"]
    assert "Launch timing" in brief and "propose_brain_entry" in brief
    assert "Only what clients should hear." in brief
    run_id = claimed["structuredContent"]["run"]["id"]
    proposed = model.tool(
        "propose_brain_entry",
        title="Launch day",
        statement="Client sites launch on Tuesdays.",
        kind="rule",
        evidence="Launch timing: 'Sites launch on Tuesdays.'",
        sources=[f"context_item:{working_notes[0]['id']}"],
        run_id=run_id,
    )
    proposal_id = proposed["structuredContent"]["proposal"]["proposal_id"]
    model.tool("complete_task", run_id=run_id, summary="One rule; case-study advice is a draft")

    (request,) = owner.ok(owner.get("/api/brain/distill/requests"))
    assert (request["status"], request["items"]) == ("done", [n["id"] for n in working_notes])
    assert request["proposals"] == [{"id": proposal_id, "title": "Launch day", "status": "pending"}]
    (waiting,) = owner.ok(owner.get("/api/brain/proposals"))
    assert waiting["task_id"] == task["id"]
    owner.ok(owner.post(f"/api/brain/proposals/{proposal_id}/decide", json={"approve": True}))
    (request,) = owner.ok(
        owner.get(f"/api/brain/distill/requests?item_id={working_notes[0]['id']}")
    )
    assert request["proposals"][0]["status"] == "approved"
    assert owner.ok(owner.get("/api/brain/distill/requests?item_id=ctx_none")) == []


def test_the_propose_tool_takes_the_run(model):
    tools = {t["name"]: t for t in model.mcp("tools/list")["result"]["tools"]}
    assert "run_id" in tools["propose_brain_entry"]["inputSchema"]["properties"]


def test_a_proposal_carries_a_plain_one_line_summary(owner, model):
    tools = {t["name"]: t for t in model.mcp("tools/list")["result"]["tools"]}
    assert "summary" in tools["propose_brain_entry"]["inputSchema"]["properties"]
    given = model.tool(
        "propose_brain_entry",
        title="Launch day",
        summary="Which weekday client sites go live.",
        statement="Client sites launch on Tuesdays. Fixes ship on Fridays.",
        kind="rule",
        evidence="Launch timing: 'Sites launch on Tuesdays.'",
    )
    derived = model.tool(
        "propose_brain_entry",
        title="Retainer billing",
        statement="Retainers are billed monthly. The first month is paid up front.",
        evidence="Billing notes: 'Retainers are billed monthly.'",
    )
    targets = {row["id"]: row["target"] for row in owner.ok(owner.get("/api/brain/proposals"))}
    # The sample vault is filed by layer, where a summary is kept as the index line.
    given_id = given["structuredContent"]["proposal"]["proposal_id"]
    derived_id = derived["structuredContent"]["proposal"]["proposal_id"]
    assert targets[given_id]["index_line"] == "Which weekday client sites go live."
    assert targets[derived_id]["index_line"] == "Retainers are billed monthly."
    too_long = model.tool(
        "propose_brain_entry",
        title="Launch week",
        summary="word " * 50,
        statement="Launches avoid the last week of a quarter.",
        evidence="Launch timing.",
    )
    assert too_long["isError"] is True


def test_the_model_for_the_apps_ai_work_is_the_owners_setting(owner, model, working_notes):
    assert owner.ok(owner.get("/api/brain/distill/settings")) == {"assignee_id": None}
    refused = model.put("/api/brain/distill/settings", json={"assignee_id": model.actor_id})
    assert refused.status_code == 403
    chosen = owner.ok(
        owner.put("/api/brain/distill/settings", json={"assignee_id": model.actor_id})
    )
    assert chosen == {"assignee_id": model.actor_id}
    bad = owner.put("/api/brain/distill/settings", json={"assignee_id": "act_nobody"})
    assert bad.status_code == 422
    cleared = owner.ok(owner.put("/api/brain/distill/settings", json={"assignee_id": None}))
    assert cleared == {"assignee_id": None}


def test_a_request_waits_for_the_first_model(owner, runtime, working_notes):
    made = owner.ok(
        owner.post(
            "/api/brain/distill/requests",
            json={"item_ids": [working_notes[0]["id"]], "guidance": "Only what lasts."},
        ),
        201,
    )
    assert (made["status"], made["assignee_id"]) == ("draft", None)
    assert made["title"] == "Find what to remember in Launch timing"
    (request,) = owner.ok(owner.get("/api/brain/distill/requests"))
    assert request["waiting"] is True
    assert Worker(runtime.ws).tick().assigned == 0  # no model yet
    claude = owner.ok(
        owner.post("/api/connections", json={"name": "Claude Code", "provider": "claude-code"}), 201
    )
    assert Worker(runtime.ws).tick().assigned == 1
    task = owner.ok(owner.get(f"/api/tasks/{made['id']}"))
    assert (task["status"], task["assignee_id"]) == ("ready", claude["actor"]["id"])


def test_a_project_in_full_and_its_progress(owner, model):
    made = owner.ok(
        owner.post(
            "/api/brain/projects",
            json={
                "name": "Spring launch",
                "summary": "Launch the spring collection site",
                "aliases": ["the launch"],
            },
        ),
        201,
    )
    update = owner.ok(
        owner.post(
            f"/api/brain/projects/{made['id']}/updates",
            json={
                "summary": "Sent the plan to the client",
                "state": {"current": "Waiting for feedback", "next": "Book the shoot"},
            },
        ),
        201,
    )
    assert update
    project = owner.ok(owner.get(f"/api/brain/projects/{made['id']}"))
    assert project["title"] == "Spring launch" and project["aliases"] == ["the launch"]
    assert project["state"]["next"] == "Book the shoot"
    assert project["updates"][0]["summary"] == "Sent the plan to the client"
    bad = owner.post(
        f"/api/brain/projects/{made['id']}/updates",
        json={"summary": "x", "state": {"mood": "good"}},
    )
    assert bad.status_code == 422
    assert owner.get("/api/brain/projects/nope").status_code == 404
    renamed = owner.ok(
        owner.post(
            "/api/brain/decisions",
            json={
                "decisions": [
                    {
                        "action": "update",
                        "entry_id": made["id"],
                        "fields": {"aliases": "the launch, spring site"},
                    }
                ]
            },
        )
    )
    assert renamed["results"][0]["ok"], renamed
    names = owner.ok(owner.get(f"/api/brain/projects/{made['id']}"))["aliases"]
    assert names == ["the launch", "spring site"]
    events = {e["type"] for e in owner.ok(owner.get("/api/events"))}
    assert {"brain.project_started", "brain.project_updated"} <= events
