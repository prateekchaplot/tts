"""Discover, load, and preview Piper voices in the local voice store."""

from __future__ import annotations

import io
import json
import logging
import re
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from tts.config import Settings

if TYPE_CHECKING:
    from piper import PiperVoice

logger = logging.getLogger(__name__)

PREVIEW_TEXT = "Hello! This is a short preview of this voice."

MODEL_SUFFIX = ".onnx"
CONFIG_SUFFIX = ".onnx.json"

_VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

_voices_dir: Path | None = None
_loaded_voices: dict[str, LoadedVoice] = {}
_load_lock = threading.Lock()


class VoiceNotFoundError(LookupError):
    """Raised when a requested voice is not installed in the local store."""


@dataclass(frozen=True)
class VoiceInfo:
    """Metadata for one installed voice, discovered from the filesystem."""

    id: str
    name: str
    language: str
    gender: str | None
    sample_rate: int


@dataclass(frozen=True)
class LoadedVoice:
    """A loaded Piper voice plus whether it exposes phoneme alignments."""

    voice: PiperVoice
    supports_alignments: bool


def ensure_data_dirs(settings: Settings) -> Path:
    """Create the voice store for these settings and remember it for later calls."""
    global _voices_dir
    voices_dir = settings.data_dir / "voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    _voices_dir = voices_dir
    return voices_dir


def _store_dir() -> Path:
    if _voices_dir is None:
        raise RuntimeError("voices.ensure_data_dirs() must be called before using the store")
    return _voices_dir


def _model_path(voice_id: str) -> Path:
    """Resolve a voice id to its model file, refusing anything path-like."""
    if not _VOICE_ID_PATTERN.fullmatch(voice_id):
        raise VoiceNotFoundError(voice_id)
    model_path = _store_dir() / f"{voice_id}{MODEL_SUFFIX}"
    if not model_path.is_file():
        raise VoiceNotFoundError(voice_id)
    return model_path


def _read_metadata(model_path: Path) -> VoiceInfo | None:
    """Read one voice's metadata, returning None when its config is unusable."""
    voice_id = model_path.name[: -len(MODEL_SUFFIX)]
    config_path = model_path.with_name(f"{voice_id}{CONFIG_SUFFIX}")
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        sample_rate = int(config["audio"]["sample_rate"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        logger.warning("Skipping voice %s: %s", voice_id, error)
        return None

    language_config = config.get("language")
    language = ""
    if isinstance(language_config, dict):
        language = str(language_config.get("code") or "")
    if not language:
        language = voice_id.split("-", 1)[0]

    return VoiceInfo(
        id=voice_id,
        name=voice_id,
        language=language,
        gender=None,
        sample_rate=sample_rate,
    )


def list_voices() -> list[VoiceInfo]:
    """Return installed voices sorted by language, then id."""
    voices = [
        info
        for path in _store_dir().glob(f"*{MODEL_SUFFIX}")
        if path.is_file() and (info := _read_metadata(path)) is not None
    ]
    return sorted(voices, key=lambda voice: (voice.language, voice.id))


def load_voice(voice_id: str) -> LoadedVoice:
    """Load a voice, enabling alignment patching, and cache it for this process."""
    model_path = _model_path(voice_id)
    with _load_lock:
        loaded = _loaded_voices.get(voice_id)
        if loaded is None:
            loaded = _load(voice_id, model_path)
            _loaded_voices[voice_id] = loaded
    return loaded


def _load(voice_id: str, model_path: Path) -> LoadedVoice:
    from piper import PiperVoice

    try:
        voice = PiperVoice.load(model_path, include_alignments=True)
    except (ImportError, ValueError) as error:
        logger.warning("Loading voice %s without alignments: %s", voice_id, error)
        voice = PiperVoice.load(model_path, include_alignments=False)

    # The alignment patch adds a second model output (the phoneme-width tensor).
    supports_alignments = len(voice.session.get_outputs()) > 1
    if not supports_alignments:
        logger.info("Voice %s does not support phoneme alignments", voice_id)
    return LoadedVoice(voice=voice, supports_alignments=supports_alignments)


def preview_wav(voice_id: str) -> bytes:
    """Render the fixed preview phrase for a voice as WAV bytes."""
    loaded = load_voice(voice_id)
    from piper import SynthesisConfig

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        loaded.voice.synthesize_wav(
            PREVIEW_TEXT,
            wav_file,
            syn_config=SynthesisConfig(length_scale=1.0, volume=1.0),
        )
    return buffer.getvalue()


def install_voice(name: str) -> str:
    """Download a voice into the local store and return its id."""
    from piper.download_voices import download_voice

    download_voice(name, _store_dir())
    return name.strip()
