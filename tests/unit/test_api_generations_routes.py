"""Unit tests for the generations HTTP surface (§9.2, task T2.2)."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Literal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tts.api.routes import generations
from tts.app import create_app
from tts.config import Settings
from tts.history.dal import Dal
from tts.jobs.manager import GenerationNotFoundError
from tts.jobs.sse import SseEvent, Subscriber
from tts.voices.store import VoiceInfo

VOICE = VoiceInfo(id="v1", name="Voice One", language="en", gender=None, sample_rate=22_050)


class FakeJobs:
    """A job manager stand-in: no engine, no worker thread, no piper import."""

    def __init__(self) -> None:
        self.submissions: list[dict[str, Any]] = []
        self.subscribed: list[str] = []
        self.events: list[SseEvent] = []
        self.known_ids: set[str] = set()
        self.cancel_result: Literal["cancelled", "cancelling"] = "cancelled"

    def submit(self, **kwargs: Any) -> str:
        self.submissions.append(kwargs)
        return str(uuid.uuid4())

    def cancel(self, generation_id: str) -> Literal["cancelled", "cancelling"]:
        return self.cancel_result

    def subscribe(self, generation_id: str) -> Subscriber:
        if generation_id not in self.known_ids:
            raise GenerationNotFoundError(generation_id)
        self.subscribed.append(generation_id)
        subscriber = Subscriber(generation_id)
        for event in self.events:
            subscriber.put(event)
        subscriber.close()
        return subscriber


@dataclass
class Env:
    client: TestClient
    app: FastAPI
    dal: Dal
    jobs: FakeJobs
    settings: Settings


def _app(settings: Settings, dal: Dal, jobs: FakeJobs) -> FastAPI:
    app = create_app(settings, bootstrap_on_startup=False)
    app.state.dal = dal
    app.state.jobs = jobs
    return app


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    settings = Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path / "data",
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id="v1",
    )
    dal = Dal(settings.data_dir, history_limit=settings.history_limit)
    monkeypatch.setattr(generations.store, "list_voices", lambda: [VOICE])
    monkeypatch.setattr(generations.store, "ensure_data_dirs", lambda s: s.data_dir / "voices")
    jobs = FakeJobs()
    app = _app(settings, dal, jobs)
    with TestClient(app) as client:
        yield Env(client=client, app=app, dal=dal, jobs=jobs, settings=settings)


def _succeeded_row(env: Env, text: str = "Hello world this is a test") -> tuple[str, Path]:
    """Store a succeeded row with a real WAV stub and camelCase result columns."""
    generations_dir = env.settings.data_dir / "generations"
    generations_dir.mkdir(parents=True, exist_ok=True)
    wav = generations_dir / "audio.wav"
    wav.write_bytes(b"RIFFfake wave data")
    generation_id = env.dal.create_generation(text=text, voice_id="v1", voice_name="Voice One")
    env.dal.set_status(
        generation_id,
        "succeeded",
        duration_seconds=2.5,
        sample_rate=22_050,
        audio_path=str(wav),
        word_timings_json=json.dumps(
            [{"text": "Hello", "startMs": 10, "endMs": 300, "aligned": True}]
        ),
        cues_json=json.dumps([{"index": 1, "startMs": 0, "endMs": 2_000, "text": "Hello world"}]),
        aligned_word_ratio=0.9,
    )
    return generation_id, wav


# -- create ------------------------------------------------------------------


def test_create_queues_with_validation_order_and_defaults(env: Env) -> None:
    response = env.client.post("/api/generations", json={"text": "Hello world."})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert uuid.UUID(response.json()["generationId"])
    assert env.jobs.submissions == [
        {
            "voice_id": "v1",
            "text": "Hello world.",
            "source_type": "text",
            "rate": 1.0,
            "volume": 1.0,
        }
    ]
    assert env.dal.get_settings() == {"defaultVoiceId": "v1", "rate": 1.0, "volume": 1.0}


def test_create_uses_persisted_defaults_when_fields_omitted(env: Env) -> None:
    env.dal.put_settings({"defaultVoiceId": "v1", "rate": 1.25, "volume": 0.5})

    response = env.client.post("/api/generations", json={"text": "Hello"})

    assert response.status_code == 202
    assert env.jobs.submissions[0]["rate"] == 1.25
    assert env.jobs.submissions[0]["volume"] == 0.5


def test_create_empty_text_returns_empty_input(env: Env) -> None:
    response = env.client.post("/api/generations", json={"text": "   \n"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EMPTY_INPUT"
    assert env.jobs.submissions == []


def test_create_over_limit_returns_input_too_long_with_details(env: Env) -> None:
    settings = replace(env.settings, max_input_chars=5)
    with TestClient(_app(settings, env.dal, env.jobs)) as client:
        response = client.post("/api/generations", json={"text": "six chars"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INPUT_TOO_LONG"
    assert error["details"] == {"maxChars": 5, "receivedChars": 9}


def test_create_without_voices_returns_no_voices(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(generations.store, "list_voices", list)

    response = env.client.post("/api/generations", json={"text": "Hello"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "NO_VOICES_INSTALLED"
    assert "tts add-voice" in response.json()["error"]["message"]


def test_create_unknown_voice_returns_voice_not_found(env: Env) -> None:
    response = env.client.post("/api/generations", json={"text": "Hello", "voiceId": "nope"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VOICE_NOT_FOUND"


@pytest.mark.parametrize(
    ("field", "value"),
    [("rate", 2.1), ("rate", 0.49), ("volume", -0.1), ("volume", 1.1)],
)
def test_create_out_of_range_returns_details(env: Env, field: str, value: float) -> None:
    response = env.client.post("/api/generations", json={"text": "Hello", field: value})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "OUT_OF_RANGE"
    assert error["details"]["field"] == field
    assert "min" in error["details"] and "max" in error["details"]


# -- list and detail ---------------------------------------------------------


def test_list_maps_summaries_and_pagination(env: Env) -> None:
    first, _ = _succeeded_row(env, "First text")
    second = env.dal.create_generation(text="Second text", voice_id="v1", voice_name="Voice One")
    env.dal.set_status(second, "failed", error={"code": "ENGINE_ERROR", "message": "Boom"})

    response = env.client.get("/api/generations", params={"limit": 1, "offset": 0})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["generationId"] == second
    assert item["inputPreview"] == "Second text"
    assert item["error"] == {"code": "ENGINE_ERROR", "message": "Boom"}
    assert "durationSeconds" in item and "createdAt" in item
    assert str(first) != second


def test_detail_pending_fields_are_null(env: Env) -> None:
    generation_id = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")

    response = env.client.get(f"/api/generations/{generation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    for key in ("wordTimings", "cues", "alignedWordRatio", "durationSeconds", "sampleRate"):
        assert body[key] is None, key


def test_detail_succeeded_maps_camel_case_results(env: Env) -> None:
    generation_id, _ = _succeeded_row(env)

    response = env.client.get(f"/api/generations/{generation_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "Hello world this is a test"
    assert body["alignedWordRatio"] == 0.9
    assert body["sampleRate"] == 22_050
    assert body["durationSeconds"] == 2.5
    assert body["wordTimings"] == [{"text": "Hello", "startMs": 10, "endMs": 300, "aligned": True}]
    assert body["cues"] == [{"index": 1, "startMs": 0, "endMs": 2_000, "text": "Hello world"}]


@pytest.mark.parametrize("generation_id", ["not-a-uuid", "00000000-0000-0000-0000-0000000000000"])
def test_detail_unknown_or_malformed_id_is_not_found(env: Env, generation_id: str) -> None:
    response = env.client.get(f"/api/generations/{generation_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "GENERATION_NOT_FOUND"


# -- media -------------------------------------------------------------------


def test_audio_requires_success_and_sets_download_name(env: Env) -> None:
    pending = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")
    assert env.client.get(f"/api/generations/{pending}/audio").status_code == 409

    generation_id, wav = _succeeded_row(env)
    response = env.client.get(f"/api/generations/{generation_id}/audio")

    assert response.status_code == 200
    assert response.content == wav.read_bytes()
    assert re.fullmatch(
        r'attachment; filename="hello-world-this-is-a-test_\d{8}-\d{6}\.wav"',
        response.headers["content-disposition"],
    )


def test_subtitles_render_srt_and_vtt_with_named_downloads(env: Env) -> None:
    generation_id, _ = _succeeded_row(env)

    srt = env.client.get(f"/api/generations/{generation_id}/subtitles", params={"format": "srt"})
    assert srt.status_code == 200
    assert "Hello world" in srt.text
    assert srt.headers["content-disposition"].endswith('.srt"')

    vtt = env.client.get(f"/api/generations/{generation_id}/subtitles", params={"format": "vtt"})
    assert vtt.status_code == 200
    assert vtt.text.startswith("WEBVTT")
    assert vtt.headers["content-disposition"].endswith('.vtt"')


def test_download_name_caps_slug_at_six_words(env: Env) -> None:
    generation_id, _ = _succeeded_row(env, "One two three four five six seven eight")

    response = env.client.get(
        f"/api/generations/{generation_id}/subtitles", params={"format": "srt"}
    )

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="one-two-three-four-five-six_'
    )


def test_subtitles_bad_format_names_accepted_values(env: Env) -> None:
    generation_id, _ = _succeeded_row(env)

    response = env.client.get(f"/api/generations/{generation_id}/subtitles")

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "SUBTITLE_FORMAT_UNKNOWN"
    assert "srt" in error["message"] and "vtt" in error["message"]


def test_subtitles_before_success_are_not_ready(env: Env) -> None:
    generation_id = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")

    response = env.client.get(
        f"/api/generations/{generation_id}/subtitles", params={"format": "srt"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GENERATION_NOT_READY"


# -- SSE ---------------------------------------------------------------------


def test_events_send_retry_then_replay_then_terminal(env: Env) -> None:
    generation_id = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")
    env.jobs.known_ids.add(generation_id)
    env.jobs.events = [
        SseEvent(
            name="progress",
            data={
                "generationId": generation_id,
                "status": "running",
                "sentenceIndex": 1,
                "sentenceCount": 2,
            },
        ),
        SseEvent(
            name="succeeded",
            data={"generationId": generation_id, "status": "succeeded", "durationSeconds": 2.5},
            terminal=True,
        ),
    ]

    with env.client.stream("GET", f"/api/generations/{generation_id}/events") as response:
        body = "\n".join(response.iter_lines())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body.startswith("retry: 3000")
    assert "event: progress" in body
    assert "event: succeeded" in body
    assert generation_id in body
    assert env.jobs.subscribed == [generation_id]


def test_events_unknown_id_fails_before_stream(env: Env) -> None:
    with env.client.stream("GET", "/api/generations/not-a-uuid/events") as response:
        response.read()
        assert response.status_code == 404

    with env.client.stream("GET", f"/api/generations/{uuid.uuid4()}/events") as response:
        response.read()
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "GENERATION_NOT_FOUND"
    assert env.jobs.subscribed == []


# -- cancel and delete -------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "cancel_result", "expected"),
    [("queued", "cancelled", "cancelled"), ("running", "cancelling", "cancelling")],
)
def test_cancel_maps_job_answer(
    env: Env, status: str, cancel_result: Literal["cancelled", "cancelling"], expected: str
) -> None:
    generation_id = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")
    env.dal.set_status(generation_id, status)
    env.jobs.cancel_result = cancel_result

    response = env.client.post(f"/api/generations/{generation_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"generationId": generation_id, "status": expected}


def test_cancel_already_cancelling_answers_cancelled(env: Env) -> None:
    generation_id = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")
    env.dal.set_status(generation_id, "cancelling")
    env.jobs.cancel_result = "cancelling"

    response = env.client.post(f"/api/generations/{generation_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_terminal_is_busy_and_unknown_is_not_found(env: Env) -> None:
    done, _ = _succeeded_row(env)
    busy = env.client.post(f"/api/generations/{done}/cancel")
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "GENERATION_BUSY"

    missing = env.client.post(f"/api/generations/{uuid.uuid4()}/cancel")
    assert missing.status_code == 404


def test_delete_removes_row_and_audio(env: Env) -> None:
    generation_id, wav = _succeeded_row(env)

    response = env.client.delete(f"/api/generations/{generation_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert env.dal.get(generation_id) is None
    assert not wav.exists()


def test_delete_active_is_busy_and_unknown_is_not_found(env: Env) -> None:
    active = env.dal.create_generation(text="Hello", voice_id="v1", voice_name="Voice One")
    busy = env.client.delete(f"/api/generations/{active}")
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "GENERATION_BUSY"

    missing = env.client.delete(f"/api/generations/{uuid.uuid4()}")
    assert missing.status_code == 404
