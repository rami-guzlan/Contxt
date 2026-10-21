"""Captures over REST: what a person brings in (a talk, a recording, a transcript, a document),
its original back for playing or downloading, and speech to text on this computer."""

from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from workspace_core.domain.records import Task
from workspace_core.errors import Conflict, PermissionDenied, ValidationFailed
from workspace_core.services.captures import MAX_ORIGINAL

from ..deps import WS, Who
from ..files import served
from ..schemas import CaptureSettingsIn, ExcludeIn, SummarizeIn

router = APIRouter()
MAX_DICTATION = 25 * 1024 * 1024  # a few minutes of talk


async def _read(upload: UploadFile) -> bytes:
    data = await upload.read(MAX_ORIGINAL + 1)  # enough to know it is too large
    if len(data) > MAX_ORIGINAL:
        raise ValidationFailed(
            f"Keep a file under {MAX_ORIGINAL // (1024 * 1024)} MB; split a long recording."
        )
    return data


@router.post("/api/captures", status_code=201)
async def bring_in(
    who: Who,
    ws: WS,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    """Audio (transcribed on this computer), a transcript or a document: private until the
    person pulls from it or files it."""
    data = await _read(file)
    note = ws.captures.bring_in(
        who, data=data, filename=file.filename or "", mime=file.content_type, title=title
    )
    return asdict(note)


@router.post("/api/captures/talk", status_code=201)
async def talk(who: Who, ws: WS, audio: Annotated[UploadFile, File()]) -> dict[str, Any]:
    """What the person just said, recorded in the browser: its text follows in seconds."""
    data = await _read(audio)
    note = ws.captures.bring_in(
        who, data=data, filename=audio.filename or "talk.webm", mime=audio.content_type, talk=True
    )
    return asdict(note)


@router.get("/api/captures/{capture_id}/original")
def original(capture_id: str, who: Who, ws: WS, download: bool = False) -> FileResponse:
    """What was brought in: played in place (audio), or downloaded."""
    filename, mime, path = ws.captures.original(who, capture_id)
    return served(path, media=mime, filename=filename, download=download)


@router.post("/api/captures/{capture_id}/retry")
def retry(capture_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.captures.retry(who, capture_id))


@router.get("/api/captures/status")
def statuses(who: Who, ws: WS, ids: str = "") -> dict[str, Any]:
    """Where each capture stands, from captured to searchable (Release 1 plan, M03), by id:
    `ids` is a comma-separated list."""
    wanted = [i.strip() for i in ids.split(",") if i.strip()][:200]
    return {k: asdict(v) for k, v in ws.sources.status(who, wanted).items()}


@router.post("/api/captures/{capture_id}/read-again", status_code=201)
def read_again(capture_id: str, who: Who, ws: WS) -> Task:
    """Read a capture for the Brain again after its run failed, with the same model."""
    return ws.sources.retry(who, capture_id)


@router.post("/api/captures/{capture_id}/exclude")
def exclude(capture_id: str, body: ExcludeIn, who: Who, ws: WS) -> dict[str, Any]:
    """Keep a capture out of the Brain until it is included."""
    return asdict(ws.sources.exclude(who, capture_id, reason=body.reason))


@router.post("/api/captures/{capture_id}/include")
def include(capture_id: str, who: Who, ws: WS) -> dict[str, Any]:
    return asdict(ws.sources.include(who, capture_id))


@router.post("/api/captures/{capture_id}/summarize", status_code=201)
def summarize(capture_id: str, body: SummarizeIn, who: Who, ws: WS) -> Task:
    """Ask a model for the capture's digest: its summary and key points, each marked by how
    it fits what the Brain holds now."""
    return ws.captures.summarize(who, capture_id, guidance=body.guidance)


@router.get("/api/captures/{capture_id}/related")
def related(capture_id: str, who: Who, ws: WS) -> list[dict[str, Any]]:
    """What the Brain already holds that the capture touches, found by meaning."""
    return ws.captures.related(who, capture_id)


@router.get("/api/captures/settings")
def capture_settings(who: Who, ws: WS) -> dict[str, Any]:
    return ws.captures.settings(who)


@router.put("/api/captures/settings")
def configure_captures(body: CaptureSettingsIn, who: Who, ws: WS) -> dict[str, Any]:
    """Whether what is brought in is summarized as it arrives."""
    return ws.captures.configure(who, summarize=body.summarize)


@router.get("/api/speech")
def speech_status(request: Request, who: Who) -> dict[str, Any]:
    """Whether this computer can turn speech into text: the library, the model, a download."""
    del who  # signed in is enough to see it
    status: dict[str, Any] = request.app.state.runtime.speech.status()
    return status


@router.post("/api/speech/transcribe")
def transcribe(request: Request, who: Who, audio: Annotated[UploadFile, File()]) -> dict[str, Any]:
    """What the person just said, as text, for the field they are filling in (an answer about
    what the Brain is for, say). Nothing is kept: the audio is read here, then deleted."""
    if not who.is_human:
        raise PermissionDenied("Only a person dictates.")
    speech = request.app.state.runtime.speech
    if not speech.ready():
        raise Conflict(
            "Speech to text is not set up on this computer yet: download the speech model in "
            "Settings first, or type your answer."
        )
    data = audio.file.read(MAX_DICTATION + 1)
    if len(data) > MAX_DICTATION:
        raise ValidationFailed("Keep one dictation to a few minutes.")
    if not data:
        raise ValidationFailed("Nothing was recorded.")
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
        handle.write(data)
        path = handle.name
    try:
        text, seconds = speech.transcribe(path, careful=False)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)
    return {"text": text.strip(), "seconds": round(seconds, 1)}


@router.post("/api/speech/download", status_code=202)
def speech_download(request: Request, who: Who) -> dict[str, Any]:
    """Fetch the speech model (about 480 MB, once): the owner's call, never automatic."""
    if not who.is_human:
        raise PermissionDenied("Only a person downloads the speech model.")
    status: dict[str, Any] = request.app.state.runtime.speech.start_download()
    return status
