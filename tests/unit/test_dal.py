"""Tests for the history data access layer."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tts.history import dal as dal_module
from tts.history.dal import Dal


def _make_generation(instance: Dal, **overrides: object) -> str:
    values: dict[str, object] = {
        "text": "Hello world.",
        "voice_id": "en_US-lessac-medium",
        "voice_name": "Lessac",
    }
    values.update(overrides)
    return instance.create_generation(**values)  # type: ignore[arg-type]


class _Clock:
    """Deterministic clock so ordering tests never depend on wall time."""

    def __init__(self) -> None:
        self._next = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> str:
        value = self._next.isoformat(timespec="milliseconds")
        self._next += timedelta(seconds=1)
        return value


@pytest.fixture
def dal(tmp_path: Path) -> Iterator[Dal]:
    instance = Dal(tmp_path)
    try:
        yield instance
    finally:
        instance.close()


def test_schema_applied_on_first_run(tmp_path: Path) -> None:
    instance = Dal(tmp_path)
    instance.close()

    db_path = tmp_path / "library.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        objects = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE name IS NOT NULL")
        }
    assert {"generations", "app_settings", "idx_generations_created"} <= objects


def test_second_run_is_a_noop_migration(tmp_path: Path) -> None:
    first = Dal(tmp_path)
    generation_id = _make_generation(first)
    first.close()

    second = Dal(tmp_path)
    try:
        assert second.get(generation_id) is not None
        with sqlite3.connect(tmp_path / "library.db") as conn:
            assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        second.close()


def test_create_generation_roundtrip(dal: Dal) -> None:
    generation_id = _make_generation(dal)

    assert uuid.UUID(generation_id).version == 4
    row = dal.get(generation_id)
    assert row is not None
    assert row["id"] == generation_id
    assert row["status"] == "queued"
    assert row["source_type"] == "text"
    assert row["input_text"] == "Hello world."
    assert row["input_filename"] is None
    assert row["voice_id"] == "en_US-lessac-medium"
    assert row["voice_name"] == "Lessac"
    assert row["rate"] == 1.0
    assert row["volume"] == 1.0
    assert row["duration_seconds"] is None
    assert row["sample_rate"] is None
    assert row["audio_path"] is None
    assert row["word_timings_json"] is None
    assert row["cues_json"] is None
    assert row["aligned_word_ratio"] is None
    assert row["error_code"] is None
    assert row["error_message"] is None
    assert datetime.fromisoformat(row["created_at"]).tzinfo is not None


def test_create_generation_records_uploaded_file(dal: Dal) -> None:
    generation_id = _make_generation(
        dal,
        text="Uploaded words.",
        source_type="file",
        input_filename="notes.txt",
        rate=1.5,
        volume=0.5,
    )

    row = dal.get(generation_id)
    assert row is not None
    assert row["source_type"] == "file"
    assert row["input_filename"] == "notes.txt"
    assert row["rate"] == 1.5
    assert row["volume"] == 0.5


def test_get_unknown_generation_returns_none(dal: Dal) -> None:
    assert dal.get(str(uuid.uuid4())) is None


def test_set_status_persists_result_fields(dal: Dal) -> None:
    generation_id = _make_generation(dal)

    dal.set_status(
        generation_id,
        "succeeded",
        duration_seconds=4.25,
        sample_rate=22050,
        audio_path="generations/audio.wav",
        word_timings_json="[]",
        cues_json="[]",
        aligned_word_ratio=0.9,
    )

    row = dal.get(generation_id)
    assert row is not None
    assert row["status"] == "succeeded"
    assert row["duration_seconds"] == 4.25
    assert row["sample_rate"] == 22050
    assert row["audio_path"] == "generations/audio.wav"
    assert row["word_timings_json"] == "[]"
    assert row["cues_json"] == "[]"
    assert row["aligned_word_ratio"] == 0.9


def test_set_status_persists_error_pair(dal: Dal) -> None:
    generation_id = _make_generation(dal)

    dal.set_status(
        generation_id,
        "failed",
        error={"code": "ENGINE_ERROR", "message": "synthesis failed"},
    )

    row = dal.get(generation_id)
    assert row is not None
    assert row["status"] == "failed"
    assert row["error_code"] == "ENGINE_ERROR"
    assert row["error_message"] == "synthesis failed"


def test_set_status_rejects_unknown_id_and_fields(dal: Dal) -> None:
    with pytest.raises(KeyError):
        dal.set_status(str(uuid.uuid4()), "succeeded")

    generation_id = _make_generation(dal)
    with pytest.raises(ValueError, match="unknown generation result field"):
        dal.set_status(generation_id, "succeeded", created_at="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="missing keys"):
        dal.set_status(generation_id, "failed", error={"code": "ENGINE_ERROR"})


def test_list_returns_newest_first_with_total(dal: Dal, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    created = [_make_generation(dal) for _ in range(3)]

    rows, total = dal.list()
    assert total == 3
    assert [row["id"] for row in rows] == list(reversed(created))

    page, total = dal.list(limit=1, offset=1)
    assert total == 3
    assert [row["id"] for row in page] == [created[1]]


def test_delete_removes_row_and_audio_file(dal: Dal, tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.wav"
    audio_path.write_bytes(b"RIFF")
    generation_id = _make_generation(dal)
    dal.set_status(generation_id, "succeeded", audio_path=str(audio_path))

    assert dal.delete(generation_id) is True
    assert dal.get(generation_id) is None
    assert not audio_path.exists()
    assert dal.delete(generation_id) is False


def test_delete_tolerates_missing_audio_file(dal: Dal, tmp_path: Path) -> None:
    generation_id = _make_generation(dal)
    dal.set_status(generation_id, "succeeded", audio_path=str(tmp_path / "gone.wav"))

    assert dal.delete(generation_id) is True
    assert dal.get(generation_id) is None


def test_evict_deletes_oldest_first_and_removes_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    instance = Dal(tmp_path, history_limit=2)
    try:
        created: list[tuple[str, Path]] = []
        for _ in range(3):
            generation_id = _make_generation(instance)
            audio_path = tmp_path / f"{generation_id}.wav"
            audio_path.write_bytes(b"RIFF")
            instance.set_status(generation_id, "succeeded", audio_path=str(audio_path))
            created.append((generation_id, audio_path))

        deleted = instance.evict_to_limit()

        assert deleted == [created[0][0]]
        rows, total = instance.list()
        assert total == 2
        assert [row["id"] for row in rows] == [created[2][0], created[1][0]]
        assert not created[0][1].exists()
        assert created[1][1].exists()
        assert created[2][1].exists()
    finally:
        instance.close()


def test_evict_never_deletes_active_ids(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    instance = Dal(tmp_path, history_limit=1)
    try:
        created = [_make_generation(instance) for _ in range(3)]

        deleted = instance.evict_to_limit({created[0]})

        assert deleted == [created[1], created[2]]
        rows, total = instance.list()
        assert total == 1
        assert rows[0]["id"] == created[0]
    finally:
        instance.close()


def test_evict_is_noop_when_all_rows_are_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    instance = Dal(tmp_path, history_limit=1)
    try:
        created = [_make_generation(instance) for _ in range(2)]

        assert instance.evict_to_limit(set(created)) == []
        _, total = instance.list()
        assert total == 2
    finally:
        instance.close()


def test_evict_is_noop_under_limit(dal: Dal) -> None:
    created = [_make_generation(dal) for _ in range(2)]

    assert dal.evict_to_limit() == []
    rows, total = dal.list()
    assert total == 2
    assert {row["id"] for row in rows} == set(created)


def test_settings_are_empty_until_written(dal: Dal) -> None:
    assert dal.get_settings() == {}


def test_put_settings_merges_partial_patches(dal: Dal) -> None:
    assert dal.put_settings({"defaultVoiceId": "en_US-lessac-medium"}) == {
        "defaultVoiceId": "en_US-lessac-medium"
    }

    result = dal.put_settings({"rate": 1.2, "volume": 0.8})

    assert result == {
        "defaultVoiceId": "en_US-lessac-medium",
        "rate": 1.2,
        "volume": 0.8,
    }
    assert dal.get_settings() == result

    assert dal.put_settings({"rate": 0.5}) == {
        "defaultVoiceId": "en_US-lessac-medium",
        "rate": 0.5,
        "volume": 0.8,
    }


def test_concurrent_writes_are_serialized(dal: Dal) -> None:
    created: list[str] = []
    created_lock = threading.Lock()

    def worker() -> None:
        for _ in range(5):
            generation_id = _make_generation(dal)
            with created_lock:
                created.append(generation_id)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    rows, total = dal.list(limit=100)
    assert total == 20
    assert len(created) == 20
    assert set(created) == {row["id"] for row in rows}
