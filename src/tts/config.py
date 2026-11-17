"""Application configuration and logging setup."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

logger = logging.getLogger(__name__)


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "tts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "tts"
    return Path.home() / ".local" / "share" / "tts"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    data_dir: Path
    max_input_chars: int
    history_limit: int
    log_level: str
    default_voice_id: str

    @classmethod
    def load(cls) -> Settings:
        """Load settings from the environment and create the data directories."""
        raw_log_level = os.environ.get("TTS_LOG_LEVEL", "INFO").upper()
        if raw_log_level not in logging.getLevelNamesMapping():
            logger.warning("Unknown TTS_LOG_LEVEL %r; falling back to INFO", raw_log_level)
            raw_log_level = "INFO"

        data_dir = Path(os.environ.get("TTS_DATA_DIR", _default_data_dir())).expanduser()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "logs").mkdir(parents=True, exist_ok=True)

        return cls(
            host=os.environ.get("TTS_HOST", "127.0.0.1"),
            port=int(os.environ.get("TTS_PORT", "8321")),
            data_dir=data_dir,
            max_input_chars=int(os.environ.get("TTS_MAX_INPUT_CHARS", "50000")),
            history_limit=int(os.environ.get("TTS_HISTORY_LIMIT", "20")),
            log_level=raw_log_level,
            default_voice_id=os.environ.get("TTS_DEFAULT_VOICE", "en_US-lessac-medium"),
        )


def configure_logging(settings: Settings) -> None:
    """Configure stdout and rotating file logging for the application."""
    logs_dir = settings.data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    level = logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    stream_handler = logging.StreamHandler()
    stream_handler.set_name("tts.stdout")
    stream_handler.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        logs_dir / "tts.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.set_name("tts.file")
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if handler.get_name() in {"tts.stdout", "tts.file"}:
            root_logger.removeHandler(handler)
            handler.close()
    root_logger.setLevel(level)
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
