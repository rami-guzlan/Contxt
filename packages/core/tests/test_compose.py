"""Compose: a request and its picks planned exactly as the run will start (an agent's run when an
agent is picked, else a run like the Skills page's, or the Brain picks), shown as the packet a
model gets, copied short for any AI, improved by a model, run here; and saved prompts, with
versions and their uses counted, private to the app."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed
from workspace_core.ports import BrainSkill

OUTLINE = "## The points\n\n1. Polls run on Tuesdays.\n2. Video keeps its budget.\n"


@pytest.fixture
def q4(brain):
    return brain.create_project(
        name="Q4 campaigns", summary="The fourth quarter", aliases=[], proposer="owner"
    )


@pytest.fixture
def outline(ws, owner):
    doc = ws.docs.create(owner, title="Q4 outline")
    return ws.notes.save(owner, doc.id, body=OUTLINE)


def test_picked_skills_docs_and_documents_make_the_run_a_model_gets(
    ws, owner, connect, q4, outline, brain
):
    claude = connect()
    spec = {
        "request": "Three LinkedIn posts from my outline.",
        "skills": ["weekly-posts"],
        "docs": [outline.id],
        "library": ["references/voice.md"],
        "project": q4.id,
    }
    packet = ws.compose.packet(owner, **spec)
    text = packet["instructions"]["text"]
    assert "in this order: /weekly-posts" in text
    assert "get_brain_reference: references/voice.md" in text
    assert f"Work from the pinned note “Q4 outline” ({outline.id})" in text
    assert "This is for the project Q4 campaigns (q4-campaigns)." in text
    assert text.rstrip().endswith("read it in full with get_context_item first.")
    (pinned,) = packet["inputs"]
    assert (pinned["title"], pinned["version"]) == ("Q4 outline", outline.revision)
    assert "Polls run on Tuesdays." in pinned["text"]
    assert packet["brain"]["text"].startswith("# Brain context")
    assert brain.briefed[-1].startswith(
        "Three LinkedIn posts from my outline.\n\nUsing the skills weekly-posts"
    )
    task = ws.compose.run(owner, **spec)
    claim = ws.bus.claim(claude, task.id)
    assert claim.packet["instructions"]["text"] == text  # what was shown is what runs
    assert [i["ref"] for i in claim.packet["inputs"]] == [f"context_item:{outline.id}"]
    ws.skills.save_result(claude, run_id=claim.run.id, title="Posts", text="One. Two. Three.")
    ws.bus.complete(claude, claim.run.id, summary="Done.")
    (run,) = ws.skills.runs_where(owner, lambda about: bool(about.get("compose")))
    assert run["skills"] == ["weekly-posts"] and run["result"]["text"] == "One. Two. Three."


def test_nothing_picked_lets_the_brain_pick(ws, owner):
    plan = ws.compose.plan(owner, request="A thank-you note to the panel.")
    assert "names no skill" in plan["instructions"]
    assert plan["title"] == "Compose: A thank-you note to the panel."
    assert plan["about"]["names"] == [] and plan["pins"] == []


def test_with_an_agent_it_is_the_agents_run_with_the_extra_picks(ws, owner, outline):
    ws.agents.save(owner, "content-strategist", {"role": "Writes the posts"}, "Write well.")
    plan = ws.compose.plan(
        owner,
        request="This week's plan.",
        agent="content-strategist",
        skills=["weekly-posts"],
        docs=[outline.id],
    )
    text = plan["instructions"]
    assert text.startswith("You are working as the agent content-strategist")
    assert "Follow these skills too, in this order" in text and "/weekly-posts" in text
    assert "Work from the pinned note “Q4 outline”" in text
    assert plan["about"]["agent"] == "content-strategist" and plan["about"]["compose"] is True
    assert plan["about"]["docs"] == [
        {"id": outline.id, "title": "Q4 outline", "revision": outline.revision}
    ]
    assert plan["title"] == "Ask content-strategist"


def test_each_pick_is_checked(ws, owner, brain):
    with pytest.raises(ValidationFailed, match="Write what you want"):
        ws.compose.plan(owner, request="  ")
    with pytest.raises(NotFound, match="No skill nope"):
        ws.compose.plan(owner, request="x", skills=["nope"])
    with pytest.raises(ValidationFailed, match="at most 6"):
        ws.compose.plan(owner, request="x", skills=[f"s{n}" for n in range(7)])
    with pytest.raises(NotFound, match="no document"):
        ws.compose.plan(owner, request="x", library=["references/gone.md"])
    with pytest.raises(NotFound):
        ws.compose.plan(owner, request="x", docs=["ctx_nope"])
    with pytest.raises(NotFound, match="No project"):
        ws.compose.plan(owner, request="x", project="nope")
    with pytest.raises(NotFound):
        ws.compose.plan(owner, request="x", agent="nobody")
    brain.extra_skills.append(
        BrainSkill(
            name="shared-assets", category="design", description="Fonts.", artifacts=["font"]
        )
    )
    brain.extra_skills.append(
        BrainSkill(
            name="brand-sheet",
            category="design",
            description="A PDF.",
            artifacts=["pdf"],
            depends_on=["shared-assets"],
        )
    )
    with pytest.raises(ValidationFailed, match="not run on its own"):
        ws.compose.plan(owner, request="x", skills=["shared-assets"])
    files = ws.compose.plan(owner, request="A one-pager.", skills=["brand-sheet"])
    assert files["about"]["files"] is True and "folder of its own" in files["instructions"]


def test_the_short_request_fetches_its_brief_and_brings_the_notes(ws, owner, outline, q4):
    ws.agents.save(owner, "content-strategist", {"role": "Writes the posts"}, "Write well.")
    short = ws.compose.short(
        owner,
        request="Three posts.",
        skills=["weekly-posts"],
        agent="content-strategist",
        docs=[outline.id],
        library=["references/voice.md"],
        project=q4.id,
    )
    assert short.startswith(
        "Three posts.\n\nBefore you start, call get_task_context with this request"
    )
    assert "(it is for the project Q4 campaigns)" in short
    assert 'call get_agent with name "content-strategist"' in short
    assert "opening each with get_skill: /weekly-posts." in short
    assert "get_reference: references/voice.md." in short
    assert "## My note: Q4 outline" in short and "Video keeps its budget." in short


def test_the_improver_reads_the_procedure_the_request_and_the_picks(ws, owner, outline):
    text = ws.compose.improver_prompt(
        owner,
        request="posts pls",
        skills=["weekly-posts"],
        docs=[outline.id],
        library=["references/voice.md"],
    )
    assert "Improve the request." in text  # the procedure the Brain ships
    assert "posts pls" in text and "- /weekly-posts: Draft posts" in text
    assert "- Q4 outline: " in text and "- references/voice.md (Voice)" in text
    assert "Write plainly. No hype." in text  # the brief, cut short
    improved = ws.compose.read_improved(
        'Here it is: {"prompt": "Three posts from the doc Q4 outline.",'
        ' "changes": ["Says how many."], "used": ["/weekly-posts"], "questions": []}'
    )
    assert improved == {
        "prompt": "Three posts from the doc Q4 outline.",
        "changes": ["Says how many."],
        "used": ["/weekly-posts"],
        "questions": [],
    }
    with pytest.raises(ValidationFailed):
        ws.compose.read_improved("I could not do it.")


def test_a_saved_prompt_keeps_its_versions_and_counts_its_runs(ws, owner, connect):
    connect()
    first = ws.prompts.create(
        owner, title="Weekly posts", body="Three posts.", picks={"skills": ["/weekly-posts"]}
    )
    assert (first.revision, first.picks["skills"], first.uses) == (1, ["weekly-posts"], 0)
    other = ws.prompts.create(owner, title="Thank-you note", body="A thank-you note.")
    changed = ws.prompts.update(owner, first.id, body="Three posts, under 200 words each.")
    assert changed.revision == 2 and [v["revision"] for v in changed.versions] == [2, 1]
    assert changed.versions[1]["body"] == "Three posts."
    picked = ws.prompts.update(owner, first.id, picks={"skills": ["weekly-posts"], "project": "q4"})
    assert picked.revision == 2 and picked.picks["project"] == "q4"  # new picks are not new words
    for _ in range(2):
        ws.compose.run(owner, prompt_id=first.id, request=changed.body, skills=["weekly-posts"])
    listed = ws.prompts.list(owner)
    assert [p.id for p in listed] == [first.id, other.id]  # the most used first
    assert listed[0].uses == 2 and listed[0].last_used is not None
    assert [p.id for p in ws.prompts.list(owner, query="thank")] == [other.id]
    ws.prompts.archive(owner, other.id)
    assert [p.id for p in ws.prompts.list(owner)] == [first.id]
    assert [p.id for p in ws.prompts.list(owner, archived=True)] == [other.id]
    with pytest.raises(ValidationFailed):
        ws.prompts.create(owner, title="Empty", body="  ")
    with pytest.raises(ValidationFailed):
        ws.prompts.create(
            owner, title="Too many", body="x", picks={"docs": [f"ctx_{n}" for n in range(6)]}
        )


def test_saved_prompts_stay_private_to_the_app(ws, owner, connect):
    claude = connect()
    saved = ws.prompts.create(owner, title="Weekly posts", body="Three posts about polls.")
    with pytest.raises(PermissionDenied):
        ws.prompts.create(claude, title="Mine", body="A prompt.")
    assert saved.id not in [n.id for n in ws.notes.list(owner)]
    assert saved.id not in [i.id for i in ws.context.list(owner)]
    assert ws.context.search(claude, "polls") == []
    assert ws.search(owner, "polls").notes == []
