"""Skills from the app: a person runs one and sees what it made; a model improves one or
writes a new one, and the proposal waits in Review; a person's own edit applies at once."""

import os

import pytest

from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.ports import BrainSkill
from workspace_core.services.skills import makes_files

KICKOFF = b"""Dana Ruiz: The newsletter goes out every other Thursday.
Sam Lee: And the polls?
Dana Ruiz: Polls run on Tuesdays through December.
Sam Lee: I'll draft the posts for this week.
"""


def test_a_run_follows_the_skill_and_its_result_shows_on_the_skill(ws, owner, connect):
    claude = connect()
    kickoff = ws.captures.bring_in(owner, data=KICKOFF, filename="Kickoff.txt", mime="text/plain")
    task = ws.skills.run(
        owner,
        "/weekly-posts",
        ask="Three posts about the Tuesday polls.",
        capture_id=kickoff.id,
        files=["references/voice.md"],
    )
    assert (task.template, task.status, task.assignee_id) == ("skill", "ready", claude.actor_id)
    assert task.title == "Run /weekly-posts"
    claim = ws.bus.claim(claude, task.id)
    text = claim.packet["instructions"]["text"]
    assert 'get_brain_skill (name "weekly-posts")' in text
    assert "Three posts about the Tuesday polls." in text
    assert "references/voice.md" in text
    assert "save_skill_result" in text
    assert "working directory" not in text  # a skill that writes text needs no folder
    (item,) = claim.packet["inputs"]
    assert item["text"].startswith("Dana Ruiz: The newsletter")
    assert claim.packet["output_contract"]["tool"] == "save_skill_result"
    saved = ws.skills.save_result
    first = saved(claude, run_id=claim.run.id, title="Poll posts", text="Post one.")
    again = saved(claude, run_id=claim.run.id, title="Poll posts", text="Post one, shorter.")
    assert again["artifact_id"] == first["artifact_id"] and again["version"] == 2
    ws.bus.complete(claude, claim.run.id, summary="Three posts.")
    (run,) = ws.skills.runs(owner, "weekly-posts")
    assert run["kind"] == "run" and run["status"] == "done"
    assert run["ask"] == "Three posts about the Tuesday polls."
    assert run["result"]["text"] == "Post one, shorter."
    assert run["capture"]["id"] == kickoff.id
    card = next(c for c in ws.skills.cards(owner)["skills"] if c["name"] == "weekly-posts")
    assert card["last_run"]["status"] == "done" and card["makes_files"] is False
    assert card["triggers"] == ["draft this week's posts"]


def test_only_the_run_saves_its_result_and_only_into_a_skill_run(ws, owner, connect):
    claude = connect()
    task = ws.skills.run(owner, "weekly-posts", ask="One post.")
    claim = ws.bus.claim(claude, task.id)
    improve = ws.skills.improve(owner, "weekly-posts", ask="Shorter hooks.")
    other = ws.bus.claim(claude, improve.id)
    with pytest.raises(ValidationFailed, match="not a skill run"):
        ws.skills.save_result(claude, run_id=other.run.id, title="Wrong", text="Wrong task.")
    with pytest.raises(ValidationFailed):
        ws.skills.save_result(claude, run_id=claim.run.id, title="Empty", text="  ")
    stranger = connect(name="Another model", provider="codex")
    with pytest.raises(PermissionDenied):
        ws.skills.save_result(stranger, run_id=claim.run.id, title="Mine", text="Not mine.")


def test_asking_needs_words_a_known_skill_and_things_the_person_can_see(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.skills.run(owner, "weekly-posts", ask=" ")
    with pytest.raises(NotFound):
        ws.skills.run(owner, "no-such-skill", ask="Anything.")
    with pytest.raises(NotFound):
        ws.skills.run(owner, "weekly-posts", ask="Anything.", files=["references/nothing.md"])
    with pytest.raises(NotFound):
        ws.skills.run(owner, "weekly-posts", ask="Anything.", capture_id="ctx_missing")
    waiting = ws.skills.run(owner, "weekly-posts", ask="Without a model connected.")
    assert (waiting.status, waiting.assignee_id) == ("draft", None)  # the local CLI takes it


def test_a_skill_that_makes_files_runs_in_a_folder_and_lists_what_it_left(
    ws, owner, connect, brain, tmp_path
):
    brain.extra_skills.append(
        BrainSkill(
            name="one-pager",
            category="sales",
            description="A one-page PDF.",
            artifacts=["pdf"],
            depends_on=["shared-assets"],
        )
    )
    assert makes_files(brain.extra_skills[0])
    connect()
    task = ws.skills.run(owner, "one-pager", ask="A one-pager for the polls.")
    assert task.provenance["skill"]["files"] is True
    card = next(c for c in ws.skills.cards(owner)["skills"] if c["name"] == "one-pager")
    assert card["makes_files"] is True and card["used_by"] == [] and card["use"] == "run"
    assert "working directory" in task.instructions and "./skill" in task.instructions
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "one-pager.pdf").write_bytes(b"%PDF-1.4 fake")
    ws.skills.record_files(
        owner, task.id, folder=str(folder), files=[{"name": "one-pager.pdf", "size": 13}]
    )
    (run,) = ws.skills.runs(owner, "one-pager")
    assert run["files"] == [{"name": "one-pager.pdf", "size": 13}]
    assert run["folder"] == str(folder)
    assert ws.skills.made_file(owner, task.id, "one-pager.pdf") == os.path.realpath(
        folder / "one-pager.pdf"
    )
    with pytest.raises(NotFound):
        ws.skills.made_file(owner, task.id, "../secrets.txt")
    with pytest.raises(NotFound):
        ws.skills.made_file(owner, task.id, "other.pdf")


def test_an_improvement_is_proposed_by_its_run_and_waits_in_review(ws, owner, connect, brain):
    claude = connect()
    task = ws.skills.improve(owner, "weekly-posts", ask="Make the hooks shorter.")
    assert (task.template, task.title) == ("skill-draft", "Improve /weekly-posts")
    claim = ws.bus.claim(claude, task.id)
    assert "propose_brain_skill" in claim.packet["instructions"]["text"]
    with pytest.raises(ValidationFailed, match='target "weekly-posts"'):
        ws.skills.propose(claude, run_id=claim.run.id, body="# /other", name="other")
    made = ws.skills.propose(
        claude,
        run_id=claim.run.id,
        target="/weekly-posts",
        body="# /weekly-posts\n\n1. Read the calendar.\n2. Draft short hooks.",
        reason="Shorter hooks, as asked.",
    )
    assert made.status == "pending"
    proposed = brain.proposed[-1]
    assert proposed["kind"] == "skill.update"
    assert f"task:{task.id}" in proposed["sources"] and f"run:{claim.run.id}" in proposed["sources"]
    assert proposed["evidence"] == "Make the hooks shorter."
    ws.bus.complete(claude, claim.run.id, summary="Proposed.")
    (run,) = ws.skills.runs(owner, "weekly-posts")
    assert run["kind"] == "improve" and run["proposal"]["id"] == made.proposal_id
    assert run["proposal"]["status"] == "waiting"
    ws.brain.decide(owner, made.proposal_id, approve=False, reason="Not now.")
    (run,) = ws.skills.runs(owner, "weekly-posts")
    assert run["proposal"] == {"id": made.proposal_id, "status": "rejected"}
    assert ws.events.activity(owner, types=["skill.proposed"])[0].data["change"] == "update"


def test_a_skill_learns_from_something_it_made_or_an_edited_copy(ws, owner, connect):
    claude = connect()
    run = ws.skills.run(owner, "weekly-posts", ask="One post on polls.")
    claim = ws.bus.claim(claude, run.id)
    made = ws.skills.save_result(claude, run_id=claim.run.id, title="Poll post", text="Short hook.")
    ws.bus.complete(claude, claim.run.id, summary="Done.")
    edited = ws.captures.bring_in(owner, data=b"# Edited\n\nShorter hook.", filename="edited.md")
    task = ws.skills.improve(
        owner,
        "weekly-posts",
        ask="Open every post like these.",
        example=made["artifact_id"],
        capture_id=edited.id,
    )
    learning = ws.bus.claim(claude, task.id)
    text = learning.packet["instructions"]["text"]
    assert "Learn from the pinned example (“Poll post” and “edited”)" in text
    kinds = sorted(i["ref"].split(":")[0] for i in learning.packet["inputs"])
    assert kinds == ["artifact", "context_item"]
    assert any(i.get("text") == "Short hook." for i in learning.packet["inputs"])
    assert task.provenance["skill"]["example"]["title"] == "Poll post"
    other = ws.skills.improve(owner, "weekly-posts", ask="Shorter.")
    with pytest.raises(NotFound):
        ws.skills.improve(owner, "weekly-posts", ask="From a stranger.", example=other.id)


def test_an_improvement_can_be_sent_as_edits_to_the_skill_as_it_is(ws, owner, connect, brain):
    claude = connect()
    task = ws.skills.improve(owner, "weekly-posts", ask="Add a review step.")
    claim = ws.bus.claim(claude, task.id)
    assert "Send the change as edits" in claim.packet["instructions"]["text"]
    with pytest.raises(ValidationFailed, match="occurs 0 times"):
        ws.skills.propose(
            claude,
            run_id=claim.run.id,
            target="weekly-posts",
            edits=[{"find": "2. Write.", "replace": "2. Draft."}],
        )
    with pytest.raises(ValidationFailed, match="not both"):
        ws.skills.propose(
            claude,
            run_id=claim.run.id,
            target="weekly-posts",
            body="# /weekly-posts",
            edits=[{"find": "2. Draft.", "replace": "x"}],
        )
    made = ws.skills.propose(
        claude,
        run_id=claim.run.id,
        target="weekly-posts",
        edits=[{"find": "2. Draft.", "replace": "2. Draft.\n3. Read it aloud once."}],
    )
    assert made.status == "pending"
    assert brain.proposed[-1]["statement"] == (
        "1. Read the calendar.\n2. Draft.\n3. Read it aloud once."
    )


def test_edits_land_only_where_they_are_quoted():
    from workspace_core.services.skills import apply_edits

    text = "Step one.\nStep two.\nStep two."
    assert apply_edits(text, [{"find": "one", "replace": "1"}]) == "Step 1.\nStep two.\nStep two."
    with pytest.raises(ValidationFailed, match="occurs 2 times"):
        apply_edits(text, [{"find": "Step two.", "replace": "x"}])
    with pytest.raises(ValidationFailed, match="quotes nothing"):
        apply_edits(text, [{"find": " ", "replace": "x"}])


def test_a_new_skill_is_drafted_from_a_description_or_from_a_capture(ws, owner, connect, brain):
    claude = connect()
    kickoff = ws.captures.bring_in(owner, data=KICKOFF, filename="Kickoff.txt", mime="text/plain")
    task = ws.skills.draft(owner, ask="A skill for poll recap posts.", capture_id=kickoff.id)
    claim = ws.bus.claim(claude, task.id)
    text = claim.packet["instructions"]["text"]
    assert "social" in text  # the categories the Brain uses
    assert "teach from" in text.lower()
    with pytest.raises(ValidationFailed, match="leave out target"):
        ws.skills.propose(claude, run_id=claim.run.id, target="weekly-posts", body="# /x")
    made = ws.skills.propose(
        claude,
        run_id=claim.run.id,
        name="poll-recap",
        category="Social",
        description="Recap a week of polls as one post.",
        triggers=["recap the polls", "recap the polls", "poll recap post"],
        artifacts=["post"],
        loads=["brand/voice"],
        body="# /poll-recap\n\n1. Read the poll results.\n2. Write one post.",
    )
    assert made.status == "pending"
    proposed = brain.proposed[-1]
    assert proposed["kind"] == "skill.create"
    assert proposed["target"]["category"] == "social"
    assert proposed["target"]["triggers"] == ["recap the polls", "poll recap post"]
    assert f"context_item:{kickoff.id}" in proposed["sources"]
    waiting = ws.skills.cards(owner)["waiting"]
    assert [w["name"] for w in waiting] == ["poll-recap"]


def test_a_persons_own_edit_applies_at_once_as_an_undo_point(ws, owner, brain):
    done = ws.skills.edit(
        owner, "weekly-posts", body="# /weekly-posts\n\n1. Draft.", reason="Simpler"
    )
    assert done["checkpoint"]["id"]
    assert brain.proposed[-1]["kind"] == "skill.update"
    assert brain.decided[done["id"]] is True
    with pytest.raises(ValidationFailed):
        ws.skills.edit(owner, "weekly-posts", body=" ")
    # A change waiting in Review is decided first.
    ws.brain.rt.brain.propose_skill(
        proposer="model:Claude",
        sources=[],
        body="# /weekly-posts\n\nWaiting.",
        target="weekly-posts",
    )
    with pytest.raises(Conflict, match="already waiting"):
        ws.skills.edit(owner, "weekly-posts", body="# /weekly-posts\n\n1. Mine.")


def test_a_skill_is_run_here_kept_for_others_or_called_in_a_chat(ws, owner, brain):
    brain.extra_skills += [
        BrainSkill(
            name="cover",
            category="social",
            description="A cover PDF.",
            artifacts=["pdf"],
            depends_on=["shared-assets"],
        ),
        BrainSkill(
            name="carousel",
            category="social",
            description="Carousel slides.",
            artifacts=["pdf"],
            depends_on=["cover", "shared-assets"],
        ),
        BrainSkill(
            name="shared-assets", category="", description="Fonts.", artifacts=["fonts", "logos"]
        ),
        BrainSkill(
            name="end-session",
            category="ops",
            description="Close a session.",
            invocation="explicit",
        ),
    ]
    uses = {c["name"]: (c["use"], c["used_by"]) for c in ws.skills.cards(owner)["skills"]}
    assert uses["cover"] == ("run", ["carousel"])  # others build on it, and it makes a PDF
    assert uses["shared-assets"] == ("support", ["cover", "carousel"])
    assert uses["end-session"] == ("chat", [])
    assert uses["weekly-posts"] == ("run", [])
    with pytest.raises(ValidationFailed, match="other skills use its files"):
        ws.skills.run(owner, "shared-assets", ask="Anything.")
    with pytest.raises(ValidationFailed, match="in a conversation"):
        ws.skills.run(owner, "end-session", ask="Anything.")


def test_a_skill_keeps_its_versions(ws, owner):
    (current,) = ws.skills.versions(owner, "weekly-posts", with_text=True)
    assert current["current"] and current["body"].startswith("1. Read the calendar.")
    with pytest.raises(NotFound):
        ws.skills.versions(owner, "no-such-skill")
