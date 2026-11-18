"""Tests for the standard error envelope and the API skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tts import __version__
from tts.api.errors import ERROR_STATUS, AppError
from tts.api.schemas import VoicePreviewRequest, WordTimingSchema
from tts.app import create_app, register_error_handlers
from tts.config import Settings


def _settings(data_dir: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=data_dir,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id="en_US-lessac-medium",
    )


def _test_app() -> FastAPI:
    """Minimal app with the production error handlers and two probe routes."""
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/probe/app-error")
    def _raise_with_details() -> None:
        raise AppError(
            "OUT_OF_RANGE",
            422,
            "Rate must be between 0.5 and 2.0.",
            {"field": "rate", "min": 0.5, "max": 2.0, "value": 3.0},
        )

    @app.get("/probe/plain-error")
    def _raise_without_details() -> None:
        raise AppError("GENERATION_NOT_FOUND", 404, "That generation no longer exists.")

    @app.post("/probe/echo")
    def _echo(payload: VoicePreviewRequest) -> VoicePreviewRequest:
        return payload

    return app


def test_health_body_matches_contract(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "status": "ok",
        "version": __version__,
        "voicesInstalled": 0,
        "defaultVoiceId": "en_US-lessac-medium",
    }


def test_health_counts_voice_models_in_the_store(tmp_path: Path) -> None:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    (voices_dir / "en_US-lessac-medium.onnx").write_bytes(b"")
    (voices_dir / "de_DE-thorsten-medium.onnx").write_bytes(b"")
    (voices_dir / "en_US-lessac-medium.onnx.json").write_text("{}", encoding="utf-8")

    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/health")

    assert response.json()["voicesInstalled"] == 2


def test_unknown_route_returns_not_found_envelope(tmp_path: Path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "error": {
            "code": "NOT_FOUND",
            "message": "The requested page or API route does not exist.",
            "details": None,
        }
    }


def test_app_error_serializes_exactly_with_details() -> None:
    with TestClient(_test_app()) as client:
        response = client.get("/probe/app-error")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "OUT_OF_RANGE",
            "message": "Rate must be between 0.5 and 2.0.",
            "details": {"field": "rate", "min": 0.5, "max": 2.0, "value": 3.0},
        }
    }


def test_app_error_without_details_serializes_null() -> None:
    with TestClient(_test_app()) as client:
        response = client.get("/probe/plain-error")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "GENERATION_NOT_FOUND",
            "message": "That generation no longer exists.",
            "details": None,
        }
    }


def test_unknown_error_code_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown API error code"):
        AppError("NOT_A_CONTRACT_CODE", 400, "nope")


def test_invalid_request_body_uses_the_error_envelope() -> None:
    with TestClient(_test_app()) as client:
        response = client.post("/probe/echo", json={"voiceId": 7})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "OUT_OF_RANGE"
    assert body["error"]["details"]["field"] == "voiceId"
    assert isinstance(body["error"]["details"]["reason"], str)


def test_word_timing_schema_serializes_camel_case() -> None:
    timing = WordTimingSchema(text="Hello", start_ms=120, end_ms=380, aligned=True)

    assert timing.model_dump(by_alias=True) == {
        "text": "Hello",
        "startMs": 120,
        "endMs": 380,
        "aligned": True,
    }
    assert timing.model_dump() == {
        "text": "Hello",
        "start_ms": 120,
        "end_ms": 380,
        "aligned": True,
    }


def test_error_status_table_matches_the_contract() -> None:
    assert ERROR_STATUS == {
        "EMPTY_INPUT": 422,
        "INPUT_TOO_LONG": 422,
        "OUT_OF_RANGE": 422,
        "VOICE_NOT_FOUND": 422,
        "UNSUPPORTED_FILE_TYPE": 415,
        "FILE_TOO_LARGE": 413,
        "DECODE_FAILED": 415,
        "NO_VOICES_INSTALLED": 409,
        "GENERATION_NOT_FOUND": 404,
        "GENERATION_NOT_READY": 409,
        "GENERATION_BUSY": 409,
        "SUBTITLE_FORMAT_UNKNOWN": 400,
        "NOT_FOUND": 404,
        "ENGINE_ERROR": 500,
        "INTERNAL_ERROR": 500,
    }
