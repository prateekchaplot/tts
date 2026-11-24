"""Tests for the section 11 logging rules and the never-log enforcement."""

from __future__ import annotations

import json
import logging
import time
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tts.config import FAULT_ENGINE, FAULT_NONE, Settings
from tts.history.dal import Dal
from tts.jobs import manager as manager_module
from tts.jobs.manager import LOG_PREVIEW_CHARS, JobManager
from tts.types import SentenceAudio, SynthesisResult, WordTiming
from tts.voices.store import LoadedVoice

VOICE_ID = "test-voice"
SAMPLE_RATE = 22_050
SENTENCE_SAMPLES = SAMPLE_RATE // 10
SENTENCE_MS = 100

SECRET_TAIL = "SECRET-TAIL-MARKER-9f3c"
LONG_INPUT = "Hello world. " * 10 + SECRET_TAIL


class RecordingEngine:
    """Emits one sentence so the manager's per-sentence hooks run."""

    def synthesize(
        self,
        voice: LoadedVoice,
        text: str,
        char_offset_map: list[tuple[int, int]],
        rate: float,
        volume: float,
        cancel_event: Any,
        on_sentence: Any,
    ) -> SynthesisResult:
        sentence = SentenceAudio(
            text=text,
            char_start=0,
            char_end=len(text),
            samples=np.zeros(SENTENCE_SAMPLES, dtype=np.float32),
            sample_rate=SAMPLE_RATE,
            phoneme_alignments=[("h", SENTENCE_SAMPLES)],
            supports_alignments=True,
        )
        on_sentence(sentence)
        return SynthesisResult(
            sentences=[sentence],
            total_samples=SENTENCE_SAMPLES,
            sample_rate=SAMPLE_RATE,
            supports_alignments=True,
        )


def _one_word_timing(voice: LoadedVoice, result: SynthesisResult) -> tuple[list[WordTiming], float]:
    """Return a single aligned word so a successful generation can finish."""
    word = WordTiming(text="word", start_ms=0, end_ms=SENTENCE_MS, aligned=True)
    return [word], 1.0


def _build_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fault: str
) -> tuple[JobManager, Dal]:
    """Wire a manager to a fake voice and engine, using the given fault mode."""
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    (voices_dir / f"{VOICE_ID}.onnx").write_bytes(b"")
    (voices_dir / f"{VOICE_ID}.onnx.json").write_text(
        json.dumps({"audio": {"sample_rate": SAMPLE_RATE}, "language": {"code": "en_US"}}),
        encoding="utf-8",
    )

    settings = Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id=VOICE_ID,
        fault=fault,
    )
    dal = Dal(tmp_path)
    manager = JobManager(dal, settings)

    fake_voice = LoadedVoice(
        voice=SimpleNamespace(config=SimpleNamespace(sample_rate=SAMPLE_RATE)),  # type: ignore[arg-type]
        supports_alignments=True,
    )
    engine = RecordingEngine()
    monkeypatch.setattr(manager_module, "load_voice", lambda voice_id: fake_voice)
    monkeypatch.setattr(manager_module, "synthesize", engine.synthesize)
    monkeypatch.setattr(manager_module, "derive_word_timings", _one_word_timing)
    return manager, dal


def _wait_for_status(
    dal: Dal, generation_id: str, statuses: set[str], timeout: float = 10.0
) -> dict[str, Any]:
    """Wait until a generation reaches one of the given statuses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = dal.get(generation_id)
        if row is not None and row["status"] in statuses:
            return row
        time.sleep(0.01)
    raise AssertionError(f"generation {generation_id} never reached {statuses}")


def _clear_fault_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point settings at a temp data dir and remove any inherited fault mode."""
    monkeypatch.setenv("TTS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("TTS_FAULT", raising=False)


def test_settings_default_to_no_fault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _clear_fault_environment(monkeypatch, tmp_path)

    assert Settings.load().fault == FAULT_NONE


def test_settings_read_fault_mode_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_fault_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("TTS_FAULT", " Engine ")

    with caplog.at_level(logging.WARNING, logger="tts.config"):
        settings = Settings.load()

    assert settings.fault == FAULT_ENGINE
    assert "Fault injection enabled: engine" in caplog.text


def test_unknown_fault_mode_warns_and_disables_injection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_fault_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("TTS_FAULT", "explode")

    with caplog.at_level(logging.WARNING, logger="tts.config"):
        settings = Settings.load()

    assert settings.fault == FAULT_NONE
    assert "Unknown TTS_FAULT 'explode'" in caplog.text
    assert "Fault injection enabled" not in caplog.text


def test_failed_generation_logs_reason_but_not_the_input_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """§11: log the failure reason, never log input beyond an 80-char preview."""
    manager, dal = _build_manager(tmp_path, monkeypatch, fault=FAULT_ENGINE)
    try:
        with caplog.at_level(logging.DEBUG, logger="tts"):
            generation_id = manager.submit(VOICE_ID, LONG_INPUT)
            row = _wait_for_status(dal, generation_id, {"failed"})

        assert row["error_code"] == "ENGINE_ERROR"
        assert "ENGINE_ERROR" in caplog.text
        assert "injected engine failure" in caplog.text
        assert repr(LONG_INPUT[:LOG_PREVIEW_CHARS]) in caplog.text
        assert any(record.exc_info for record in caplog.records)

        assert LONG_INPUT not in caplog.text
        assert SECRET_TAIL not in caplog.text
        match = SequenceMatcher(None, LONG_INPUT, caplog.text, autojunk=False).find_longest_match(
            0, len(LONG_INPUT), 0, len(caplog.text)
        )
        assert match.size <= LOG_PREVIEW_CHARS
        assert "wordTimings" not in caplog.text
        assert "startMs" not in caplog.text
    finally:
        manager.close()
        dal.close()


def test_the_manager_does_not_read_the_fault_environment_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7.1: only config reads the environment, so a Settings without fault succeeds."""
    monkeypatch.setenv("TTS_FAULT", FAULT_ENGINE)
    manager, dal = _build_manager(tmp_path, monkeypatch, fault=FAULT_NONE)
    try:
        generation_id = manager.submit(VOICE_ID, "One. Two.")

        row = _wait_for_status(dal, generation_id, {"succeeded", "failed"})

        assert row["status"] == "succeeded", row
    finally:
        manager.close()
        dal.close()
