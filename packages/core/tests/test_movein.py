"""Moving in and the Brain's goals from the workspace: what an AI app knew becomes sourced
suggestions (a password never does), the goals are the owner's to set, they are a setup step,
and the work that finds what to remember weighs against them."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed
from workspace_core.services.movein import title_of

MEMORY = """known: Write plainly.
Ships the newsletter every Tuesday.
rule: Prefers short answers.
clash: Headlines use title case.
secret: The wifi password is hunter2."""


def test_a_preview_reads_and_keeping_proposes_what_is_worth_it(ws, owner, brain):
    sources = [{"kind": "chatgpt", "text": MEMORY, "label": "ChatGPT memory"}]
    preview = ws.move_in.preview(owner, sources)
    assert [i["status"] for i in preview["ideas"]] == ["known", "new", "new", "disagree", "private"]
    assert brain.proposed == []  # a preview writes nothing
    kept = ws.move_in.keep(owner, sources)
    assert [p["idea"] for p in kept["proposed"]] == ["i2", "i3", "i4"]
    assert kept["secrets_left_out"] == 1
    newsletter, short, clash = brain.proposed
    assert newsletter["origin"] == "import:chatgpt"
    assert newsletter["evidence"].startswith("Moved in from ChatGPT memory on 2026-09-28")
    assert newsletter["title"] == "Ships the newsletter every Tuesday"
    assert short["scope"] == "person:owner"  # about the person: filed with their own notes
    assert clash["contradicts"] == ["voice-guide"]


def test_what_the_sift_left_out_is_kept_only_when_chosen(ws, owner, brain):
    sources = [{"kind": "paste", "text": "project: Book the guest.\noff: Has a dog named Pepper."}]
    kept = ws.move_in.keep(owner, sources)
    assert [p["idea"] for p in kept["proposed"]] == ["i1"]
    (guest,) = brain.proposed
    assert (guest["extra"]["goal"], guest["extra"]["project_id"]) == (
        "what your Brain is for",
        "q4-webinars",
    )
    anyway = ws.move_in.keep(owner, sources, ids=["i2"])  # pulled anyway
    assert [p["idea"] for p in anyway["proposed"]] == ["i2"]


def test_only_the_ideas_chosen_are_kept(ws, owner, brain):
    sources = [{"kind": "paste", "text": MEMORY}]
    kept = ws.move_in.keep(owner, sources, ids=["i3"])
    assert [p["idea"] for p in kept["proposed"]] == ["i3"]
    assert len(brain.proposed) == 1


def test_sources_are_checked(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.move_in.preview(owner, [])
    with pytest.raises(ValidationFailed):
        ws.move_in.preview(owner, [{"kind": "fax", "text": "x"}])
    with pytest.raises(ValidationFailed):
        ws.move_in.preview(owner, [{"kind": "paste", "text": "   "}])


def test_titles_are_a_few_plain_words():
    assert title_of("Prefers short answers. Hates emojis.") == "Prefers short answers"
    assert title_of("A b c d e f g h i j k") == "A b c d e f g h i…"


def test_the_owner_sets_the_goals_and_the_setup_counts_them(ws, owner, brain, connect):
    steps = {s["id"]: s["done"] for s in ws.onboarding.status(owner)["steps"]}
    assert list(steps)[:2] == ["you", "goals"] and not steps["goals"]
    with pytest.raises(PermissionDenied):
        ws.brain.set_goals(connect(), {"purpose": "Run the studio."})
    with pytest.raises(ValidationFailed):
        ws.brain.set_goals(owner, {"purpose": 3})
    saved = ws.brain.set_goals(owner, {"purpose": "Run the studio.", "outcomes": "Ten clients."})
    assert saved["status"] == "saved"
    assert ws.brain.goals(owner)["answers"]["outcomes"] == "Ten clients."
    steps = {s["id"]: s["done"] for s in ws.onboarding.status(owner)["steps"]}
    assert steps["goals"]
    (event,) = ws.events.activity(owner, types=["brain.goals_set"])
    assert event.data["answered"] == ["outcomes", "purpose"]


def pinned(ws, owner, task):
    return {(p.ref_type, p.ref_id) for p in ws.tasks.pins(owner, task.id)}


def test_pulling_what_matters_pins_the_goals_and_the_active_projects(ws, owner, brain):
    note = ws.notes.create(owner, title="Kickoff", body="We agreed to ship monthly.")
    plain = ws.distill.request(owner, item_ids=[note.id], wait=True)
    assert pinned(ws, owner, plain) == {("context_item", note.id)}
    ws.brain.set_goals(owner, {"purpose": "Help me run the studio."})
    ws.brain.create_project(owner, name="Webinars", summary="Monthly webinars for CLOs")
    weighed = ws.distill.request(owner, item_ids=[note.id], wait=True, guidance="Just pricing")
    assert pinned(ws, owner, weighed) == {
        ("context_item", note.id),
        ("brain_entry", "you-goals"),
        ("brain_project", "webinars"),
    }
    assert weighed.title == "Pull what matters from Kickoff"
    assert "does it serve one of the person's goals" in weighed.instructions
    assert "Guidance from Owner (it overrides the goals): Just pricing" in weighed.instructions


def test_pulling_reads_documents_filed_in_the_brain(ws, owner, brain):
    task = ws.distill.request(owner, paths=["references/voice.md"], wait=True)
    assert pinned(ws, owner, task) == {("brain_file", "references/voice.md")}
    (request,) = ws.distill.requests(owner)
    assert request.files == ["references/voice.md"] and request.items == []
    with pytest.raises(NotFound):
        ws.distill.request(owner, paths=["references/none.md"], wait=True)
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, wait=True)


def test_what_a_run_left_out_comes_back_with_the_request(ws, owner, connect, brain):
    claude = connect()
    note = ws.notes.create(owner, title="Kickoff", body="We agreed to ship monthly.")
    task = ws.distill.request(owner, item_ids=[note.id], assignee_id=claude.actor_id)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(
        claude,
        run.id,
        summary="1 proposal",
        left_out=[{"statement": "The coffee was cold.", "why": "small talk"}, "Bare text"],
    )
    (request,) = ws.distill.requests(owner)
    assert request.left_out == [
        {"statement": "The coffee was cold.", "why": "small talk"},
        {"statement": "Bare text", "why": ""},
    ]


def test_a_proposal_names_the_goal_and_the_project_it_serves(ws, owner, brain):
    ws.brain.create_project(owner, name="Webinars", summary="Monthly webinars for CLOs")
    ws.brain.propose(
        owner,
        title="Webinar day",
        statement="Webinars run on the last Tuesday.",
        evidence="Kickoff",
        goal="Stop dropping follow-ups",
        project="webinars",
    )
    assert brain.proposed[-1]["extra"] == {
        "goal": "Stop dropping follow-ups",
        "project_id": "webinars",
    }
    (card,) = [g for g in ws.catch_up.plan(owner)["quick"]]
    (item,) = card["items"]
    assert item["goal"] == "Stop dropping follow-ups"
    assert item["project"] == {"id": "webinars", "title": "Webinars"}
    with pytest.raises(ValidationFailed):
        ws.brain.propose(owner, title="X", statement="Y.", evidence="Z", project="no such project")


def test_built_in_skills_are_listed_and_added(ws, owner, connect):
    listed = ws.brain.builtin_skills(owner)
    assert listed["missing"] == ["knowledge-check"]
    with pytest.raises(PermissionDenied):
        ws.brain.add_builtin_skills(connect())
    assert ws.brain.add_builtin_skills(owner)["added"] == ["knowledge-check"]
    assert ws.brain.builtin_skills(owner)["missing"] == []


def test_a_merge_is_asked_of_a_model_with_both_entries_pinned(ws, owner, brain):
    brain.entries["tone"] = brain.entries["voice-guide"].__class__(
        **{**brain.entries["voice-guide"].__dict__, "id": "tone", "title": "Tone"}
    )
    task = ws.distill.merge(owner, keep_id="voice-guide", other_id="tone")
    assert task.template == "merge"
    assert 'revises="voice-guide"' in task.instructions
    assert 'replaces=["tone"]' in task.instructions
    pins = {p.ref_id for p in ws.tasks.pins(owner, task.id)}
    assert pins == {"voice-guide", "tone"}
    with pytest.raises(ValidationFailed):
        ws.distill.merge(owner, keep_id="tone", other_id="tone")


def test_a_change_may_retire_the_entries_it_now_covers(ws, owner, brain):
    made = ws.brain.propose(
        owner,
        title="Voice",
        statement="Write plainly, warmly, and briefly.",
        evidence="Merging the voice notes",
        revises="voice-guide",
        replaces=["tone"],
    )
    assert made.status == "pending"
    assert brain.proposed[-1]["revises"] == "voice-guide"
    assert brain.proposed[-1]["replaces"] == ["tone"]
    with pytest.raises(ValidationFailed):
        ws.brain.propose(
            owner,
            title="Voice",
            statement="Write plainly.",
            evidence="x",
            revises="voice-guide",
            contradicts=["tone"],
        )


def test_a_summary_reads_the_goals_and_projects_and_its_nudges_come_back(ws, owner, connect, brain):
    ws.brain.set_goals(owner, {"purpose": "Help me run the studio."})
    ws.brain.create_project(owner, name="Webinars", summary="Monthly webinars for CLOs")
    claude = connect()
    nudged = []
    for number in range(3):
        note = ws.notes.create(owner, title=f"Hiring call {number}", body="We need a designer.")
        task = ws.captures.summarize(owner, note.id)
        assert {("brain_entry", "you-goals"), ("brain_project", "webinars")} <= pinned(
            ws, owner, task
        )
        nudged.append((note, task))
    assert "about: one line saying what it is mostly about" in nudged[0][1].instructions
    for note, task in nudged:
        run = ws.bus.claim(claude, task.id).run
        ws.captures.save_digest(
            claude,
            run_id=run.id,
            item_id=note.id,
            summary="A call about hiring a designer.",
            about="Mostly about: hiring a designer",
            new_project="Designer hire",
            off_goal="Hiring",
            points=[{"text": "We need a designer.", "fit": "new", "serves": "goals"}],
        )
    digest = ws.notes.get(owner, nudged[0][0].id).digest
    assert digest["about"] == "Mostly about: hiring a designer"
    assert digest["points"][0]["serves"] == "goals"
    nudges = {n["type"]: n for n in ws.catch_up.plan(owner)["nudges"]}
    assert nudges["start_project"]["name"] == "Designer hire"
    assert nudges["add_goal"]["count"] == 3 and nudges["add_goal"]["subject"] == "Hiring"
    ws.catch_up.dismiss(owner, nudges["add_goal"]["key"])
    assert [n["type"] for n in ws.catch_up.plan(owner)["nudges"]] == ["start_project"]
