"""Unit tests for the plain-text upload endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tts.app import create_app
from tts.config import Settings

MAX_UPLOAD_BYTES = 2 * 1024 * 1024


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id="en_US-lessac-medium",
    )


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(_settings(tmp_path)))


def test_upload_returns_decoded_text_and_size(tmp_path: Path) -> None:
    data = b"Hello world.\nSecond line."

    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.txt", data, "text/plain")},
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "Hello world.\nSecond line.",
        "filename": "notes.txt",
        "sizeBytes": len(data),
    }


def test_upload_strips_utf8_bom(tmp_path: Path) -> None:
    data = b"\xef\xbb\xbfHallo Welt"

    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.txt", data, "text/plain")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "Hallo Welt"
    assert response.json()["sizeBytes"] == len(data)


def test_upload_decodes_utf16_with_bom(tmp_path: Path) -> None:
    data = "Héllo wörld".encode("utf-16")

    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.txt", data, "text/plain")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "Héllo wörld"


def test_unsupported_extension_rejected_with_accepted_types(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.pdf", b"%PDF-1.4", "application/pdf")},
        )

    assert response.status_code == 415
    body = response.json()["error"]
    assert body["code"] == "UNSUPPORTED_FILE_TYPE"
    assert "only plain-text .txt files are accepted" in body["message"]


def test_unsupported_content_type_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.txt", b"hello", "application/pdf")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_octet_stream_content_type_is_accepted(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("notes.txt", b"hello", "application/octet-stream")},
        )

    assert response.status_code == 200
    assert response.json()["text"] == "hello"


def test_oversized_file_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("big.txt", b"a" * (MAX_UPLOAD_BYTES + 1), "text/plain")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_undecodable_bytes_rejected(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post(
            "/api/uploads",
            files={"file": ("bad.txt", b"not utf8 \xc3(", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "DECODE_FAILED"


def test_missing_file_field_uses_error_envelope(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        response = client.post("/api/uploads")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OUT_OF_RANGE"
