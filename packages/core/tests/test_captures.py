"""Captures: what a person brings in (a talk, a recording, a transcript, a document) waits in
their notes, private, with its original kept; audio gets its text from the worker."""

import pytest

from workspace_core.errors import Conflict, NotFound, PermissionDenied, ValidationFailed
from workspace_core.services.captures import looks_like_transcript

TEAMS = b"""Dana Ruiz: We keep the faculty videos and film all three in October.
Sam Lee: And the podcast?
Dana Ruiz: We drop it. Half the money goes to a client case study.
Sam Lee: Fine, I'll update the proposal tonight.
"""


class Markdown:
    """The server's document reader, as far as these tests need it."""

    def extract(self, data, filename, mime):
        return data.decode()

    def markdown(self, data, filename):
        return f"# {filename}\n\n{data.decode()}" if filename.endswith(".docx") else None


def test_a_recording_waits_for_its_text_and_keeps_its_audio(ws, owner):
    note = ws.captures.bring_in(
        owner, data=b"RIFF....WAVEfmt ", filename="Kickoff call.m4a", mime="audio/mp4"
    )
    assert (note.capture, note.title, note.body) == ("recording", "Kickoff call", "")
    assert note.original == {"filename": "Kickoff call.m4a", "mime": "audio/mp4", "size": 16}
    assert note.transcription == {
        "state": "pending",
        "progress": 0.0,
        "duration": None,
        "error": None,
    }
    assert [n.id for n in ws.notes.list(owner)] == [note.id]  # one of the person's notes
    filename, mime, path = ws.captures.original(owner, note.id)
    assert (filename, mime) == ("Kickoff call.m4a", "audio/mp4")
    with open(path, "rb") as handle:
        assert handle.read() == b"RIFF....WAVEfmt "
    with pytest.raises(Conflict, match="still being turned into text"):
        ws.notes.save(owner, note.id, body="typed over it")


def test_a_talk_takes_its_first_line_as_its_title_once_transcribed(ws, owner):
    talk = ws.captures.bring_in(owner, data=b"webm", filename="", mime="audio/webm", talk=True)
    assert (talk.capture, talk.title) == ("talk", "Talk")
    claim = ws.captures.claim()
    assert (claim.id, claim.kind, claim.filename) == (talk.id, "talk", "talk.webm")
    assert ws.captures.claim() is None  # one at a time: the next waits
    ws.captures.progress(talk.id, 0.5)
    assert ws.notes.get(owner, talk.id).transcription["state"] == "working"
    assert ws.notes.get(owner, talk.id).transcription["progress"] == 0.5
    ws.captures.transcribed(
        talk.id,
        text="Remind me to send Dana the poll plan.\n\nBy Thursday.",
        duration=4.2,
        model="small.en",
    )
    done = ws.notes.get(owner, talk.id)
    assert (done.title, done.body) == (
        "Remind me to send Dana the poll plan.",
        "Remind me to send Dana the poll plan.\n\nBy Thursday.",
    )
    assert done.transcription == {"state": "ready", "progress": 1.0, "duration": 4.2, "error": None}
    versions = ws.notes.versions(owner, talk.id)
    assert (versions[0].label, versions[0].sealed) == ("Transcribed on this computer", True)
    assert ws.notes.save(owner, talk.id, body="Edited after.").body == "Edited after."


def test_a_failed_transcription_says_why_and_can_be_tried_again(ws, owner):
    note = ws.captures.bring_in(owner, data=b"audio", filename="call.mp3", mime="audio/mpeg")
    ws.captures.claim()
    ws.captures.failed(note.id, "Nothing was heard in it.")
    failed = ws.notes.get(owner, note.id)
    assert failed.transcription["state"] == "failed"
    assert failed.transcription["error"] == "Nothing was heard in it."
    assert ws.captures.retry(owner, note.id).transcription["state"] == "pending"
    with pytest.raises(Conflict):
        ws.captures.retry(owner, note.id)


def test_a_stopped_server_leaves_nothing_half_done(ws, owner):
    note = ws.captures.bring_in(owner, data=b"audio", filename="call.mp3", mime="audio/mpeg")
    ws.captures.claim()
    assert ws.captures.requeue() == 1
    assert ws.notes.get(owner, note.id).transcription["state"] == "pending"
    ws.notes.archive(owner, note.id)
    assert ws.captures.claim() is None  # set aside: not transcribed


def test_a_transcript_or_a_document_reads_at_once(ws, owner):
    transcript = ws.captures.bring_in(
        owner, data=TEAMS, filename="kickoff-call_2026-10-05.txt", mime="text/plain"
    )
    assert transcript.title == "kickoff call 2026-10-05"  # a date keeps its dashes
    assert (transcript.capture, transcript.transcription) == ("transcript", None)
    assert transcript.body.startswith("Dana Ruiz: We keep the faculty videos")
    plain = ws.captures.bring_in(owner, data=b"# Ideas\n\nShorter posts.\n", filename="ideas.md")
    assert (plain.capture, plain.title, plain.body) == (
        "document",
        "ideas",
        "# Ideas\n\nShorter posts.",
    )
    with pytest.raises(ValidationFailed, match="can't be read here"):
        ws.captures.bring_in(owner, data=b"PK...", filename="Brief.docx")  # no reader
    ws.captures.rt.extractor = Markdown()
    brief = ws.captures.bring_in(owner, data=b"Who we want to reach.", filename="Q4 brief.docx")
    assert (brief.capture, brief.title, brief.body) == (
        "document",
        "Q4 brief",
        "# Q4 brief.docx\n\nWho we want to reach.",
    )
    assert looks_like_transcript("[00:01] Hi\n[00:05] Hello\n[00:09] Shall we start\n[00:12] Yes")
    assert not looks_like_transcript("# Plan\n\nOne.\n\nTwo.\n\nThree.\n\nFour.")


def test_a_document_is_filed_as_itself_so_the_brain_keeps_its_shape(ws, owner, brain):
    ws.captures.rt.extractor = Markdown()
    brief = ws.captures.bring_in(owner, data=b"Who we want to reach.", filename="Q4 brief.docx")
    ws.notes.to_brain(owner, brief.id, project="q4")
    sent = brain.uploaded[-1]
    assert (sent["filename"], sent["data"], sent["project"]) == (
        "Q4 brief.docx",
        b"Who we want to reach.",
        "q4",
    )
    talk = ws.captures.bring_in(owner, data=b"webm", filename="", mime="audio/webm", talk=True)
    ws.captures.claim()
    ws.captures.transcribed(
        talk.id, text="Polls every other Tuesday.", duration=2, model="small.en"
    )
    ws.notes.to_brain(owner, talk.id)
    assert (
        brain.uploaded[-1]["data"]
        == b"# Polls every other Tuesday.\n\nPolls every other Tuesday.\n"
    )


def test_captures_stay_private_and_only_people_bring_things_in(ws, owner, connect):
    note = ws.captures.bring_in(owner, data=b"audio", filename="call.mp3", mime="audio/mpeg")
    model = connect()
    assert ws.notes.list(model) == []
    with pytest.raises(NotFound):
        ws.captures.original(model, note.id)
    with pytest.raises(PermissionDenied):
        ws.captures.bring_in(model, data=b"audio", filename="call.mp3", mime="audio/mpeg")
    with pytest.raises(ValidationFailed, match="empty"):
        ws.captures.bring_in(owner, data=b"", filename="call.mp3")


def test_a_digest_is_asked_for_and_saved_by_the_run_that_reads_it(ws, owner, connect):
    transcript = ws.captures.bring_in(owner, data=TEAMS, filename="Kickoff.txt", mime="text/plain")
    claude = connect()
    task = ws.captures.summarize(owner, transcript.id, guidance="Say who owns each action.")
    assert (task.template, task.status, task.assignee_id) == ("digest", "ready", claude.actor_id)
    assert ws.notes.get(owner, transcript.id).digest["state"] == "waiting"
    claim = ws.bus.claim(claude, task.id)
    packet, run_id = claim.packet, claim.run.id
    assert "Say who owns each action." in packet["instructions"]["text"]
    assert "save_digest" in packet["instructions"]["text"]
    (item,) = packet["inputs"]
    assert item["text"].startswith("Dana Ruiz: We keep the faculty videos")
    saved = ws.captures.save_digest(
        claude,
        run_id=run_id,
        item_id=transcript.id,
        summary="The kickoff kept the videos and dropped the podcast.",
        points=[
            {"text": "Three faculty videos, filmed in October.", "fit": "new"},
            {
                "text": "The podcast is dropped.",
                "fit": "clashes",
                "entry": "brain:media-plan",
                "why": "The plan funds it.",
            },
            {"text": "Odd fit", "fit": "maybe"},
        ],
        actions=["Sam updates the proposal tonight.", "Sam updates the proposal tonight."],
        people=["Dana Ruiz", "Sam Lee"],
    )
    assert saved["state"] == "ready" and saved["task_id"] == task.id
    digest = ws.notes.get(owner, transcript.id).digest
    assert digest["points"][1] == {
        "text": "The podcast is dropped.",
        "fit": "clashes",
        "entry": "media-plan",
        "why": "The plan funds it.",
    }
    assert digest["points"][2]["fit"] == "new"  # an unknown fit is read as new
    assert digest["actions"] == ["Sam updates the proposal tonight."]
    other = ws.captures.bring_in(owner, data=b"# Other\n\nText.", filename="other.md")
    with pytest.raises(NotFound):
        ws.captures.save_digest(claude, run_id=run_id, item_id=other.id, summary="Wrong item.")
    stranger = connect(name="Another model", provider="codex")
    with pytest.raises(PermissionDenied):
        ws.captures.save_digest(stranger, run_id=run_id, item_id=transcript.id, summary="Not mine.")


def test_what_is_brought_in_is_summarized_once_its_text_is_in_unless_turned_off(ws, owner):
    assert ws.captures.settings(owner) == {"summarize": True}
    recording = ws.captures.bring_in(owner, data=b"audio", filename="call.mp3", mime="audio/mpeg")
    document = ws.captures.bring_in(owner, data=b"# Plan\n\nShorter posts.", filename="plan.md")
    typed = ws.notes.create(owner, title="Typed", body="Not summarized by itself.")
    assert ws.notes.get(owner, recording.id).digest == {"state": "queued"}
    assert ws.notes.get(owner, typed.id).digest is None
    assert ws.captures.to_summarize() == [document.id]  # the recording has no text yet
    ws.captures.claim()
    ws.captures.transcribed(
        recording.id, text="Polls every other Tuesday.", duration=3, model="small.en"
    )
    # oldest first: the recording came in before the document (the same moment here, so the
    # order they were made in decides, on every database)
    assert ws.captures.to_summarize() == [recording.id, document.id]
    ws.captures.summarize(owner, document.id)  # no model yet: it waits for one
    assert ws.captures.to_summarize() == [recording.id]
    ws.captures.configure(owner, summarize=False)
    later = ws.captures.bring_in(owner, data=b"# Later\n\nText.", filename="later.md")
    assert ws.notes.get(owner, later.id).digest is None
    assert later.id not in ws.captures.to_summarize()
    with pytest.raises(ValidationFailed, match="no text"):
        ws.captures.summarize(
            owner, ws.captures.bring_in(owner, data=b"a", filename="a.mp3", mime="audio/mpeg").id
        )


def test_related_entries_are_found_part_by_part(ws, owner):
    text = ("Polls every other Tuesday. " * 40) + "Keep the brand voice plain and warm. " * 5
    capture = ws.captures.bring_in(
        owner, data=text.encode(), filename="sync.txt", mime="text/plain"
    )
    related = ws.captures.related(owner, capture.id)
    assert [r["id"] for r in related] == ["voice-guide"]  # found in a later part, not the start
    assert related[0]["title"] == "Voice guide"
