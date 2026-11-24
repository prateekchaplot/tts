"""Run one generation at a time to completion, atomically, with cancellation.

The manager owns the whole life cycle of a generation: it queues the job, runs
it on a single worker thread, writes the audio atomically, derives honest word
timings and subtitle cues, and publishes progress events (ARCHITECTURE.md
§7.8, §10.1, §10.2).

Two invariants shape the code:

* **Partial output is never success.** Audio is written to ``{id}.wav.part``
  and renamed to ``{id}.wav`` only after every derived artifact exists; the
  database row is marked ``succeeded`` only after that rename (§1, NFR-03).
* **One synthesis at a time.** A single-worker executor serializes the queue,
  so two submissions can never synthesize concurrently (§7.8, ADR-8).
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import numpy as np

from tts.config import FAULT_ENGINE, Settings
from tts.engine.piper_engine import synthesize
from tts.history.dal import Dal
from tts.jobs.sse import EventBus, SseEvent, Subscriber
from tts.subtitles.cues import build_cues
from tts.timing.reconcile import derive_word_timings
from tts.types import Cue, SentenceAudio, SynthesisResult, WordTiming
from tts.voices.store import (
    VoiceNotFoundError,
    ensure_data_dirs,
    install_voice,
    list_voices,
    load_voice,
)

if TYPE_CHECKING:
    from tts.voices.store import LoadedVoice

logger = logging.getLogger(__name__)

MAX_WAV_VALUE = 32767.0
"""Float-to-int16 scale used by piper when it writes WAV files."""

LOG_PREVIEW_CHARS = 80
"""Longest input preview that may appear in a log line (§11)."""

_TERMINATORS = ".!?…"
"""Characters that end a sentence."""

_CLOSERS = "\"'”’)]}"
"""Characters that may trail a sentence terminator."""

_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "mt",
        "ft",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "no",
        "inc",
        "ltd",
        "co",
        "fig",
        "approx",
        "a.m",
        "p.m",
        "u.s",
        "u.k",
    }
)
"""Tokens whose trailing period does not end a sentence."""


class JobError(RuntimeError):
    """Base class for errors the API layer maps to a §9.1 code."""


class GenerationNotFoundError(JobError):
    """Raised when a generation id does not exist."""


class GenerationNotCancellableError(JobError):
    """Raised when a generation already reached a terminal state."""


class EngineFaultError(RuntimeError):
    """Raised by the injected fault to simulate a mid-run engine failure."""


@dataclass
class _Job:
    """The in-memory state of one queued or running generation."""

    cancel_event: threading.Event
    sentence_index: int = 0
    sentence_count: int = 0


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Split text into sentence spans with their character offsets.

    The engine never splits text itself: the caller supplies the segmentation
    (§7.4), so the jobs manager owns it. A sentence ends at ``.``, ``!``, ``?``
    or ``…`` — optionally followed by closing punctuation — when the next
    character is whitespace or the end of the text. A period inside a decimal
    number or an abbreviation (``Dr.``, ``e.g.``) does not end a sentence.

    The spans are returned in source order and never overlap.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        if text[index] in _TERMINATORS:
            end = index + 1
            while end < length and text[end] in _TERMINATORS:
                end += 1
            while end < length and text[end] in _CLOSERS:
                end += 1
            if (end >= length or text[end].isspace()) and not _is_abbreviation(text, start, index):
                spans.append((start, end))
                while end < length and text[end].isspace():
                    end += 1
                start = end
                index = end
                continue
        index += 1
    if start < length:
        spans.append((start, length))
    return spans


def _is_abbreviation(text: str, sentence_start: int, terminator_index: int) -> bool:
    """Report whether the token before a terminator is an abbreviation."""
    words = text[sentence_start:terminator_index].split()
    if not words:
        return False
    lowered = words[-1].lower()
    if lowered in _ABBREVIATIONS:
        return True
    # A single letter before a period is an initial (``J. Smith``).
    return len(lowered) == 1 and lowered.isalpha()


def _samples_to_bytes(samples: np.ndarray) -> bytes:
    """Convert float PCM samples to 16-bit little-endian bytes.

    The scale matches piper's own WAV writer so a rendered file is identical
    to one produced by ``piper`` (ADR-5).
    """
    if samples.size == 0:
        return b""
    scaled = np.clip(samples * MAX_WAV_VALUE, -MAX_WAV_VALUE, MAX_WAV_VALUE)
    return scaled.astype(np.int16).tobytes()


def _duration_seconds(result: SynthesisResult) -> float:
    """Return the rendered duration in seconds."""
    if result.sample_rate <= 0:
        return 0.0
    return result.total_samples / result.sample_rate


def _duration_ms(result: SynthesisResult) -> int:
    """Return the rendered duration in whole milliseconds, rounded half up."""
    if result.sample_rate <= 0:
        return 0
    return math.floor(result.total_samples * 1000.0 / result.sample_rate + 0.5)


def _log_preview(text: str) -> str:
    """Return the longest input fragment that may appear in a log line (§11)."""
    return text[:LOG_PREVIEW_CHARS]


def _sentence_triplets(voice: LoadedVoice, result: SynthesisResult) -> list[tuple[int, int, int]]:
    """Return one ``(char_start, char_end, first_word_idx)`` triplet per sentence.

    ``build_cues`` needs the index at which each sentence starts in the final
    word list (§7.6). A sentence whose words cannot be reconciled collapses to
    a single unaligned entry, so the count cannot be assumed to equal the
    token count; deriving the sentence on its own yields the real number of
    entries the reconciler produced for it.
    """
    triplets: list[tuple[int, int, int]] = []
    first_word_idx = 0
    for sentence in result.sentences:
        triplets.append((sentence.char_start, sentence.char_end, first_word_idx))
        first_word_idx += _sentence_word_count(voice, sentence, result.supports_alignments)
    return triplets


def _sentence_word_count(
    voice: LoadedVoice, sentence: SentenceAudio, supports_alignments: bool
) -> int:
    """Count the word entries one sentence contributes to the final word list."""
    single = SynthesisResult(
        sentences=[sentence],
        total_samples=len(sentence.samples),
        sample_rate=sentence.sample_rate,
        supports_alignments=supports_alignments,
    )
    timings, _ = derive_word_timings(voice, single)
    return len(timings)


def _progress_event(generation_id: str, status: str, job: _Job | None) -> SseEvent:
    """Build a progress event carrying the current sentence position (§9.2)."""
    return SseEvent(
        name="progress",
        data={
            "generationId": generation_id,
            "status": status,
            "sentenceIndex": job.sentence_index if job else 0,
            "sentenceCount": job.sentence_count if job else 0,
        },
    )


def _succeeded_event(generation_id: str, duration_seconds: float | None) -> SseEvent:
    """Build the terminal event of a successful generation."""
    return SseEvent(
        name="succeeded",
        data={
            "generationId": generation_id,
            "status": "succeeded",
            "durationSeconds": duration_seconds,
        },
        terminal=True,
    )


def _failed_event(generation_id: str, code: str, message: str) -> SseEvent:
    """Build the terminal event of a failed generation."""
    return SseEvent(
        name="failed",
        data={
            "generationId": generation_id,
            "status": "failed",
            "error": {"code": code, "message": message},
        },
        terminal=True,
    )


def _cancelled_event(generation_id: str) -> SseEvent:
    """Build the terminal event of a cancelled generation."""
    return SseEvent(
        name="cancelled",
        data={"generationId": generation_id, "status": "cancelled"},
        terminal=True,
    )


def _remove_file(path: Path) -> None:
    """Delete a file, tolerating one that is already gone."""
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning("Could not remove %s", path)


class JobManager:
    """Runs one generation at a time to completion, atomically."""

    def __init__(self, dal: Dal, settings: Settings) -> None:
        self._dal = dal
        self._settings = settings
        self._lock = threading.RLock()
        self._bus = EventBus()
        self._jobs: dict[str, _Job] = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-jobs")
        self._generations_dir = settings.data_dir / "generations"
        self._generations_dir.mkdir(parents=True, exist_ok=True)
        ensure_data_dirs(settings)

    # -- public interface ----------------------------------------------------

    def submit(
        self,
        voice_id: str,
        text: str,
        source_type: str = "text",
        input_filename: str | None = None,
        rate: float = 1.0,
        volume: float = 1.0,
    ) -> str:
        """Queue a generation and return its id.

        The row is created as ``queued`` before the job reaches the worker, so
        a client that receives the id can always read the generation back.
        """
        voice_name = self._voice_name(voice_id)
        generation_id = self._dal.create_generation(
            text=text,
            voice_id=voice_id,
            voice_name=voice_name,
            source_type=source_type,
            input_filename=input_filename,
            rate=rate,
            volume=volume,
        )
        job = _Job(cancel_event=threading.Event())
        with self._lock:
            self._jobs[generation_id] = job
            # §8.5: every in-flight id is protected from eviction, not just
            # the one that was just inserted.
            self._dal.evict_to_limit(set(self._jobs))
            self._executor.submit(self._run_job, generation_id, job)
        return generation_id

    def cancel(self, generation_id: str) -> Literal["cancelled", "cancelling"]:
        """Request cancellation and report the resulting state.

        A job that never started is cancelled outright; a running job is asked
        to stop and reports ``cancelling`` until the worker confirms it. A
        generation that already reached a terminal state cannot be cancelled
        and raises :class:`GenerationNotCancellableError`.
        """
        with self._lock:
            row = self._dal.get(generation_id)
            if row is None:
                raise GenerationNotFoundError(generation_id)
            status = row["status"]
            job = self._jobs.get(generation_id)

            if status == "queued":
                if job is not None:
                    job.cancel_event.set()
                self._dal.set_status(generation_id, "cancelled")
                self._jobs.pop(generation_id, None)
                self._bus.publish(generation_id, _cancelled_event(generation_id))
                self._bus.close(generation_id)
                return "cancelled"

            if status == "running":
                if job is not None:
                    job.cancel_event.set()
                self._dal.set_status(generation_id, "cancelling")
                self._bus.publish(generation_id, _progress_event(generation_id, "cancelling", job))
                return "cancelling"

            if status == "cancelling":
                return "cancelling"

            raise GenerationNotCancellableError(generation_id)

    def subscribe(self, generation_id: str) -> Subscriber:
        """Register an SSE subscriber and replay the current state.

        Replaying the state makes a reconnect stateless-safe: the client sees
        where the generation stands without replaying its whole history
        (§9.2).
        """
        with self._lock:
            row = self._dal.get(generation_id)
            if row is None:
                raise GenerationNotFoundError(generation_id)
            subscriber = self._bus.subscribe(generation_id)
            self._replay_state(generation_id, subscriber, row)
            return subscriber

    def close(self) -> None:
        """Stop the worker and close every event stream."""
        self._executor.shutdown(wait=True)
        with self._lock:
            self._jobs.clear()
            self._bus.close_all()

    # -- worker ---------------------------------------------------------------

    def _run_job(self, generation_id: str, job: _Job) -> None:
        """Claim a queued job and run it, or skip it when it was cancelled."""
        with self._lock:
            row = self._dal.get(generation_id)
            if row is None or row["status"] != "queued":
                return
            self._dal.set_status(generation_id, "running")
            self._bus.publish(generation_id, _progress_event(generation_id, "running", job))
        try:
            self._execute(generation_id, job, row)
        except Exception:
            logger.exception("Generation %s crashed outside its failure handler", generation_id)

    def _execute(self, generation_id: str, job: _Job, row: dict[str, Any]) -> None:
        """Synthesize one generation and publish its outcome."""
        text = str(row["input_text"])
        voice_id = str(row["voice_id"])
        part_path = self._generations_dir / f"{generation_id}.wav.part"
        final_path = self._generations_dir / f"{generation_id}.wav"
        voice: LoadedVoice | None = None

        try:
            voice = load_voice(voice_id)
            segments = split_sentences(text)
            job.sentence_count = len(segments)
            sample_rate = int(voice.voice.config.sample_rate)
            logger.info(
                "Generation %s started for voice %s (%d characters, %d sentences)",
                generation_id,
                voice_id,
                len(text),
                job.sentence_count,
            )

            with wave.open(str(part_path), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                result = synthesize(
                    voice,
                    text,
                    segments,
                    rate=float(row["rate"]),
                    volume=float(row["volume"]),
                    cancel_event=job.cancel_event,
                    on_sentence=self._on_sentence(generation_id, job, wav_file),
                )

            if job.cancel_event.is_set():
                self._finish_cancelled(generation_id, job, part_path)
                return

            if result.total_samples <= 0:
                # A generation with no audio is not a success: the file would
                # be a valid but empty WAV that no player can use.
                logger.warning(
                    "Generation %s produced no audio for %d characters", generation_id, len(text)
                )
                self._finish_failed(
                    generation_id,
                    job,
                    part_path,
                    "ENGINE_ERROR",
                    "The speech engine produced no audio for this text.",
                    "synthesis produced no samples",
                )
                return

            words, ratio = derive_word_timings(voice, result)
            triplets = _sentence_triplets(voice, result)
            cues = build_cues(words, triplets, _duration_ms(result))
            self._finish_succeeded(
                generation_id, job, result, words, cues, ratio, part_path, final_path
            )
        except EngineFaultError as error:
            logger.exception(
                "Generation %s failed for voice %s (%d characters, preview %r)",
                generation_id,
                voice_id,
                len(text),
                _log_preview(text),
            )
            self._finish_failed(
                generation_id,
                job,
                part_path,
                "ENGINE_ERROR",
                "The speech engine could not render this text.",
                str(error),
            )
        except Exception as error:
            logger.exception(
                "Generation %s failed for voice %s (%d characters, preview %r)",
                generation_id,
                voice_id,
                len(text),
                _log_preview(text),
            )
            self._finish_failed(
                generation_id,
                job,
                part_path,
                "INTERNAL_ERROR",
                "The generation failed unexpectedly.",
                str(error),
            )

    def _on_sentence(
        self, generation_id: str, job: _Job, wav_file: wave.Wave_write
    ) -> Callable[[SentenceAudio], None]:
        """Build the callback that streams one sentence and reports progress."""

        def on_sentence(sentence: SentenceAudio) -> None:
            if job.cancel_event.is_set():
                return
            wav_file.writeframes(_samples_to_bytes(sentence.samples))
            with self._lock:
                job.sentence_index += 1
                self._bus.publish(generation_id, _progress_event(generation_id, "running", job))
            if self._settings.fault == FAULT_ENGINE and job.sentence_index == 1:
                raise EngineFaultError("injected engine failure")

        return on_sentence

    # -- terminal transitions -------------------------------------------------

    def _finish_succeeded(
        self,
        generation_id: str,
        job: _Job,
        result: SynthesisResult,
        words: list[WordTiming],
        cues: list[Cue],
        ratio: float,
        part_path: Path,
        final_path: Path,
    ) -> None:
        """Rename the audio, store the results, and publish the outcome."""
        with self._lock:
            if job.cancel_event.is_set():
                self._cancel_locked(generation_id, job, part_path)
                return
            os.replace(part_path, final_path)
            duration_seconds = _duration_seconds(result)
            self._dal.set_status(
                generation_id,
                "succeeded",
                duration_seconds=duration_seconds,
                sample_rate=result.sample_rate,
                audio_path=str(final_path),
                word_timings_json=json.dumps(
                    [
                        {
                            "text": word.text,
                            "startMs": word.start_ms,
                            "endMs": word.end_ms,
                            "aligned": word.aligned,
                        }
                        for word in words
                    ]
                ),
                cues_json=json.dumps(
                    [
                        {
                            "index": cue.index,
                            "startMs": cue.start_ms,
                            "endMs": cue.end_ms,
                            "text": cue.text,
                        }
                        for cue in cues
                    ]
                ),
                aligned_word_ratio=ratio if ratio >= 0 else None,
            )
            self._jobs.pop(generation_id, None)
            if ratio < 0:
                logger.warning("Generation %s finished without word alignments", generation_id)
            else:
                logger.info(
                    "Generation %s succeeded in %.2fs (aligned ratio %.3f)",
                    generation_id,
                    duration_seconds,
                    ratio,
                )
            self._bus.publish(generation_id, _succeeded_event(generation_id, duration_seconds))
            self._bus.close(generation_id)

    def _finish_cancelled(self, generation_id: str, job: _Job, part_path: Path) -> None:
        """Discard the partial output and mark the generation cancelled."""
        with self._lock:
            self._cancel_locked(generation_id, job, part_path)

    def _cancel_locked(self, generation_id: str, job: _Job, part_path: Path) -> None:
        """Cancel a generation; the caller already holds the manager lock."""
        _remove_file(part_path)
        self._dal.set_status(generation_id, "cancelled")
        self._jobs.pop(generation_id, None)
        logger.info("Generation %s cancelled", generation_id)
        self._bus.publish(generation_id, _cancelled_event(generation_id))
        self._bus.close(generation_id)

    def _finish_failed(
        self,
        generation_id: str,
        job: _Job,
        part_path: Path,
        code: str,
        message: str,
        reason: str,
    ) -> None:
        """Discard the partial output and mark the generation failed."""
        with self._lock:
            _remove_file(part_path)
            self._dal.set_status(generation_id, "failed", error={"code": code, "message": message})
            self._jobs.pop(generation_id, None)
            logger.warning("Generation %s failed (%s): %s", generation_id, code, reason)
            self._bus.publish(generation_id, _failed_event(generation_id, code, message))
            self._bus.close(generation_id)

    # -- helpers --------------------------------------------------------------

    def _voice_name(self, voice_id: str) -> str:
        """Resolve the display name of a voice, refusing an unknown one."""
        for voice in list_voices():
            if voice.id == voice_id:
                return voice.name
        raise VoiceNotFoundError(voice_id)

    def _replay_state(
        self, generation_id: str, subscriber: Subscriber, row: dict[str, Any]
    ) -> None:
        """Send the current state of a generation to a fresh subscriber."""
        status = row["status"]
        job = self._jobs.get(generation_id)
        if status == "succeeded":
            subscriber.put(_succeeded_event(generation_id, row["duration_seconds"]))
            self._bus.close(generation_id)
        elif status == "failed":
            subscriber.put(
                _failed_event(
                    generation_id,
                    str(row["error_code"] or "INTERNAL_ERROR"),
                    str(row["error_message"] or "The generation failed unexpectedly."),
                )
            )
            self._bus.close(generation_id)
        elif status == "cancelled":
            subscriber.put(_cancelled_event(generation_id))
            self._bus.close(generation_id)
        else:
            subscriber.put(_progress_event(generation_id, status, job))


def bootstrap(settings: Settings, dal: Dal) -> None:
    """Install the default voice on first run, tolerating an offline machine.

    A failure to download is not fatal: the application keeps serving and the
    UI shows the no-voice guidance with the exact remedy (§10.4, R7). The
    settings seeding that §8.2 asks for belongs to the settings route, so the
    DAL is accepted here only to keep the startup hook in one place.
    """
    ensure_data_dirs(settings)
    if list_voices():
        return
    logger.info(
        "Downloading default voice %s (one-time, requires internet)", settings.default_voice_id
    )
    try:
        install_voice(settings.default_voice_id)
    except Exception as error:  # noqa: BLE001 - an offline first run must not crash
        logger.warning(
            "Could not download the default voice %s: %s", settings.default_voice_id, error
        )
        logger.warning(
            "No voices are installed. Run `tts add-voice %s` (needs internet once), then reload.",
            settings.default_voice_id,
        )
        return
    logger.info("Installed default voice %s", settings.default_voice_id)
