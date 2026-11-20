"""NFR-05 consistency property tests for the history data access layer.

These tests pin the invariant from ARCHITECTURE §7.7: the DAL never leaves a
row referencing a missing audio file, and a forced failure between the row
delete and the file delete always leaves a recoverable state.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tts.history import dal as dal_module
from tts.history.dal import ActiveGenerationError, Dal

_BLOCK_DELETE_TRIGGER = """
CREATE TRIGGER block_generation_delete BEFORE DELETE ON generations
BEGIN
    SELECT RAISE(ABORT, 'forced delete failure');
END;
"""


class _Clock:
    """Deterministic clock so ordering assertions never depend on wall time."""

    def __init__(self) -> None:
        self._next = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    def __call__(self) -> str:
        value = self._next.isoformat(timespec="microseconds")
        self._next += timedelta(seconds=1)
        return value


@pytest.fixture
def dal(tmp_path: Path) -> Iterator[Dal]:
    instance = Dal(tmp_path)
    try:
        yield instance
    finally:
        instance.close()


def _make_generation(instance: Dal, audio_path: Path | None = None, **overrides: object) -> str:
    values: dict[str, object] = {
        "text": "Hello world.",
        "voice_id": "en_US-lessac-medium",
        "voice_name": "Lessac",
    }
    values.update(overrides)
    generation_id = instance.create_generation(**values)  # type: ignore[arg-type]
    if audio_path is not None:
        audio_path.write_bytes(b"RIFF")
        instance.set_status(generation_id, "succeeded", audio_path=str(audio_path))
    return generation_id


def _assert_no_dangling_rows(instance: Dal) -> None:
    """Every surviving row must still point at an audio file that exists."""
    rows, _ = instance.list(limit=1000)
    for row in rows:
        audio_path = row["audio_path"]
        if audio_path is None:
            continue
        assert Path(audio_path).exists(), f"row {row['id']} references a missing audio file"


# -- delete: atomicity between the row and its file ---------------------------


def test_row_delete_failure_keeps_row_and_audio_file_consistent(dal: Dal, tmp_path: Path) -> None:
    """A failure while deleting the row must not orphan the row's audio file."""
    audio_path = tmp_path / "audio.wav"
    generation_id = _make_generation(dal, audio_path)
    dal._conn.execute(_BLOCK_DELETE_TRIGGER)

    with pytest.raises(sqlite3.IntegrityError):
        dal.delete(generation_id)

    row = dal.get(generation_id)
    assert row is not None, "the row must survive a failed delete"
    assert audio_path.exists(), "the row's audio file must survive a failed delete"
    _assert_no_dangling_rows(dal)


def test_failed_delete_can_be_retried_after_the_obstacle_clears(dal: Dal, tmp_path: Path) -> None:
    """The delete is idempotent on retry: the retry removes row and file."""
    audio_path = tmp_path / "audio.wav"
    generation_id = _make_generation(dal, audio_path)
    dal._conn.execute(_BLOCK_DELETE_TRIGGER)

    with pytest.raises(sqlite3.IntegrityError):
        dal.delete(generation_id)

    dal._conn.execute("DROP TRIGGER block_generation_delete")

    assert dal.delete(generation_id) is True
    assert dal.get(generation_id) is None
    assert not audio_path.exists()
    assert dal.delete(generation_id) is False


def test_file_delete_failure_leaves_no_dangling_row(
    dal: Dal, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the OS refuses the file removal the row is already gone."""
    audio_path = tmp_path / "audio.wav"
    generation_id = _make_generation(dal, audio_path)
    real_remove = dal_module._remove_file
    monkeypatch.setattr(dal_module, "_remove_file", lambda path: False)

    assert dal.delete(generation_id) is True

    assert dal.get(generation_id) is None
    assert audio_path.exists(), "the file removal is deferred, not lost"
    _assert_no_dangling_rows(dal)

    monkeypatch.setattr(dal_module, "_remove_file", real_remove)
    other_id = _make_generation(dal)
    dal.set_status(other_id, "succeeded")
    assert dal.delete(other_id) is True
    assert not audio_path.exists(), "the deferred removal must be retried"


def test_deferred_file_removal_is_flushed_on_close(
    dal: Dal, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deferred removal is retried when the DAL shuts down."""
    audio_path = tmp_path / "audio.wav"
    generation_id = _make_generation(dal, audio_path)
    real_remove = dal_module._remove_file
    monkeypatch.setattr(dal_module, "_remove_file", lambda path: False)

    assert dal.delete(generation_id) is True
    assert audio_path.exists()

    monkeypatch.setattr(dal_module, "_remove_file", real_remove)
    dal.close()
    assert not audio_path.exists()


# -- delete: active rows -------------------------------------------------------


@pytest.mark.parametrize("status", ["queued", "running", "cancelling"])
def test_delete_refuses_active_generation(dal: Dal, tmp_path: Path, status: str) -> None:
    """§7.7: the DAL never deletes a row that is still in flight."""
    audio_path = tmp_path / "audio.wav"
    generation_id = _make_generation(dal, audio_path)
    dal.set_status(generation_id, status)

    with pytest.raises(ActiveGenerationError):
        dal.delete(generation_id)

    assert dal.get(generation_id) is not None
    assert audio_path.exists()
    _assert_no_dangling_rows(dal)


def test_active_generation_error_carries_the_generation_id(dal: Dal) -> None:
    generation_id = _make_generation(dal)

    with pytest.raises(ActiveGenerationError) as excinfo:
        dal.delete(generation_id)

    assert excinfo.value.generation_id == generation_id


# -- eviction ------------------------------------------------------------------


def test_eviction_leaves_no_dangling_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every evicted row's file is gone and every survivor keeps its file."""
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    instance = Dal(tmp_path, history_limit=2)
    try:
        created: list[tuple[str, Path]] = []
        for _ in range(5):
            audio_path = tmp_path / f"{len(created)}.wav"
            generation_id = _make_generation(instance, audio_path)
            created.append((generation_id, audio_path))

        deleted = instance.evict_to_limit()

        assert deleted == [generation_id for generation_id, _ in created[:3]]
        for _, audio_path in created[:3]:
            assert not audio_path.exists()
        for _, audio_path in created[3:]:
            assert audio_path.exists()
        _assert_no_dangling_rows(instance)
    finally:
        instance.close()


def test_eviction_does_not_touch_active_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller owns the active set; a protected id keeps its file."""
    monkeypatch.setattr(dal_module, "_utc_now", _Clock())
    instance = Dal(tmp_path, history_limit=1)
    try:
        protected_audio = tmp_path / "protected.wav"
        protected_id = _make_generation(instance, protected_audio)
        other_audio = tmp_path / "other.wav"
        other_id = _make_generation(instance, other_audio)

        deleted = instance.evict_to_limit({protected_id})

        assert deleted == [other_id]
        assert protected_audio.exists()
        assert not other_audio.exists()
        _assert_no_dangling_rows(instance)
    finally:
        instance.close()


# -- concurrency ---------------------------------------------------------------


def test_concurrent_deletes_and_eviction_leave_no_dangling_rows(tmp_path: Path) -> None:
    """Parallel delete and eviction keep the row/file invariant intact."""
    instance = Dal(tmp_path, history_limit=5)
    try:
        created: list[tuple[str, Path]] = []
        for index in range(20):
            audio_path = tmp_path / f"{index}.wav"
            created.append((_make_generation(instance, audio_path), audio_path))

        barrier = threading.Barrier(4)

        def deleter(ids: list[str]) -> None:
            barrier.wait()
            for generation_id in ids:
                try:
                    instance.delete(generation_id)
                except ActiveGenerationError:
                    pass

        def evictor() -> None:
            barrier.wait()
            instance.evict_to_limit()

        threads = [
            threading.Thread(target=deleter, args=([id for id, _ in created[:5]],)),
            threading.Thread(target=deleter, args=([id for id, _ in created[5:10]],)),
            threading.Thread(target=deleter, args=([id for id, _ in created[10:15]],)),
            threading.Thread(target=evictor),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        _assert_no_dangling_rows(instance)
        rows, _ = instance.list(limit=1000)
        assert len(rows) <= len(created)
    finally:
        instance.close()


# -- ordering -------------------------------------------------------------------


def test_rapid_inserts_keep_insertion_order(tmp_path: Path) -> None:
    """The system clock is too coarse to order rapid inserts on its own."""
    instance = Dal(tmp_path)
    try:
        created = [_make_generation(instance) for _ in range(50)]

        rows, total = instance.list(limit=100)
        assert total == 50
        assert [row["id"] for row in rows] == list(reversed(created))
    finally:
        instance.close()


def test_insert_order_survives_a_restart(tmp_path: Path) -> None:
    """A reopened DAL keeps emitting timestamps after the stored rows."""
    first = Dal(tmp_path)
    try:
        created = [_make_generation(first) for _ in range(3)]
    finally:
        first.close()

    second = Dal(tmp_path)
    try:
        newest = _make_generation(second)
        rows, _ = second.list(limit=100)
        assert [row["id"] for row in rows] == [newest, *reversed(created)]
    finally:
        second.close()


# -- settings ------------------------------------------------------------------


def test_put_settings_rejects_unknown_keys(dal: Dal) -> None:
    with pytest.raises(ValueError, match="unknown settings key"):
        dal.put_settings({"pitch": 1.0})

    assert dal.get_settings() == {}


def test_get_settings_ignores_unknown_stored_keys(dal: Dal) -> None:
    dal._conn.execute("INSERT INTO app_settings (key, value) VALUES ('pitch', '1.0')")

    assert dal.get_settings() == {}


def test_seed_settings_writes_defaults_without_overwriting(dal: Dal) -> None:
    dal.put_settings({"rate": 1.5})

    seeded = dal.seed_settings("en_US-lessac-medium")

    assert seeded == {
        "defaultVoiceId": "en_US-lessac-medium",
        "rate": 1.5,
        "volume": 1.0,
    }
    assert dal.seed_settings("de_DE-thorsten-medium") == seeded
