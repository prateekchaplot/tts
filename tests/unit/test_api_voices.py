"""Unit tests for the voice listing and preview endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tts.app import create_app
from tts.config import Settings
from tts.voices import store

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "voices"
DEFAULT_VOICE_ID = "de_DE-thorsten-low"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id=DEFAULT_VOICE_ID,
    )


def _client(tmp_path: Path) -> TestClient:
    settings = _settings(tmp_path)
    store.ensure_data_dirs(settings)
    return TestClient(create_app(settings, bootstrap_on_startup=False))


def _install_fixtures(voices_dir: Path, *names: str) -> None:
    voices_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(FIXTURES / f"{name}.onnx.json", voices_dir / f"{name}.onnx.json")
        (voices_dir / f"{name}.onnx").touch()


def test_list_voices_matches_the_contract(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _install_fixtures(tmp_path / "voices", "en_US-alpha-medium", DEFAULT_VOICE_ID)

    with client:
        response = client.get("/api/voices")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [DEFAULT_VOICE_ID, "en_US-alpha-medium"]
    assert body["items"][1]["sampleRate"] == 22_050
    assert body["items"][0]["language"] == "de_DE"
    assert body["total"] == 2
    assert body["defaultVoiceId"] == DEFAULT_VOICE_ID


def test_list_voices_with_empty_store(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.get("/api/voices")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "defaultVoiceId": DEFAULT_VOICE_ID}


def test_preview_unknown_voice_returns_voice_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)
    _install_fixtures(tmp_path / "voices", "en_US-alpha-medium")

    with client:
        response = client.post("/api/voices/preview", json={"voiceId": "en_US-missing-medium"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VOICE_NOT_FOUND"


def test_preview_with_empty_store_returns_no_voices_installed(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/voices/preview", json={"voiceId": "en_US-lessac-medium"})

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "NO_VOICES_INSTALLED"
    assert "tts add-voice" in body["message"]


def test_preview_engine_failure_maps_to_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path)
    _install_fixtures(tmp_path / "voices", "en_US-alpha-medium")

    def _fail(voice_id: str) -> bytes:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(store, "preview_wav", _fail)

    with client:
        response = client.post("/api/voices/preview", json={"voiceId": "en_US-alpha-medium"})

    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "ENGINE_ERROR"
    assert body["details"] is None


def test_preview_success_returns_wav_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(tmp_path)
    _install_fixtures(tmp_path / "voices", "en_US-alpha-medium")
    monkeypatch.setattr(store, "preview_wav", lambda voice_id: b"RIFF-wav")

    with client:
        response = client.post("/api/voices/preview", json={"voiceId": "en_US-alpha-medium"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFF-wav"


def test_preview_missing_voice_id_uses_error_envelope(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/voices/preview", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OUT_OF_RANGE"
