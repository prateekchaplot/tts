"""Tests for the local Piper voice store."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from tts.config import Settings
from tts.voices import store
from tts.voices.store import (
    VoiceInfo,
    VoiceNotFoundError,
    ensure_data_dirs,
    list_voices,
    load_voice,
    preview_wav,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "voices"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path / "data",
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id="en_US-alpha-medium",
    )


def _configure(tmp_path: Path) -> Path:
    return ensure_data_dirs(_settings(tmp_path))


def _install_fixtures(store_dir: Path, *names: str) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    for name in names:
        shutil.copyfile(FIXTURES / f"{name}.onnx.json", store_dir / f"{name}.onnx.json")
        (store_dir / f"{name}.onnx").touch()


def test_ensure_data_dirs_creates_the_voice_store(tmp_path: Path) -> None:
    store_dir = _configure(tmp_path)

    assert store_dir == tmp_path / "data" / "voices"
    assert store_dir.is_dir()


def test_store_requires_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(store, "_voices_dir", None)

    with pytest.raises(RuntimeError, match="ensure_data_dirs"):
        list_voices()


def test_list_voices_returns_sorted_metadata(tmp_path: Path) -> None:
    store_dir = _configure(tmp_path)
    _install_fixtures(
        store_dir,
        "en_US-alpha-medium",
        "de_DE-thorsten-low",
        "en_GB-alba-medium",
        "xx_XX-nolang-medium",
    )

    voices = list_voices()

    assert [voice.id for voice in voices] == [
        "de_DE-thorsten-low",
        "en_GB-alba-medium",
        "en_US-alpha-medium",
        "xx_XX-nolang-medium",
    ]
    assert voices[0] == VoiceInfo(
        id="de_DE-thorsten-low",
        name="de_DE-thorsten-low",
        language="de_DE",
        gender=None,
        sample_rate=16_000,
    )
    assert voices[2].language == "en_US"
    assert voices[2].sample_rate == 22_050


def test_list_voices_falls_back_to_the_id_language_prefix(tmp_path: Path) -> None:
    store_dir = _configure(tmp_path)
    _install_fixtures(store_dir, "xx_XX-nolang-medium")

    (voice,) = list_voices()

    assert voice.language == "xx_XX"


def test_list_voices_skips_unusable_configs(tmp_path: Path) -> None:
    store_dir = _configure(tmp_path)
    _install_fixtures(store_dir, "en_US-alpha-medium")
    _install_fixtures(store_dir, "broken-missing-rate", "corrupt-not-json")
    (store_dir / "orphan-without-config.onnx").touch()
    (store_dir / "notes.txt").write_text("not a voice", encoding="utf-8")

    voices = list_voices()

    assert [voice.id for voice in voices] == ["en_US-alpha-medium"]


def test_load_voice_rejects_unknown_ids(tmp_path: Path) -> None:
    _configure(tmp_path)

    with pytest.raises(VoiceNotFoundError):
        load_voice("en_US-missing-medium")


@pytest.mark.parametrize("voice_id", ["../escape", "sub/dir", ".hidden", "with space"])
def test_voice_ids_cannot_escape_the_store(tmp_path: Path, voice_id: str) -> None:
    _configure(tmp_path)

    with pytest.raises(VoiceNotFoundError):
        load_voice(voice_id)


def test_preview_of_unknown_voice_does_not_load_the_engine(tmp_path: Path) -> None:
    _configure(tmp_path)
    assert "piper" not in sys.modules

    with pytest.raises(VoiceNotFoundError):
        preview_wav("en_US-missing-medium")

    assert "piper" not in sys.modules
