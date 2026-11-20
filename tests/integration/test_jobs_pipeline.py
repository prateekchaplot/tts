"""Integration tests for the jobs manager against a real Piper voice."""

from __future__ import annotations

import json
import queue
import time
import wave
from pathlib import Path
from typing import Any

import pytest

from tts.config import Settings
from tts.history.dal import Dal
from tts.jobs.manager import JobManager
from tts.jobs.sse import SseEvent
from tts.voices.store import ensure_data_dirs, list_voices

pytestmark = pytest.mark.integration

DEFAULT_VOICE_ID = "en_US-lessac-medium"

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}

LONG_TEXT = (
    "The first sentence says hello. "
    "The second sentence says goodbye. "
    "The third sentence keeps going. "
    "The fourth sentence ends the text."
)


@pytest.fixture
def environment(tmp_path: Path) -> Any:
    """Build a manager that renders with the downloaded voice but writes to a temp dir."""
    real_settings = Settings.load()
    voices_dir = ensure_data_dirs(real_settings)
    installed = {voice.id for voice in list_voices()}
    if DEFAULT_VOICE_ID not in installed:
        pytest.skip(
            f"{DEFAULT_VOICE_ID} is not installed; run: python -m piper.download_voices "
            f"{DEFAULT_VOICE_ID} --download-dir {voices_dir}"
        )

    settings = Settings(
        host=real_settings.host,
        port=real_settings.port,
        data_dir=tmp_path,
        max_input_chars=real_settings.max_input_chars,
        history_limit=real_settings.history_limit,
        log_level=real_settings.log_level,
        default_voice_id=real_settings.default_voice_id,
    )
    dal = Dal(tmp_path)
    manager = JobManager(dal, settings)
    # The manager points the voice store at its own data directory; restore the
    # real one so the downloaded voice stays visible to the store.
    ensure_data_dirs(real_settings)

    yield manager, dal, tmp_path

    manager.close()
    dal.close()


def _wait_for_status(dal: Dal, generation_id: str, timeout: float = 60.0) -> dict[str, Any]:
    """Wait until a generation reaches a terminal status."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = dal.get(generation_id)
        if row is not None and row["status"] in TERMINAL_STATUSES:
            return row
        time.sleep(0.01)
    raise AssertionError(f"generation {generation_id} never finished")


def _wait_until_running(dal: Dal, generation_id: str, timeout: float = 60.0) -> dict[str, Any]:
    """Wait until a generation is claimed by the worker."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = dal.get(generation_id)
        if row is None:
            raise AssertionError(f"generation {generation_id} disappeared")
        if row["status"] == "running":
            return row
        if row["status"] in TERMINAL_STATUSES:
            raise AssertionError(f"generation {generation_id} finished before it was observed")
        time.sleep(0.005)
    raise AssertionError(f"generation {generation_id} never started")


def _drain(subscriber: Any, timeout: float = 60.0) -> list[SseEvent]:
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


def _audio_paths(tmp_path: Path, generation_id: str) -> tuple[Path, Path]:
    """Return the ``.part`` and final audio paths of a generation."""
    generations = tmp_path / "generations"
    return generations / f"{generation_id}.wav.part", generations / f"{generation_id}.wav"


def test_real_voice_job_reports_progress_and_succeeds(environment: Any) -> None:
    manager, dal, tmp_path = environment
    generation_id = manager.submit(DEFAULT_VOICE_ID, "Hello there. This is a test.")

    _wait_until_running(dal, generation_id)
    subscriber = manager.subscribe(generation_id)
    events = _drain(subscriber)

    progress = [event for event in events if event.name == "progress"]
    assert len(progress) >= 1
    assert progress[-1].data["sentenceIndex"] >= 1
    assert progress[-1].data["sentenceCount"] == 2
    assert events[-1].name == "succeeded"

    row = dal.get(generation_id)
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["duration_seconds"] is not None and row["duration_seconds"] > 0
    assert row["sample_rate"] == 22_050
    assert row["aligned_word_ratio"] is not None

    part_path, final_path = _audio_paths(tmp_path, generation_id)
    assert final_path.is_file()
    assert not part_path.exists()
    with wave.open(str(final_path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 22_050
        assert wav_file.getnframes() > 0


def test_real_voice_job_derives_one_cue_per_sentence(environment: Any) -> None:
    manager, dal, _ = environment
    generation_id = manager.submit(DEFAULT_VOICE_ID, "First sentence here. Second sentence here.")

    row = _wait_for_status(dal, generation_id)

    assert row["status"] == "succeeded"
    cues = json.loads(row["cues_json"])
    assert len(cues) == 2
    assert cues[0]["index"] == 1
    assert cues[1]["index"] == 2
    assert cues[0]["endMs"] <= cues[1]["startMs"]


def test_injected_engine_fault_leaves_no_audio(
    environment: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    manager, dal, tmp_path = environment
    monkeypatch.setenv("TTS_FAULT", "engine")

    generation_id = manager.submit(DEFAULT_VOICE_ID, "One sentence. Two sentences.")

    row = _wait_for_status(dal, generation_id)
    part_path, final_path = _audio_paths(tmp_path, generation_id)

    assert row["status"] == "failed"
    assert row["error_code"] == "ENGINE_ERROR"
    assert not final_path.exists()
    assert not part_path.exists()


def test_cancel_mid_run_leaves_no_audio(environment: Any) -> None:
    manager, dal, tmp_path = environment
    generation_id = manager.submit(DEFAULT_VOICE_ID, LONG_TEXT)

    _wait_until_running(dal, generation_id)
    assert manager.cancel(generation_id) == "cancelling"

    row = _wait_for_status(dal, generation_id)
    part_path, final_path = _audio_paths(tmp_path, generation_id)

    assert row["status"] == "cancelled"
    assert not final_path.exists()
    assert not part_path.exists()


def test_two_jobs_run_strictly_sequentially(environment: Any) -> None:
    manager, dal, tmp_path = environment
    first = manager.submit(DEFAULT_VOICE_ID, "First job text.")
    second = manager.submit(DEFAULT_VOICE_ID, "Second job text.")

    deadline = time.monotonic() + 60.0
    overlapped = False
    while time.monotonic() < deadline:
        first_row = dal.get(first)
        second_row = dal.get(second)
        assert first_row is not None
        assert second_row is not None
        if first_row["status"] == "running" and second_row["status"] == "running":
            overlapped = True
        if first_row["status"] in TERMINAL_STATUSES and second_row["status"] in TERMINAL_STATUSES:
            break
        time.sleep(0.005)

    assert not overlapped
    assert dal.get(first) is not None
    assert dal.get(first)["status"] == "succeeded"  # type: ignore[index]
    assert dal.get(second)["status"] == "succeeded"  # type: ignore[index]

    _, first_audio = _audio_paths(tmp_path, first)
    _, second_audio = _audio_paths(tmp_path, second)
    assert first_audio.is_file()
    assert second_audio.is_file()


def test_a_second_job_does_not_start_before_the_first_finishes(environment: Any) -> None:
    manager, dal, _ = environment
    first = manager.submit(DEFAULT_VOICE_ID, "First job text.")
    second = manager.submit(DEFAULT_VOICE_ID, "Second job text.")

    deadline = time.monotonic() + 60.0
    second_started_early = False
    while time.monotonic() < deadline:
        first_row = dal.get(first)
        second_row = dal.get(second)
        assert first_row is not None
        assert second_row is not None
        if second_row["status"] == "running" and first_row["status"] not in TERMINAL_STATUSES:
            second_started_early = True
        if first_row["status"] in TERMINAL_STATUSES and second_row["status"] in TERMINAL_STATUSES:
            break
        time.sleep(0.005)

    assert not second_started_early


def test_bootstrap_is_a_no_op_when_a_voice_is_installed(environment: Any) -> None:
    """The first-run download must not run again once a voice is present."""
    _, dal, _ = environment
    before = {voice.id for voice in list_voices()}

    from tts.jobs.manager import bootstrap

    bootstrap(Settings.load(), dal)

    assert {voice.id for voice in list_voices()} == before
