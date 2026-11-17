"""Tests for application settings and logging."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest

from tts.config import Settings, configure_logging


def test_load_uses_defaults_and_creates_data_directories(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Keep the test independent of host-specific environment settings.
    for name in (
        "TTS_HOST",
        "TTS_PORT",
        "TTS_DATA_DIR",
        "TTS_MAX_INPUT_CHARS",
        "TTS_HISTORY_LIMIT",
        "TTS_LOG_LEVEL",
        "TTS_DEFAULT_VOICE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TTS_DATA_DIR", str(tmp_path / "app-data"))

    settings = Settings.load()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8321
    assert settings.data_dir == tmp_path / "app-data"
    assert settings.max_input_chars == 50_000
    assert settings.history_limit == 20
    assert settings.log_level == "INFO"
    assert settings.default_voice_id == "en_US-lessac-medium"
    assert settings.data_dir.is_dir()
    assert (settings.data_dir / "logs").is_dir()


def test_load_applies_every_environment_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TTS_HOST", "127.0.0.2")
    monkeypatch.setenv("TTS_PORT", "9000")
    monkeypatch.setenv("TTS_DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("TTS_MAX_INPUT_CHARS", "100000")
    monkeypatch.setenv("TTS_HISTORY_LIMIT", "50")
    monkeypatch.setenv("TTS_LOG_LEVEL", "debug")
    monkeypatch.setenv("TTS_DEFAULT_VOICE", "de_DE-thorsten-medium")

    settings = Settings.load()

    assert settings.host == "127.0.0.2"
    assert settings.port == 9000
    assert settings.data_dir == tmp_path / "custom"
    assert settings.max_input_chars == 100_000
    assert settings.history_limit == 50
    assert settings.log_level == "DEBUG"
    assert settings.default_voice_id == "de_DE-thorsten-medium"


def test_data_directory_default_is_platform_specific(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("TTS_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    cases = (
        ("win32", {"LOCALAPPDATA": str(tmp_path / "Local")}, tmp_path / "Local" / "tts"),
        (
            "darwin",
            {},
            tmp_path / "Library" / "Application Support" / "tts",
        ),
        ("linux", {}, tmp_path / ".local" / "share" / "tts"),
    )
    for platform, environment, expected in cases:
        monkeypatch.setattr(sys, "platform", platform)
        for name in ("LOCALAPPDATA",):
            monkeypatch.delenv(name, raising=False)
        for name, value in environment.items():
            monkeypatch.setenv(name, value)

        assert Settings.load().data_dir == expected


def test_unknown_log_level_warns_and_falls_back_to_info(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("TTS_DATA_DIR", str(tmp_path / "app-data"))
    monkeypatch.setenv("TTS_LOG_LEVEL", "verbose")

    with caplog.at_level(logging.WARNING):
        settings = Settings.load()

    assert settings.log_level == "INFO"
    assert "Unknown TTS_LOG_LEVEL" in caplog.text


def test_configure_logging_uses_rotating_file_and_expected_format(tmp_path: Path) -> None:
    settings = Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="DEBUG",
        default_voice_id="en_US-lessac-medium",
    )

    configure_logging(settings)

    root_logger = logging.getLogger()
    file_handlers = [
        handler for handler in root_logger.handlers if isinstance(handler, RotatingFileHandler)
    ]
    assert root_logger.level == logging.DEBUG
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(tmp_path / "logs" / "tts.log")
    assert file_handlers[0].maxBytes == 10 * 1024 * 1024
    assert file_handlers[0].backupCount == 5
    assert file_handlers[0].formatter is not None
    assert file_handlers[0].formatter._fmt == "%(asctime)s %(levelname)s %(name)s %(message)s"

    logging.shutdown()
