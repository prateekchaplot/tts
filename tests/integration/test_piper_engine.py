"""Integration tests for the Piper engine against a real voice."""

from __future__ import annotations

import statistics
import threading

import numpy as np
import pytest

from tts.config import Settings
from tts.engine.piper_engine import synthesize
from tts.types import SentenceAudio, SynthesisResult
from tts.voices.store import LoadedVoice, ensure_data_dirs, list_voices, load_voice

pytestmark = pytest.mark.integration

DEFAULT_VOICE_ID = "en_US-lessac-medium"
TEXT = "Hello there. How are you today? This is a test."
SENTENCES = ["Hello there.", "How are you today?", "This is a test."]


def _segments(text: str, sentences: list[str]) -> list[tuple[int, int]]:
    """Locate each sentence in ``text`` and return its span."""
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for sentence in sentences:
        start = text.index(sentence, cursor)
        end = start + len(sentence)
        offsets.append((start, end))
        cursor = end
    return offsets


@pytest.fixture(scope="module")
def loaded_voice() -> LoadedVoice:
    settings = Settings.load()
    voices_dir = ensure_data_dirs(settings)
    installed = {voice.id for voice in list_voices()}
    if DEFAULT_VOICE_ID not in installed:
        pytest.skip(
            f"{DEFAULT_VOICE_ID} is not installed; run: python -m piper.download_voices "
            f"{DEFAULT_VOICE_ID} --download-dir {voices_dir}"
        )
    return load_voice(DEFAULT_VOICE_ID)


def _synthesize(voice: LoadedVoice, rate: float = 1.0) -> SynthesisResult:
    return synthesize(
        voice,
        TEXT,
        _segments(TEXT, SENTENCES),
        rate=rate,
        volume=1.0,
        cancel_event=threading.Event(),
        on_sentence=lambda sentence: None,
    )


def test_synthesizes_three_sentences_with_alignments(loaded_voice: LoadedVoice) -> None:
    result = _synthesize(loaded_voice)

    assert [sentence.text for sentence in result.sentences] == SENTENCES
    assert len(result.sentences) == 3
    assert result.sample_rate == 22_050
    assert result.supports_alignments is True
    assert sum(len(sentence.samples) for sentence in result.sentences) == result.total_samples
    assert result.total_samples > 0

    for sentence in result.sentences:
        assert isinstance(sentence, SentenceAudio)
        assert sentence.samples.ndim == 1
        assert sentence.samples.dtype == np.float32
        assert sentence.samples.size > 0
        assert sentence.supports_alignments is True
        assert sentence.phoneme_alignments
        assert all(phoneme not in {"^", "$", "_"} for phoneme, _ in sentence.phoneme_alignments)
        assert all(count > 0 for _, count in sentence.phoneme_alignments)


def _mean_seconds(loaded_voice: LoadedVoice, rate: float, runs: int = 7) -> float:
    durations = []
    for _ in range(runs):
        result = _synthesize(loaded_voice, rate=rate)
        durations.append(result.total_samples / result.sample_rate)
    return statistics.mean(durations)


def test_rate_scales_duration_within_ten_percent(loaded_voice: LoadedVoice) -> None:
    # length_scale = 1/rate, so rate 1.25 is nominally 0.8x the duration.
    # Piper 1.8's duration predictor is stochastic and only nearly linear for
    # length_scale < 1 (length_scale 2.0 measures ~1.73x, not 2x), so the
    # nominal 0.8x is never reached: measured ratios on en_US-lessac-medium
    # cluster around 0.87 and spread over 0.81-0.91 for a 3-run mean.
    # Averaging 7 runs per rate tightens the estimate to 0.855-0.896, so the
    # band asserts a clearly audible speed-up while tolerating the predictor's
    # randomness. The rate -> length_scale mapping itself is unit-tested.
    baseline = _mean_seconds(loaded_voice, rate=1.0)
    faster = _mean_seconds(loaded_voice, rate=1.25)

    assert baseline > 0
    assert 0.78 <= faster / baseline <= 0.93


def test_cancel_before_first_sentence_yields_empty_result(loaded_voice: LoadedVoice) -> None:
    cancel_event = threading.Event()
    cancel_event.set()
    seen: list[SentenceAudio] = []

    result = synthesize(
        loaded_voice,
        TEXT,
        _segments(TEXT, SENTENCES),
        rate=1.0,
        volume=1.0,
        cancel_event=cancel_event,
        on_sentence=seen.append,
    )

    assert result.sentences == []
    assert result.total_samples == 0
    assert seen == []
