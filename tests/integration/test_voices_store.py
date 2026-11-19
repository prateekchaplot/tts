"""Integration tests for the voice store against a real Piper voice."""

from __future__ import annotations

import io
import wave

import pytest

from tts.config import Settings
from tts.voices.store import ensure_data_dirs, list_voices, load_voice, preview_wav

pytestmark = pytest.mark.integration

DEFAULT_VOICE_ID = "en_US-lessac-medium"


@pytest.fixture(scope="module")
def voice_id() -> str:
    settings = Settings.load()
    voices_dir = ensure_data_dirs(settings)
    installed = {voice.id for voice in list_voices()}
    if DEFAULT_VOICE_ID not in installed:
        pytest.skip(
            f"{DEFAULT_VOICE_ID} is not installed; run: python -m piper.download_voices "
            f"{DEFAULT_VOICE_ID} --download-dir {voices_dir}"
        )
    return DEFAULT_VOICE_ID


def test_list_voices_reports_real_voice_metadata(voice_id: str) -> None:
    voices = list_voices()
    match = next(voice for voice in voices if voice.id == voice_id)

    assert match.name == voice_id
    assert match.language == "en_US"
    assert match.sample_rate == 22_050
    assert match.gender is None
    assert voices == sorted(voices, key=lambda voice: (voice.language, voice.id))


def test_load_voice_supports_alignments(voice_id: str) -> None:
    loaded = load_voice(voice_id)

    assert loaded.supports_alignments is True
    assert loaded.voice.config.sample_rate == 22_050
    assert load_voice(voice_id) is loaded


def test_preview_wav_is_short_valid_pcm(voice_id: str) -> None:
    data = preview_wav(voice_id)

    assert data.startswith(b"RIFF")
    assert data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 22_050
        duration_seconds = wav_file.getnframes() / wav_file.getframerate()

    assert 0.0 < duration_seconds <= 5.0
