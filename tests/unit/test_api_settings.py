"""Tests for settings persistence and first-run bootstrap."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tts.app import create_app
from tts.config import Settings

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "voices"
DEFAULT_VOICE_ID = "de_DE-thorsten-low"
OTHER_VOICE_ID = "en_US-alpha-medium"


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


def _install_fixture(voices_dir: Path, voice_id: str) -> None:
    shutil.copyfile(FIXTURES / f"{voice_id}.onnx.json", voices_dir / f"{voice_id}.onnx.json")
    (voices_dir / f"{voice_id}.onnx").touch()


def test_settings_seed_lazily_and_partial_updates_persist(tmp_path: Path) -> None:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    _install_fixture(voices_dir, DEFAULT_VOICE_ID)
    _install_fixture(voices_dir, OTHER_VOICE_ID)
    app = create_app(_settings(tmp_path), bootstrap_on_startup=False)

    with TestClient(app) as client:
        seeded = client.get("/api/settings")
        assert seeded.status_code == 200
        assert seeded.json() == {
            "defaultVoiceId": DEFAULT_VOICE_ID,
            "rate": 1.0,
            "volume": 1.0,
        }

        updated = client.put("/api/settings", json={"rate": 1.4})
        assert updated.status_code == 200
        assert updated.json() == {
            "defaultVoiceId": DEFAULT_VOICE_ID,
            "rate": 1.4,
            "volume": 1.0,
        }

        updated_voice = client.put("/api/settings", json={"defaultVoiceId": OTHER_VOICE_ID})
        assert updated_voice.status_code == 200
        assert updated_voice.json() == {
            "defaultVoiceId": OTHER_VOICE_ID,
            "rate": 1.4,
            "volume": 1.0,
        }
        assert client.get("/api/settings").json() == updated_voice.json()
        assert client.get("/api/health").json()["defaultVoiceId"] == OTHER_VOICE_ID
        assert client.get("/api/voices").json()["defaultVoiceId"] == OTHER_VOICE_ID

    with TestClient(create_app(_settings(tmp_path), bootstrap_on_startup=False)) as reopened:
        assert reopened.get("/api/settings").json() == updated_voice.json()


def test_settings_update_rejects_unknown_voice_without_persisting(tmp_path: Path) -> None:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    _install_fixture(voices_dir, DEFAULT_VOICE_ID)

    with TestClient(create_app(_settings(tmp_path), bootstrap_on_startup=False)) as client:
        response = client.put("/api/settings", json={"defaultVoiceId": "en_US-missing"})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VOICE_NOT_FOUND"
        assert client.get("/api/settings").json()["defaultVoiceId"] == DEFAULT_VOICE_ID


@pytest.mark.parametrize(
    ("patch", "field", "minimum", "maximum"),
    [
        ({"rate": 0.49}, "rate", 0.5, 2.0),
        ({"rate": 2.01}, "rate", 0.5, 2.0),
        ({"volume": -0.01}, "volume", 0.0, 1.0),
        ({"volume": 1.01}, "volume", 0.0, 1.0),
    ],
)
def test_settings_update_rejects_out_of_range_values(
    tmp_path: Path,
    patch: dict[str, float],
    field: str,
    minimum: float,
    maximum: float,
) -> None:
    with TestClient(create_app(_settings(tmp_path), bootstrap_on_startup=False)) as client:
        response = client.put("/api/settings", json=patch)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OUT_OF_RANGE"
    assert response.json()["error"]["details"]["field"] == field
    assert response.json()["error"]["details"]["min"] == minimum
    assert response.json()["error"]["details"]["max"] == maximum


def test_settings_update_rejects_extra_and_null_values(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path), bootstrap_on_startup=False)) as client:
        extra = client.put("/api/settings", json={"unknown": 1})
        null_rate = client.put("/api/settings", json={"rate": None})

    assert extra.status_code == 422
    assert extra.json()["error"]["code"] == "OUT_OF_RANGE"
    assert null_rate.status_code == 422
    assert null_rate.json()["error"]["code"] == "OUT_OF_RANGE"


def test_offline_first_run_keeps_app_serving_without_voices(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_install(name: str) -> str:
        raise OSError("network unavailable")

    monkeypatch.setattr("tts.jobs.manager.install_voice", fail_install)
    with TestClient(create_app(_settings(tmp_path))) as client:
        health = client.get("/api/health")

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["voicesInstalled"] == 0
    assert health.json()["defaultVoiceId"] == DEFAULT_VOICE_ID
