"""Distillation: a model finds what will last in a person's notes and proposes it to the Brain."""

import pytest

from workspace_core.errors import NotFound, PermissionDenied, ValidationFailed


@pytest.fixture
def notes(ws, owner):
    return [
        ws.notes.create(owner, title="Posting days", body="We post Tue and Thu."),
        ws.notes.create(owner, title="Tone", body="Plain words, no hype."),
    ]


def test_a_request_is_a_ready_task_with_the_notes_pinned(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[n.id for n in notes], assignee_id=claude.actor_id)
    assert (task.template, task.status, task.review_policy) == ("distill", "ready", "auto")
    assert task.title == "Pull what matters from 2 items"
    assert task.assignee_id == claude.actor_id
    assert "propose_brain_entry" in task.instructions and "run_id" in task.instructions
    assert "Posting days" in (task.brain_request or "")
    pins = ws.tasks.pins(owner, task.id)
    assert {(p.ref_id, p.pinned_version) for p in pins} == {(n.id, 1) for n in notes}


def test_a_request_names_one_note_by_its_title(ws, owner, notes, connect):
    task = ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=connect().actor_id)
    assert task.title == "Pull what matters from Posting days"


def test_a_request_needs_something_to_read(ws, owner, notes, connect):
    claude = connect()
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[], assignee_id=claude.actor_id)
    with pytest.raises(NotFound):
        ws.distill.request(owner, item_ids=["ctx_missing"], assignee_id=claude.actor_id)
    empty = ws.notes.create(owner, title="Later")
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[empty.id], assignee_id=claude.actor_id)
    ws.notes.archive(owner, notes[1].id)
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[1].id], assignee_id=claude.actor_id)


def test_the_model_is_chosen_for_you_when_there_is_one_answer(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id])
    assert task.assignee_id == claude.actor_id


def test_with_several_models_you_choose_or_configure_one(ws, owner, notes, connect):
    connect()
    codex = connect(name="Codex", provider="codex")
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[0].id])
    ws.distill.configure(owner, assignee_id=codex.actor_id)
    assert ws.distill.settings(owner) == {
        "assignee_id": codex.actor_id,
        "triage": None,
        "model": "haiku",
    }
    assert ws.distill.request(owner, item_ids=[notes[0].id]).assignee_id == codex.actor_id
    with pytest.raises(ValidationFailed):
        ws.distill.configure(owner, assignee_id=owner.actor_id)
    with pytest.raises(PermissionDenied):
        ws.distill.configure(codex, assignee_id=None)


def test_without_a_model_a_request_waits_for_the_first_one(ws, owner, notes, connect):
    with pytest.raises(ValidationFailed):
        ws.distill.request(owner, item_ids=[notes[0].id])
    task = ws.distill.request(owner, item_ids=[notes[0].id], wait=True)
    assert (task.status, task.assignee_id) == ("draft", None)
    (request,) = ws.distill.requests(owner)
    assert request.waiting
    claude = connect()
    (started,) = ws.distill.assign_waiting(ws.system())
    assert (started.id, started.status, started.assignee_id) == (task.id, "ready", claude.actor_id)


def test_guidance_and_the_note_reach_the_model(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id], guidance="Focus on the posting rules.")
    packet = ws.bus.claim(claude, task.id).packet
    assert "Focus on the posting rules." in packet["instructions"]["text"]
    (note,) = packet["inputs"]
    assert (note["title"], note["text"], note["type"]) == (
        "Posting days",
        "We post Tue and Thu.",
        "page",
    )


def test_a_request_runs_end_to_end_and_reports_its_proposals(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[n.id for n in notes])
    run = ws.bus.claim(claude, task.id).run
    first = ws.brain.propose(
        claude,
        title="Posting days",
        statement="We post on Tuesdays and Thursdays.",
        evidence="Posting days note",
        sources=[f"context_item:{notes[0].id}"],
        run_id=run.id,
    )
    ws.brain.propose(
        claude,
        title="Tone",
        statement="Plain words, no hype.",
        evidence="Tone note",
        sources=[f"context_item:{notes[1].id}"],
        run_id=run.id,
    )
    ws.bus.complete(claude, run.id, summary="Two durable statements")
    assert ws.tasks.get(owner, task.id).status == "done"
    ws.brain.decide(owner, first.proposal_id, approve=True)
    (request,) = ws.distill.requests(owner)
    assert (request.task_id, request.status) == (task.id, "done")
    assert request.items == [n.id for n in notes]
    assert request.summary == "Two durable statements"
    assert request.assignee_name == "Claude Code"
    assert [(p.title, p.status) for p in request.proposals] == [
        ("Posting days", "approved"),
        ("Tone", "pending"),
    ]


def test_a_proposal_records_the_capture_version_place_speaker_and_words_it_read(
    ws, owner, notes, connect, brain
):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id])
    run = ws.bus.claim(claude, task.id).run
    ws.brain.propose(
        claude,
        title="Posting days",
        statement="We post on Tuesdays and Thursdays.",
        evidence="Posting days note",
        sources=[f"context_item:{notes[0].id}"],
        run_id=run.id,
        source_locator="line 1",
        source_excerpt="We post on Tuesdays and Thursdays.",
    )
    sent = brain.proposed[-1]["extra"]
    assert sent["source_id"] == f"context_item:{notes[0].id}"
    assert sent["source_version"].startswith("r1")
    assert (sent["source_locator"], sent["source_speaker"]) == ("line 1", "unknown")
    assert sent["source_excerpt"] == "We post on Tuesdays and Thursdays."


def test_a_sheet_value_goes_to_its_sheet_through_the_same_inbox(ws, owner, notes, brain):
    ws.brain.propose(
        owner,
        title="Dana confirmed",
        statement="Dana Ruiz is confirmed for November 12.",
        evidence="kickoff call",
        sources=[f"context_item:{notes[0].id}"],
        destination="sheet",
        place={"sheet": "guests", "row": "Dana Ruiz", "column": "Status", "value": "Confirmed"},
    )
    sent = brain.proposed[-1]["extra"]
    assert sent["destination"] == "sheet"
    assert sent["place"]["column"] == "Status"


def test_a_typed_piece_without_its_place_is_refused(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.brain.propose(
            owner,
            title="Dana confirmed",
            statement="Dana Ruiz is confirmed.",
            evidence="kickoff call",
            destination="sheet",
            place={"sheet": "guests"},
        )


def test_a_place_or_speaker_without_its_capture_is_refused(ws, owner):
    with pytest.raises(ValidationFailed):
        ws.brain.propose(
            owner,
            title="Posting days",
            statement="We post on Tuesdays.",
            evidence="Taylor said so",
            source_speaker="Taylor",
        )


def test_requests_can_be_listed_for_one_note(ws, owner, notes, connect):
    claude = connect()
    one = ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=claude.actor_id)
    ws.distill.request(owner, item_ids=[notes[1].id], assignee_id=claude.actor_id)
    assert [r.task_id for r in ws.distill.requests(owner, item_id=notes[0].id)] == [one.id]
    assert len(ws.distill.requests(owner)) == 2


def test_an_undone_approval_is_waiting_again(ws, owner, notes, connect):
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id])
    run = ws.bus.claim(claude, task.id).run
    made = ws.brain.propose(
        claude,
        title="Posting days",
        statement="We post on Tuesdays.",
        evidence="note",
        run_id=run.id,
    )
    point = ws.brain.decide(owner, made.proposal_id, approve=True)["checkpoint"]
    assert ws.distill.requests(owner)[0].proposals[0].status == "approved"
    ws.brain.undo(owner, point["id"])
    assert ws.distill.requests(owner)[0].proposals[0].status == "pending"


def test_a_proposal_can_suggest_a_must_hold_and_waits_like_any_other(ws, owner, brain):
    made = ws.brain.propose(
        owner,
        title="Peanut allergy",
        statement="Ollie is allergic to peanuts.",
        kind="rule",
        evidence="Taylor said so",
        must_hold={
            "applies_to": "food",
            "triggers": "dinner, lunchbox, restaurant",
            "must_text": "No peanuts for Ollie, ever.",
        },
    )
    assert made.status == "pending"
    sent = brain.proposed[-1]["extra"]["must_hold"]
    assert sent == {
        "applies_to": "food",
        "triggers": "dinner, lunchbox, restaurant",
        "must_text": "No peanuts for Ollie, ever.",
    }
    with pytest.raises(ValidationFailed):
        ws.brain.propose(
            owner,
            title="Bad",
            statement="Bad.",
            evidence="x",
            must_hold={"must_text": "x" * 500},
        )


def test_text_read_before_or_held_word_for_word_makes_no_model_call(
    ws, owner, notes, connect, brain
):
    """Hash dedupe before any model call (brain-logic plan 7.1)."""
    from workspace_core.domain import statements
    from workspace_core.errors import Conflict

    claude = connect()
    ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=claude.actor_id)
    again = ws.notes.create(owner, title="Posting days, pasted twice", body="We post  Tue and THU.")
    with pytest.raises(Conflict) as caught:
        ws.distill.request(owner, item_ids=[again.id], assignee_id=claude.actor_id)
    assert "the same text was read before (Posting days)" in str(caught.value)
    # Asking again about the same capture still reads it.
    assert ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=claude.actor_id)
    # What the Brain holds word for word is not read; the rest of the request goes on.
    brain.held_texts = {statements.fingerprint("Plain words, no hype.")}
    task = ws.distill.request(
        owner, item_ids=[notes[1].id, again.id, notes[0].id], assignee_id=claude.actor_id
    )
    about = task.provenance["distill"]
    assert about["items"] == [notes[0].id]
    assert {s["id"] for s in about["skipped"]} == {notes[1].id, again.id}
    assert "word for word" in next(s["why"] for s in about["skipped"] if s["id"] == notes[1].id)


def test_what_was_left_out_is_found_by_its_words_and_scored_against_the_goals_now(
    ws, owner, notes, connect, brain
):
    """The left-out list as a searchable record, re-scored when the goals change (7.2)."""
    claude = connect()
    task = ws.distill.request(owner, item_ids=[notes[0].id], assignee_id=claude.actor_id)
    run = ws.bus.claim(claude, task.id).run
    ws.bus.complete(
        claude,
        run.id,
        summary="0 proposals",
        left_out=[
            {
                "statement": "The webinar sign-ups doubled after the newsletter mention.",
                "why": "serves no goal or project",
            },
            {"statement": "The coffee was cold.", "why": "small talk"},
        ],
    )
    everything = ws.distill.left_out(owner)
    assert [r["statement"] for r in everything] == [
        "The webinar sign-ups doubled after the newsletter mention.",
        "The coffee was cold.",
    ]
    assert everything[0]["source"] == task.title and everything[0]["fits"] == []
    assert [r["statement"] for r in ws.distill.left_out(owner, q="coffee")] == [
        "The coffee was cold."
    ]
    # The goals change: what was left out for serving none is scored again, and now fits.
    brain.goal_answers = {"purpose": "Grow webinar sign-ups through the newsletter."}
    now = ws.distill.left_out(owner)[0]
    assert now["for_goals"] and set(now["fits"]) >= {"webinar", "newsletter"}


TRANSCRIPT = """Jordan: Morning all, how was the weekend?
Maya: Good, thanks. Coffee first.
Jordan: We decided the webinar moves to Tuesdays at noon from November.
Maya: Agreed, and sign-ups close two days before.
Jordan: Great, talk soon."""


def test_triage_is_off_until_chosen_and_then_only_kept_parts_reach_the_model(ws, owner, connect):
    """Triage (7.2, step 2) behind a switch: a cheaper model names the parts worth distilling."""
    from workspace_core.errors import Conflict

    claude = connect()
    asked = []

    def triager(model, text):
        asked.append(model)
        return [2, 3] if "webinar" in text else []

    ws.distill.triager = triager
    call = ws.notes.create(owner, title="Monday call", body=TRANSCRIPT)
    ws.distill.request(owner, item_ids=[call.id], assignee_id=claude.actor_id)
    assert asked == []  # off by default
    ws.distill.configure(owner, triage="claude")
    again = ws.notes.create(owner, title="Monday call, again", body=TRANSCRIPT + "\nMaya: Bye.")
    task = ws.distill.request(owner, item_ids=[again.id], assignee_id=claude.actor_id)
    assert asked == ["claude"]
    assert task.provenance["distill"]["triage"][again.id]["kept"] == [2, 3]
    packet = ws.bus.packet(owner, task_id=task.id)
    (item,) = [i for i in packet["inputs"] if i["ref"] == f"context_item:{again.id}"]
    assert "Tuesdays at noon" in item["text"] and "Coffee first" not in item["text"]
    assert "Triage kept 2 of" in item["note"]
    chatter = ws.notes.create(owner, title="Hallway", body="A: Hi.\nB: Hello.\nA: Bye now.")
    with pytest.raises(Conflict) as caught:
        ws.distill.request(owner, item_ids=[chatter.id], assignee_id=claude.actor_id)
    assert "triage found nothing durable" in str(caught.value)
    with pytest.raises(ValidationFailed):
        ws.distill.configure(owner, triage="gpt-anything")


def test_reading_what_comes_in_runs_on_haiku_unless_the_owner_chooses(ws, owner):
    assert ws.distill.settings(owner)["model"] == "haiku"
    assert ws.distill.configure(owner, model="sonnet")["model"] == "sonnet"
    assert ws.distill.configure(owner, model="claude-opus-5-5")["model"] == "claude-opus-5-5"
    assert ws.distill.configure(owner, model=None)["model"] is None  # the CLI's own default
    with pytest.raises(ValidationFailed):
        ws.distill.configure(owner, model="gpt-anything")
