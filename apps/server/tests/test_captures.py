"""Captures over REST: bring in audio, a transcript or a document; play or download what was
brought in; and turn speech into text on this computer."""

import os

import pytest

from workspace_server.digests import DigestWorker
from workspace_server.runners import RunnerStatus
from workspace_server.speech import Speech, TranscriptionWorker, paragraphs

HERE = os.path.dirname(os.path.abspath(__file__))
TALK = os.path.join(
    HERE, "fixtures", "talk.wav"
)  # "We keep the faculty videos and drop the podcast."
MODELS = os.environ.get("BRAIN_TEST_MODELS", "")
VTT = (
    "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n<v Dana Ruiz>We keep the videos.</v>\n\n"
    "00:00:04.000 --> 00:00:06.000\n<v Sam Lee>And the podcast?</v>\n"
)


class Spoken:
    """A speech engine that hears the same thing every time."""

    model = "small.en"

    def __init__(self, text="We keep the videos.", error=None):
        self.text, self.error, self.calls = text, error, []

    def ready(self):
        return True

    def transcribe(self, path, *, careful, progress=None):
        self.calls.append((os.path.basename(path), careful))
        if self.error:
            raise RuntimeError(self.error)
        if progress:
            progress(0.5)
        return self.text, 3.0


def upload(owner, name, data, mime):
    return owner.post("/api/captures", files={"file": (name, data, mime)}, data={"title": ""})


def test_a_recording_is_kept_and_waits_for_its_text(owner, runtime):
    made = owner.ok(upload(owner, "Kickoff call.m4a", b"fake audio", "audio/mp4"), 201)
    assert (made["capture"], made["title"], made["body"]) == ("recording", "Kickoff call", "")
    assert made["transcription"]["state"] == "pending"
    played = owner.get(f"/api/captures/{made['id']}/original")
    assert played.content == b"fake audio" and played.headers["content-type"] == "audio/mp4"
    assert played.headers["content-disposition"].startswith("inline")
    saved = owner.get(f"/api/captures/{made['id']}/original?download=true")
    assert saved.headers["content-disposition"].startswith("attachment")
    # The worker turns it into text, with the careful search a recording gets.
    spoken = Spoken()
    assert TranscriptionWorker(runtime.ws, spoken).run_once() is True
    assert spoken.calls[0][1] is True
    done = owner.ok(owner.get(f"/api/notes/{made['id']}"))
    assert (done["body"], done["transcription"]["state"]) == ("We keep the videos.", "ready")
    assert TranscriptionWorker(runtime.ws, spoken).run_once() is False  # nothing left


def test_a_talk_is_transcribed_quickly_and_named_by_what_was_said(owner, runtime):
    made = owner.ok(
        owner.post("/api/captures/talk", files={"audio": ("blob", b"webm", "audio/webm")}), 201
    )
    assert (made["capture"], made["title"]) == ("talk", "Talk")
    spoken = Spoken("Send Dana the poll plan by Thursday.")
    TranscriptionWorker(runtime.ws, spoken).run_once()
    assert spoken.calls[0][1] is False  # quick: greedy
    assert owner.ok(owner.get(f"/api/notes/{made['id']}"))["title"] == (
        "Send Dana the poll plan by Thursday."
    )


def test_a_failed_transcription_is_tried_again_and_silence_is_said(owner, runtime):
    made = owner.ok(upload(owner, "call.mp3", b"fake audio", "audio/mpeg"), 201)
    TranscriptionWorker(runtime.ws, Spoken(error="bad audio")).run_once()
    failed = owner.ok(owner.get(f"/api/notes/{made['id']}"))["transcription"]
    assert failed["state"] == "failed" and "bad audio" in failed["error"]
    again = owner.ok(owner.post(f"/api/captures/{made['id']}/retry"))
    assert again["transcription"]["state"] == "pending"
    TranscriptionWorker(runtime.ws, Spoken(text="  ")).run_once()
    quiet = owner.ok(owner.get(f"/api/notes/{made['id']}"))["transcription"]
    assert quiet["error"] == "Nothing was heard in it."


def test_a_transcript_reads_as_turns_and_a_model_never_sees_it(owner, model):
    made = owner.ok(upload(owner, "Kickoff.vtt", VTT.encode(), "text/vtt"), 201)
    assert made["capture"] == "transcript"
    assert made["body"] == (
        "**Dana Ruiz** [00:01] We keep the videos.\n\n**Sam Lee** [00:04] And the podcast?"
    )
    assert model.get(f"/api/captures/{made['id']}/original").status_code == 404
    refused = upload(owner, "photo.png", b"\x89PNG", "image/png")
    assert refused.status_code == 422 and "can't be read here" in refused.text


def test_the_speech_model_is_downloaded_only_when_asked(owner, model, runtime, monkeypatch):
    status = owner.ok(owner.get("/api/speech"))
    assert {"installed", "model", "present", "ready", "downloading", "about_mb"} <= set(status)
    asked = []
    monkeypatch.setattr(
        runtime.speech, "start_download", lambda: asked.append(1) or {"downloading": True}
    )
    assert owner.ok(owner.post("/api/speech/download"), 202) == {"downloading": True}
    assert model.post("/api/speech/download").status_code == 403
    assert asked == [1]


def test_pieces_of_speech_become_paragraphs_at_pauses():
    timed = [(0.0, 2.0, " One."), (2.5, 4.0, " Two."), (9.0, 10.0, " Three.")]
    assert paragraphs(timed, timestamps=True) == "[00:00] One. Two.\n\n[00:09] Three."
    assert paragraphs(timed, timestamps=False) == "One. Two.\n\nThree."


@pytest.mark.skipif(
    not MODELS or not Speech(MODELS).ready(),
    reason="needs BRAIN_TEST_MODELS with the faster-whisper small.en model",
)
def test_a_real_talk_is_heard_on_this_computer():
    text, duration = Speech(MODELS).transcribe(TALK, careful=False)
    assert 2 < duration < 6
    assert "faculty videos" in text.lower() and "podcast" in text.lower()


def test_a_model_writes_the_digest_beside_the_capture(owner, model):
    made = owner.ok(upload(owner, "Kickoff.vtt", VTT.encode(), "text/vtt"), 201)
    assert made["digest"] == {"state": "queued"}  # summarized as it arrives
    task = owner.ok(owner.post(f"/api/captures/{made['id']}/summarize", json={}), 201)
    assert (task["template"], task["status"]) == ("digest", "ready")
    claimed = model.tool("claim_task", task_id=task["id"])
    assert "save_digest" in claimed["content"][0]["text"]
    run_id = claimed["structuredContent"]["run"]["id"]
    saved = model.tool(
        "save_digest",
        run_id=run_id,
        item_id=made["id"],
        summary="Dana keeps the videos; Sam asks about the podcast.",
        points=[{"text": "The faculty videos stay.", "fit": "new"}],
        people=["Dana Ruiz", "Sam Lee"],
    )
    assert "Saved the digest (1 key points)" in saved["content"][0]["text"]
    model.tool("complete_task", run_id=run_id, summary="Wrote the digest")
    digest = owner.ok(owner.get(f"/api/notes/{made['id']}"))["digest"]
    assert (digest["state"], digest["people"]) == ("ready", ["Dana Ruiz", "Sam Lee"])
    assert owner.ok(owner.get(f"/api/tasks/{task['id']}"))["status"] == "done"


def test_summaries_can_be_turned_off_and_related_entries_show_at_once(owner):
    assert owner.ok(owner.get("/api/captures/settings")) == {"summarize": True}
    assert owner.ok(owner.put("/api/captures/settings", json={"summarize": False})) == {
        "summarize": False
    }
    made = owner.ok(
        upload(owner, "Pricing.md", b"# Pricing\n\nThe day rate for design work.", "text/markdown"),
        201,
    )
    assert made["digest"] is None
    related = owner.ok(owner.get(f"/api/captures/{made['id']}/related"))
    assert isinstance(related, list)


class Runs:
    """The local CLI runner, as the digest worker sees it."""

    def __init__(self, installed=True, busy=False):
        self.runs = {"r1": type("Run", (), {"status": "running"})()} if busy else {}
        self.installed, self.started = installed, []

    def statuses(self, who):
        return [
            RunnerStatus(
                "claude", "Claude Code", "claude-code", True, self.installed, "2.1", True, "", ""
            )
        ]

    def start(self, who, runner_id, task_id):
        self.started.append((runner_id, task_id))


def test_the_digest_worker_runs_one_summary_at_a_time_with_the_local_cli(owner, runtime):
    made = owner.ok(upload(owner, "Kickoff.vtt", VTT.encode(), "text/vtt"), 201)
    busy = Runs(busy=True)
    assert DigestWorker(runtime.ws, busy).run_once() is False and busy.started == []
    runs = Runs()
    assert DigestWorker(runtime.ws, runs).run_once() is True
    ((runner, task_id),) = runs.started
    assert runner == "claude"
    note = owner.ok(owner.get(f"/api/notes/{made['id']}"))
    assert (note["digest"]["state"], note["digest"]["task_id"]) == ("waiting", task_id)
    assert DigestWorker(runtime.ws, runs).run_once() is False  # nothing else waits
    later = owner.ok(upload(owner, "Weekly.vtt", VTT.encode(), "text/vtt"), 201)
    away = Runs(installed=False)
    assert DigestWorker(runtime.ws, away).run_once() is True and away.started == []
    assert owner.ok(owner.get(f"/api/notes/{later['id']}"))["digest"]["state"] == "waiting"


def test_a_capture_says_where_it_stands_and_can_be_kept_out(owner):
    made = owner.ok(upload(owner, "Call notes.vtt", VTT.encode(), "text/vtt"), 201)
    found = owner.ok(owner.get(f"/api/captures/status?ids={made['id']}"))[made["id"]]
    assert (found["status"], found["stage"]) == ("captured", "captured")
    out = owner.ok(owner.post(f"/api/captures/{made['id']}/exclude", json={"reason": "Personal"}))
    assert (out["status"], out["detail"]) == ("excluded", "Personal")
    back = owner.ok(owner.post(f"/api/captures/{made['id']}/include"))
    assert back["status"] == "captured"
    refused = owner.post(f"/api/captures/{made['id']}/read-again")
    assert refused.status_code == 409


def test_a_receipt_names_the_captures_not_searchable_yet(owner, runtime):
    owner.ok(upload(owner, "Call notes.vtt", VTT.encode(), "text/vtt"), 201)
    packet = runtime.ws.rt.brain.brain.context("What did we decide about the videos?")
    found = owner.ok(owner.get(f"/api/brain/receipts/{packet.data['packet_id']}"))
    assert any(u.startswith("Not searchable yet: Call notes") for u in found["unknown"])
    assert "not proof" in found["note"]
