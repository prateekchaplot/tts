"""Unit tests for the jobs manager using a fake engine and a real DAL."""

from __future__ import annotations

import itertools
import json
import queue
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tts.config import Settings
from tts.history.dal import Dal
from tts.jobs import manager as manager_module
from tts.jobs.manager import (
    EngineFaultError,
    GenerationNotCancellableError,
    GenerationNotFoundError,
    JobManager,
    split_sentences,
)
from tts.jobs.sse import SseEvent
from tts.types import Cue, SentenceAudio, SynthesisResult, WordTiming
from tts.voices.store import LoadedVoice

SAMPLE_RATE = 22_050
VOICE_ID = "test-voice"
SENTENCE_MS = 100


class FakeEngine:
    """Stands in for the piper engine: deterministic sentences, optional faults."""

    def __init__(
        self,
        *,
        gate: threading.Event | None = None,
        fail_after: int | None = None,
        silent: bool = False,
    ) -> None:
        self.gate = gate
        self.fail_after = fail_after
        self.silent = silent
        self.started = threading.Event()
        self.calls: list[str] = []
        self.concurrent = 0
        self.max_concurrent = 0

    def synthesize(
        self,
        voice: LoadedVoice,
        text: str,
        char_offset_map: list[tuple[int, int]],
        rate: float,
        volume: float,
        cancel_event: threading.Event,
        on_sentence: Any,
    ) -> SynthesisResult:
        self.started.set()
        self.calls.append(text)
        self.concurrent += 1
        self.max_concurrent = max(self.max_concurrent, self.concurrent)
        try:
            if self.gate is not None:
                self.gate.wait(timeout=10)
            sentences: list[SentenceAudio] = []
            for index, (start, end) in enumerate(char_offset_map):
                if cancel_event.is_set():
                    break
                if self.fail_after is not None and index >= self.fail_after:
                    raise RuntimeError("engine exploded")
                sentence = _sentence(text, start, end, silent=self.silent)
                sentences.append(sentence)
                on_sentence(sentence)
            return SynthesisResult(
                sentences=sentences,
                total_samples=sum(len(item.samples) for item in sentences),
                sample_rate=SAMPLE_RATE,
                supports_alignments=True,
            )
        finally:
            self.concurrent -= 1


def _sentence(text: str, start: int, end: int, *, silent: bool = False) -> SentenceAudio:
    """Build one deterministic sentence of silent audio."""
    sample_count = 0 if silent else SAMPLE_RATE * SENTENCE_MS // 1000
    samples = np.zeros(sample_count, dtype=np.float32)
    return SentenceAudio(
        text=text[start:end],
        char_start=start,
        char_end=end,
        samples=samples,
        sample_rate=SAMPLE_RATE,
        phoneme_alignments=[("h", len(samples))],
        supports_alignments=True,
    )


def _fake_timings(voice: LoadedVoice, result: SynthesisResult) -> tuple[list[WordTiming], float]:
    """Derive one word timing per whitespace token, ignoring the collapse rule."""
    words: list[WordTiming] = []
    for sentence in result.sentences:
        for token in sentence.text.split():
            words.append(WordTiming(text=token, start_ms=0, end_ms=SENTENCE_MS, aligned=True))
    return words, 1.0


def _install_fake_voice(data_dir: Path) -> None:
    """Write a minimal voice pair so the real voice store can list it."""
    voices_dir = data_dir / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    (voices_dir / f"{VOICE_ID}.onnx").write_bytes(b"")
    (voices_dir / f"{VOICE_ID}.onnx.json").write_text(
        json.dumps({"audio": {"sample_rate": SAMPLE_RATE}, "language": {"code": "en_US"}}),
        encoding="utf-8",
    )


class Harness:
    """A manager wired to fakes, plus the DAL and the fake engine behind it."""

    def __init__(self, manager: JobManager, dal: Dal, engine: FakeEngine) -> None:
        self.manager = manager
        self.dal = dal
        self.engine = engine


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    """Build a manager with a fake engine and an installed fake voice."""
    _install_fake_voice(tmp_path)
    settings = Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id=VOICE_ID,
    )
    dal = Dal(tmp_path)
    manager = JobManager(dal, settings)

    fake_voice = LoadedVoice(
        voice=SimpleNamespace(config=SimpleNamespace(sample_rate=SAMPLE_RATE)),  # type: ignore[arg-type]
        supports_alignments=True,
    )
    engine = FakeEngine()
    monkeypatch.setattr(manager_module, "load_voice", lambda voice_id: fake_voice)
    monkeypatch.setattr(manager_module, "synthesize", engine.synthesize)
    monkeypatch.setattr(manager_module, "derive_word_timings", _fake_timings)

    harness = Harness(manager, dal, engine)
    yield harness
    manager.close()
    dal.close()


def _wait_for_status(
    dal: Dal, generation_id: str, statuses: set[str], timeout: float = 10.0
) -> dict[str, Any]:
    """Wait until a generation reaches one of the given statuses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = dal.get(generation_id)
        if row is not None and row["status"] in statuses:
            return row
        time.sleep(0.005)
    raise AssertionError(f"generation {generation_id} never reached {sorted(statuses)}")


def _drain(subscriber: Any, timeout: float = 10.0) -> list[SseEvent]:
    """Collect every event a subscriber receives until its stream closes."""
    events: list[SseEvent] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            event = subscriber.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            break
        if event is None:
            break
        events.append(event)
    return events


def _generation_files(harness: Harness, generation_id: str) -> tuple[Path, Path]:
    """Return the ``.part`` and final audio paths of a generation."""
    generations = harness.manager._generations_dir
    return (
        generations / f"{generation_id}.wav.part",
        generations / f"{generation_id}.wav",
    )


# -- submission ---------------------------------------------------------------


def test_submit_creates_a_row_and_reaches_succeeded(harness: Harness) -> None:
    generation_id = harness.manager.submit(VOICE_ID, "Hello there. Second one.")

    row = _wait_for_status(harness.dal, generation_id, {"succeeded"})

    assert row["status"] == "succeeded"
    assert row["voice_id"] == VOICE_ID
    assert row["voice_name"] == VOICE_ID
    assert row["input_text"] == "Hello there. Second one."
    assert row["source_type"] == "text"
    assert row["sample_rate"] == SAMPLE_RATE
    assert row["duration_seconds"] == pytest.approx(0.2)
    assert row["aligned_word_ratio"] == pytest.approx(1.0)


def test_submit_rejects_an_unknown_voice(harness: Harness) -> None:
    from tts.voices.store import VoiceNotFoundError

    with pytest.raises(VoiceNotFoundError):
        harness.manager.submit("missing-voice", "Hello.")


def test_successful_job_writes_audio_atomically(harness: Harness) -> None:
    generation_id = harness.manager.submit(VOICE_ID, "One. Two.")
    _wait_for_status(harness.dal, generation_id, {"succeeded"})

    part_path, final_path = _generation_files(harness, generation_id)

    assert final_path.is_file()
    assert not part_path.exists()

    with wave.open(str(final_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == SAMPLE_RATE
        assert wav_file.getnframes() == SAMPLE_RATE * 2 * SENTENCE_MS // 1000


def test_successful_job_stores_timings_and_cues(harness: Harness) -> None:
    generation_id = harness.manager.submit(VOICE_ID, "Hello there. Second one.")
    _wait_for_status(harness.dal, generation_id, {"succeeded"})

    row = harness.dal.get(generation_id)
    assert row is not None

    word_timings = json.loads(row["word_timings_json"])
    assert word_timings == [
        {"text": "Hello", "startMs": 0, "endMs": 100, "aligned": True},
        {"text": "there.", "startMs": 0, "endMs": 100, "aligned": True},
        {"text": "Second", "startMs": 0, "endMs": 100, "aligned": True},
        {"text": "one.", "startMs": 0, "endMs": 100, "aligned": True},
    ]

    cues = json.loads(row["cues_json"])
    assert [cue["index"] for cue in cues] == [1, 2]
    assert cues[0]["text"] == "Hello there."
    assert cues[0]["startMs"] == 0
    assert set(cues[0]) == {"index", "startMs", "endMs", "text"}

    assert row["audio_path"] == str(_generation_files(harness, generation_id)[1])


# -- events -------------------------------------------------------------------


def test_progress_events_are_published_before_success(harness: Harness) -> None:
    gate = threading.Event()
    harness.engine.gate = gate
    generation_id = harness.manager.submit(VOICE_ID, "One. Two.")
    assert harness.engine.started.wait(timeout=10)

    subscriber = harness.manager.subscribe(generation_id)
    gate.set()
    events = _drain(subscriber)

    progress = [event for event in events if event.name == "progress"]
    assert len(progress) >= 1
    assert progress[-1].data["sentenceIndex"] == 2
    assert progress[-1].data["sentenceCount"] == 2
    assert progress[-1].data["status"] == "running"
    assert events[-1].name == "succeeded"
    assert events[-1].data["durationSeconds"] == pytest.approx(0.2)


def test_subscribe_replays_the_terminal_state(harness: Harness) -> None:
    generation_id = harness.manager.submit(VOICE_ID, "One.")
    _wait_for_status(harness.dal, generation_id, {"succeeded"})

    subscriber = harness.manager.subscribe(generation_id)
    events = _drain(subscriber)

    assert [event.name for event in events] == ["succeeded"]
    assert events[0].data["status"] == "succeeded"


def test_subscribe_replays_a_running_state(harness: Harness) -> None:
    gate = threading.Event()
    harness.engine.gate = gate
    generation_id = harness.manager.submit(VOICE_ID, "One.")
    assert harness.engine.started.wait(timeout=10)

    subscriber = harness.manager.subscribe(generation_id)
    gate.set()
    events = _drain(subscriber)

    assert events[0].name == "progress"
    assert events[0].data["status"] == "running"


def test_subscribe_rejects_an_unknown_generation(harness: Harness) -> None:
    with pytest.raises(GenerationNotFoundError):
        harness.manager.subscribe("6f0c8e2a-0000-4000-8000-000000000000")


# -- failures -----------------------------------------------------------------


def test_engine_failure_leaves_no_audio_and_marks_failed(harness: Harness) -> None:
    harness.engine.fail_after = 1
    generation_id = harness.manager.submit(VOICE_ID, "One. Two. Three.")

    row = _wait_for_status(harness.dal, generation_id, {"failed"})
    part_path, final_path = _generation_files(harness, generation_id)

    assert row["status"] == "failed"
    assert row["error_code"] == "INTERNAL_ERROR"
    assert row["error_message"]
    assert not final_path.exists()
    assert not part_path.exists()


def test_a_generation_without_audio_fails_instead_of_succeeding(harness: Harness) -> None:
    """A valid but empty WAV would be unplayable, so it must not be a success."""
    harness.engine.silent = True
    generation_id = harness.manager.submit(VOICE_ID, "---")

    row = _wait_for_status(harness.dal, generation_id, {"failed"})
    part_path, final_path = _generation_files(harness, generation_id)

    assert row["error_code"] == "ENGINE_ERROR"
    assert not final_path.exists()
    assert not part_path.exists()


def test_injected_fault_marks_the_job_failed_with_engine_error(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(manager_module.FAULT_ENV_VAR, manager_module.FAULT_ENGINE)
    generation_id = harness.manager.submit(VOICE_ID, "One. Two.")

    row = _wait_for_status(harness.dal, generation_id, {"failed"})
    part_path, final_path = _generation_files(harness, generation_id)

    assert row["error_code"] == "ENGINE_ERROR"
    assert not final_path.exists()
    assert not part_path.exists()


def test_a_cancelled_job_is_not_turned_into_a_failure(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(manager_module.FAULT_ENV_VAR, manager_module.FAULT_ENGINE)
    gate = threading.Event()
    harness.engine.gate = gate
    generation_id = harness.manager.submit(VOICE_ID, "One. Two.")
    assert harness.engine.started.wait(timeout=10)

    assert harness.manager.cancel(generation_id) == "cancelling"
    gate.set()
    row = _wait_for_status(harness.dal, generation_id, {"cancelled"})

    assert row["status"] == "cancelled"
    assert row["error_code"] is None


# -- cancellation -------------------------------------------------------------


def test_cancel_mid_run_cancels_the_job_and_removes_the_output(harness: Harness) -> None:
    gate = threading.Event()
    harness.engine.gate = gate
    generation_id = harness.manager.submit(VOICE_ID, "One. Two.")
    assert harness.engine.started.wait(timeout=10)

    assert harness.manager.cancel(generation_id) == "cancelling"
    gate.set()
    row = _wait_for_status(harness.dal, generation_id, {"cancelled"})
    part_path, final_path = _generation_files(harness, generation_id)

    assert row["status"] == "cancelled"
    assert not final_path.exists()
    assert not part_path.exists()


def test_cancel_while_queued_never_starts_the_job(harness: Harness) -> None:
    gate = threading.Event()
    harness.engine.gate = gate
    first = harness.manager.submit(VOICE_ID, "Blocking.")
    assert harness.engine.started.wait(timeout=10)

    second = harness.manager.submit(VOICE_ID, "Second job.")
    assert harness.manager.cancel(second) == "cancelled"

    row = _wait_for_status(harness.dal, second, {"cancelled"})
    assert row["status"] == "cancelled"

    gate.set()
    _wait_for_status(harness.dal, first, {"succeeded"})
    assert harness.engine.calls == ["Blocking."]


def test_cancel_rejects_an_unknown_generation(harness: Harness) -> None:
    with pytest.raises(GenerationNotFoundError):
        harness.manager.cancel("6f0c8e2a-0000-4000-8000-000000000000")


def test_cancel_rejects_a_terminal_generation(harness: Harness) -> None:
    generation_id = harness.manager.submit(VOICE_ID, "One.")
    _wait_for_status(harness.dal, generation_id, {"succeeded"})

    with pytest.raises(GenerationNotCancellableError):
        harness.manager.cancel(generation_id)


# -- serialization ------------------------------------------------------------


def test_two_jobs_run_strictly_sequentially(harness: Harness) -> None:
    first = harness.manager.submit(VOICE_ID, "One.")
    second = harness.manager.submit(VOICE_ID, "Two.")

    _wait_for_status(harness.dal, first, {"succeeded"})
    _wait_for_status(harness.dal, second, {"succeeded"})

    assert harness.engine.max_concurrent == 1
    assert harness.engine.calls == ["One.", "Two."]


def test_eviction_is_given_every_in_flight_id(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[set[str]] = []
    original = harness.dal.evict_to_limit

    def spy(active_ids: set[str] | None = None) -> list[str]:
        captured.append(set(active_ids or set()))
        return original(active_ids)

    monkeypatch.setattr(harness.dal, "evict_to_limit", spy)

    gate = threading.Event()
    harness.engine.gate = gate
    first = harness.manager.submit(VOICE_ID, "One.")
    assert harness.engine.started.wait(timeout=10)
    second = harness.manager.submit(VOICE_ID, "Two.")

    assert captured[-1] == {first, second}

    gate.set()
    _wait_for_status(harness.dal, first, {"succeeded"})
    _wait_for_status(harness.dal, second, {"succeeded"})


# -- sentence segmentation ----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hello. World.", [(0, 6), (7, 13)]),
        ("Hello world", [(0, 11)]),
        ("Hello.", [(0, 6)]),
        ("Wait! What? Yes.", [(0, 5), (6, 11), (12, 16)]),
        ('He said "stop." Then left.', [(0, 15), (16, 26)]),
        ("Dr. Smith went home.", [(0, 20)]),
        ("J. Smith went home.", [(0, 19)]),
        ("The price is 3.14 today.", [(0, 24)]),
        ("One.   Two.", [(0, 4), (7, 11)]),
    ],
)
def test_split_sentences(text: str, expected: list[tuple[int, int]]) -> None:
    assert split_sentences(text) == expected


def test_split_sentences_covers_the_text_without_overlap() -> None:
    text = "First one. Second one! Third one? Done"
    spans = split_sentences(text)

    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)
    for previous, current in itertools.pairwise(spans):
        assert previous[1] <= current[0]
        assert previous[1] < current[1]


# -- cue sentence triplets ----------------------------------------------------


def test_sentence_triplets_use_the_real_per_sentence_entry_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A collapsed sentence contributes one entry, not one entry per token."""
    sentences = [
        _sentence("Hello there.", 0, 12),
        _sentence("Goodbye.", 13, 21),
    ]
    result = SynthesisResult(
        sentences=sentences,
        total_samples=sum(len(item.samples) for item in sentences),
        sample_rate=SAMPLE_RATE,
        supports_alignments=True,
    )

    def collapsing_timings(
        voice: LoadedVoice, synthesis: SynthesisResult
    ) -> tuple[list[WordTiming], float]:
        if len(synthesis.sentences) == 1:
            # The reconciler collapses an unplaceable sentence to one entry.
            return [
                WordTiming(text=synthesis.sentences[0].text, start_ms=0, end_ms=1, aligned=False)
            ], 0.0
        return _fake_timings(voice, synthesis)

    monkeypatch.setattr(manager_module, "derive_word_timings", collapsing_timings)
    fake_voice = LoadedVoice(
        voice=SimpleNamespace(config=SimpleNamespace(sample_rate=SAMPLE_RATE)),  # type: ignore[arg-type]
        supports_alignments=True,
    )

    triplets = manager_module._sentence_triplets(fake_voice, result)

    assert triplets == [(0, 12, 0), (13, 21, 1)]


def test_engine_fault_error_is_an_exception() -> None:
    assert issubclass(EngineFaultError, RuntimeError)
    assert isinstance(Cue(index=1, start_ms=0, end_ms=1, text="x"), Cue)
