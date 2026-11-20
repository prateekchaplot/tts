"""Integration tests for voice routes against a real Piper voice."""

from __future__ import annotations

import io
import wave
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tts.app import create_app
from tts.config import Settings
from tts.voices.store import ensure_data_dirs, list_voices

pytestmark = pytest.mark.integration

DEFAULT_VOICE_ID = "en_US-lessac-medium"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    settings = Settings.load()
    voices_dir = ensure_data_dirs(settings)
    installed = {voice.id for voice in list_voices()}
    if DEFAULT_VOICE_ID not in installed:
        pytest.skip(
            f"{DEFAULT_VOICE_ID} is not installed; run: python -m piper.download_voices "
            f"{DEFAULT_VOICE_ID} --download-dir {voices_dir}"
        )
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_list_voices_includes_the_real_voice(client: TestClient) -> None:
    response = client.get("/api/voices")

    assert response.status_code == 200
    body = response.json()
    match = next(item for item in body["items"] if item["id"] == DEFAULT_VOICE_ID)
    assert match["language"] == "en_US"
    assert match["sampleRate"] == 22_050
    assert match["gender"] is None


def test_preview_returns_a_short_valid_pcm_wav(client: TestClient) -> None:
    response = client.post("/api/voices/preview", json={"voiceId": DEFAULT_VOICE_ID})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    data = response.content
    assert data.startswith(b"RIFF")
    assert data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getframerate() == 22_050
        duration_seconds = wav_file.getnframes() / wav_file.getframerate()

    assert 0.0 < duration_seconds <= 5.0
