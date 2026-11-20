"""Integration test for the generations HTTP surface against a real Piper voice.

Covers the §14.2 T2.2 acceptance criteria end to end: create → SSE → succeeded
→ detail/media exports → delete, with a reconnect replay check.
"""

from __future__ import annotations

import io
import json
import wave
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tts.app import create_app
from tts.config import Settings
from tts.history.dal import Dal
from tts.jobs.manager import JobManager
from tts.voices.store import ensure_data_dirs, list_voices

pytestmark = pytest.mark.integration

VOICE_ID = "en_US-lessac-medium"
TEXT = "Hello from the generations API. This audio has two sentences."


def _event_names(body: str) -> list[str]:
    return [
        line.removeprefix("event: ") for line in body.splitlines() if line.startswith("event: ")
    ]


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    settings = Settings.load()
    voices_dir = ensure_data_dirs(settings)
    if VOICE_ID not in {voice.id for voice in list_voices()}:
        pytest.skip(
            f"{VOICE_ID} is not installed; run: python -m piper.download_voices "
            f"{VOICE_ID} --download-dir {voices_dir}"
        )

    dal = Dal(tmp_path_factory.mktemp("generations-api"), history_limit=settings.history_limit)
    jobs = JobManager(dal, settings)
    app = create_app(settings)
    app.state.dal = dal
    app.state.jobs = jobs
    with TestClient(app) as client:
        yield client, dal, jobs


def test_create_stream_detail_media_and_delete(env: Any) -> None:
    client: TestClient = env[0]
    dal: Dal = env[1]

    created = client.post(
        "/api/generations",
        json={"text": TEXT, "voiceId": VOICE_ID, "rate": 1.0, "volume": 1.0},
    )
    assert created.status_code == 202
    body = created.json()
    assert body["status"] == "queued"
    generation_id = body["generationId"]

    with client.stream("GET", f"/api/generations/{generation_id}/events") as stream:
        assert stream.status_code == 200
        stream_body = stream.read().decode("utf-8")

    assert "retry: 3000" in stream_body
    names = _event_names(stream_body)
    assert "succeeded" in names
    if "progress" in names:
        progress_payloads = [
            json.loads(line.removeprefix("data: "))
            for line in stream_body.splitlines()
            if line.startswith("data: ") and "sentenceIndex" in line
        ]
        assert max(int(item["sentenceIndex"]) for item in progress_payloads) >= 1

    # A reconnect replays the terminal state instead of leaving a gap (§9.2).
    with client.stream("GET", f"/api/generations/{generation_id}/events") as reconnect:
        replay = reconnect.read().decode("utf-8")
    assert _event_names(replay) == ["succeeded"]

    detail = client.get(f"/api/generations/{generation_id}")
    assert detail.status_code == 200
    result = detail.json()
    assert result["status"] == "succeeded"
    assert result["text"] == TEXT
    assert result["durationSeconds"] > 0
    assert result["wordTimings"]
    assert all(word["startMs"] <= word["endMs"] for word in result["wordTimings"])

    audio = client.get(f"/api/generations/{generation_id}/audio")
    assert audio.status_code == 200
    assert audio.headers["content-disposition"].endswith('.wav"')
    with wave.open(io.BytesIO(audio.content), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getsampwidth() == 2
        assert wav_file.getnframes() > 0

    for subtitle_format, header in (("srt", "1\n"), ("vtt", "WEBVTT")):
        subtitles = client.get(
            f"/api/generations/{generation_id}/subtitles",
            params={"format": subtitle_format},
        )
        assert subtitles.status_code == 200
        assert subtitles.text.startswith(header)
        assert subtitles.headers["content-disposition"].endswith(f'.{subtitle_format}"')

    audio_path = str(dal.get(generation_id)["audio_path"])
    deleted = client.delete(f"/api/generations/{generation_id}")
    assert deleted.status_code == 204
    assert dal.get(generation_id) is None
    assert not Path(audio_path).exists()
