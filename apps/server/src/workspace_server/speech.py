"""Speech to text on this computer, for what people say and record into the app (captures).

faster-whisper (CTranslate2) with an English Whisper model kept in the Brain's model folder,
beside the embedding model. The server never downloads a model on its own: the owner asks for it
(Settings, AI apps, or `workspace speech --download`), and until then spoken captures wait. No
audio leaves this computer.

A talk (a few seconds to a few minutes) is transcribed greedily, for speed; a recording with a
wider beam, since it runs in the background anyway. Measured 2026-10-06 on a 12-thread laptop
CPU with small.en (int8): greedy 6.2 times real time, beam 5 3.9 times, so an hour-long meeting
takes 10 to 15 minutes and a 15-second talk about 2 seconds.
"""

from __future__ import annotations

import gc
import glob
import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from workspace_core.workspace import Workspace

log = logging.getLogger("workspace.speech")

MODEL = "small.en"
REPO = "Systran/faster-whisper-small.en"
ABOUT_MB = 480
RATE = 16000
PAUSE = 2.0  # seconds of quiet that start a new paragraph
PARAGRAPH_WORDS = 90


def decode(path: str) -> Any:
    """The audio as 16 kHz mono float32 samples. PyAV 15 dropped an argument faster-whisper
    1.2 passes to av.open, so the app decodes it itself, the same way."""
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=RATE)
    chunks = []
    with av.open(path, mode="r") as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    del resampler
    gc.collect()  # PyAV keeps resampler buffers until collected
    samples = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def paragraphs(segments: list[tuple[float, float, str]], *, timestamps: bool) -> str:
    """Timed pieces of speech as Markdown paragraphs: a new one after a pause or a long run,
    each starting with when it was said when `timestamps`."""
    out: list[tuple[float, list[str]]] = []
    last_end: float | None = None
    for start, end, text in segments:
        words = text.strip()
        if not words:
            continue
        current = out[-1] if out else None
        if (
            current is None
            or last_end is None
            or start - last_end > PAUSE
            or len(" ".join(current[1]).split()) >= PARAGRAPH_WORDS
        ):
            out.append((start, [words]))
        else:
            current[1].append(words)
        last_end = end
    return "\n\n".join(
        (f"[{clock(start)}] " if timestamps else "") + " ".join(parts) for start, parts in out
    )


class Speech:
    def __init__(self, models_dir: str, model: str = MODEL) -> None:
        self.models_dir = os.path.abspath(models_dir)
        self.model = model
        self._model: Any = None
        self._lock = threading.Lock()
        self._downloading = False
        self._error: str | None = None

    @staticmethod
    def installed() -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def present(self) -> bool:
        repo = f"models--{REPO.replace('/', '--')}" if self.model == MODEL else ""
        pattern = os.path.join(self.models_dir, repo or "*", "snapshots", "*", "model.bin")
        return bool(glob.glob(pattern))

    def ready(self) -> bool:
        return self.installed() and self.present()

    def status(self) -> dict[str, Any]:
        return {
            "installed": self.installed(),
            "model": self.model,
            "present": self.present(),
            "ready": self.ready(),
            "downloading": self._downloading,
            "about_mb": ABOUT_MB,
            "error": self._error,
        }

    def download(self) -> dict[str, Any]:
        """Fetch the model into the model folder (an owner's request; never automatic). Uses
        the certificates the operating system trusts, as a company network's TLS inspection
        needs; verification stays on."""
        with self._lock:
            if self._downloading:
                return self.status()
            self._downloading, self._error = True, None
        try:
            try:
                import truststore

                truststore.inject_into_ssl()
            except ImportError:
                pass
            from faster_whisper.utils import download_model

            os.makedirs(self.models_dir, exist_ok=True)
            download_model(self.model, cache_dir=self.models_dir)
        except Exception as exc:  # the network, the disk: say what went wrong
            self._error = f"The speech model could not be downloaded: {exc}"
            log.warning(self._error, exc_info=True)
        finally:
            self._downloading = False
        return self.status()

    def start_download(self) -> dict[str, Any]:
        if not self._downloading:
            threading.Thread(target=self.download, name="speech-download", daemon=True).start()
            time.sleep(0.05)
        return dict(self.status(), downloading=True)

    def _load(self) -> Any:
        with self._lock:
            if self._model is None:
                from faster_whisper import WhisperModel

                self._model = WhisperModel(
                    self.model,
                    device="cpu",
                    compute_type="int8",
                    download_root=self.models_dir,
                    local_files_only=True,
                    cpu_threads=os.cpu_count() or 4,
                )
            return self._model

    def transcribe(
        self, path: str, *, careful: bool, progress: Callable[[float], None] | None = None
    ) -> tuple[str, float]:
        """(Markdown text, seconds of audio). Timestamps for a recording, not for a talk."""
        audio = decode(path)
        duration = len(audio) / RATE
        if duration < 0.3:
            return "", duration
        model = self._load()
        segments, _info = model.transcribe(
            audio,
            beam_size=5 if careful else 1,
            vad_filter=True,
            language="en" if self.model.endswith(".en") else None,
        )
        timed: list[tuple[float, float, str]] = []
        for segment in segments:
            timed.append((segment.start, segment.end, segment.text))
            if progress is not None:
                progress(min(1.0, segment.end / duration))
        return paragraphs(timed, timestamps=careful), duration


class TranscriptionWorker:
    """Turns spoken captures into text, one at a time, oldest first, while the server runs."""

    def __init__(self, ws: Workspace, speech: Speech, interval: float = 3.0) -> None:
        self.ws = ws
        self.speech = speech
        self.interval = max(0.5, float(interval))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Transcribe the oldest waiting capture. False when there was nothing to do (or no
        model to do it with)."""
        if not self.speech.ready():
            return False
        claim = self.ws.captures.claim()
        if claim is None:
            return False
        reported = [0.0, time.monotonic()]

        def progress(fraction: float) -> None:
            # A few updates, not one per sentence: each is a write.
            if fraction - reported[0] >= 0.05 and time.monotonic() - reported[1] >= 2.0:
                reported[:] = [fraction, time.monotonic()]
                self.ws.captures.progress(claim.id, fraction)

        try:
            text, duration = self.speech.transcribe(
                claim.path, careful=claim.kind == "recording", progress=progress
            )
        except Exception as exc:
            log.exception("transcription of %s failed", claim.id)
            self.ws.captures.failed(claim.id, f"The audio could not be turned into text: {exc}")
            return True
        if not text.strip():
            self.ws.captures.failed(claim.id, "Nothing was heard in it.")
            return True
        self.ws.captures.transcribed(
            claim.id, text=text, duration=duration, model=self.speech.model
        )
        log.info("transcribed %s (%.0f s of audio)", claim.id, duration)
        return True

    def start(self) -> None:
        if self._thread is not None:
            return
        waiting = self.ws.captures.requeue()
        if waiting:
            log.info("%d capture(s) left half transcribed wait again", waiting)
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="transcription", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                log.exception("transcription worker tick failed")
                worked = False
            if not worked:
                self._stop.wait(self.interval)
