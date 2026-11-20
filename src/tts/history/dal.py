"""SQLite data access layer for generation records and app settings."""

from __future__ import annotations

import builtins
import json
import logging
import shutil
import sqlite3
import threading
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
"""Current schema version stored in ``PRAGMA user_version``."""

HISTORY_LIMIT_DEFAULT = 20
"""Fallback row budget used when the caller does not pass ``history_limit``."""

DEFAULT_RATE = 1.0
"""Default speaking rate seeded into ``app_settings`` (§8.2)."""

DEFAULT_VOLUME = 1.0
"""Default volume seeded into ``app_settings`` (§8.2)."""

_ACTIVE_STATUSES = frozenset({"queued", "running", "cancelling"})
"""Generation statuses that are still in flight and must never be deleted."""

_SETTINGS_KEYS = frozenset({"defaultVoiceId", "rate", "volume"})
"""The only ``app_settings`` keys the schema allows (§8.2)."""


class ActiveGenerationError(RuntimeError):
    """Raised when a delete targets a generation that is still in flight.

    ARCHITECTURE §7.7 forbids the DAL from deleting a row whose id is active
    (``queued``/``running``/``cancelling``). The API layer maps this to the
    ``GENERATION_BUSY`` 409 response (§9.2).
    """

    def __init__(self, generation_id: str) -> None:
        super().__init__(f"generation {generation_id} is active and cannot be deleted")
        self.generation_id = generation_id


_RESULT_FIELDS = frozenset(
    {
        "duration_seconds",
        "sample_rate",
        "audio_path",
        "word_timings_json",
        "cues_json",
        "aligned_word_ratio",
        "error_code",
        "error_message",
    }
)
"""Columns that may be supplied as ``**result_fields`` to ``set_status``."""

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
_MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def _utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string with microsecond precision."""
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _parse_timestamp(value: str) -> datetime | None:
    """Parse a stored ``created_at`` value, tolerating a malformed one."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _remove_file(path: str | None) -> bool:
    """Delete an audio file, tolerating a file that is already gone.

    Returns ``True`` when the file is gone afterwards and ``False`` when the
    operating system refused the removal (for example a Windows file lock).
    """
    if not path:
        return True
    try:
        Path(path).unlink()
    except FileNotFoundError:
        logger.debug("Audio file already missing: %s", path)
        return True
    except OSError:
        return False
    return True


class Dal:
    """Owns the SQLite database: generation records, settings, and bounded eviction."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        history_limit: int = HISTORY_LIMIT_DEFAULT,
    ) -> None:
        if history_limit < 0:
            raise ValueError(f"history_limit must be >= 0, got {history_limit}")
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._data_dir / "library.db"
        self._history_limit = history_limit
        self._lock = threading.RLock()
        self._pending_removals: set[str] = set()
        self._last_created_at: datetime | None = None
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._migrate()
            self._last_created_at = self._latest_created_at()

    def close(self) -> None:
        """Close the underlying database connection."""
        with self._lock:
            self._flush_pending_removals()
            self._conn.close()

    # -- schema ---------------------------------------------------------------

    def _migrate(self) -> None:
        """Apply the v1 schema on first run, then any newer numbered migrations."""
        version = self._user_version()
        if version < 1:
            self._apply_script(_SCHEMA_PATH.read_text(encoding="utf-8"), SCHEMA_VERSION)
            version = SCHEMA_VERSION
            logger.info("Initialized library database at %s (schema v1)", self._db_path)

        for migration in sorted(_MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql")):
            target = int(migration.name[:3])
            if target <= version:
                continue
            self._backup_database()
            self._apply_script(migration.read_text(encoding="utf-8"), target)
            version = target
            logger.info("Applied database migration %s (schema v%d)", migration.name, version)

    def _user_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def _latest_created_at(self) -> datetime | None:
        """Return the newest stored ``created_at``, so a restart keeps ordering."""
        row = self._conn.execute(
            "SELECT created_at FROM generations ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return _parse_timestamp(row["created_at"])

    def _next_created_at(self) -> str:
        """Return a timestamp strictly greater than every timestamp before it.

        The system clock is too coarse to order rapid inserts (thousands of
        calls can share a single tick), so the clock value is nudged forward
        when it would repeat or move backwards. History order (newest first)
        and eviction order (oldest first) then follow insertion order instead
        of an arbitrary id tiebreaker (§8.5).
        """
        now = _parse_timestamp(_utc_now()) or datetime.now(UTC)
        if self._last_created_at is not None and now <= self._last_created_at:
            now = self._last_created_at + timedelta(microseconds=1)
        self._last_created_at = now
        return now.isoformat(timespec="microseconds")

    def _apply_script(self, sql: str, version: int) -> None:
        # executescript() commits any open transaction first, so the migration
        # supplies its own so a failure rolls back cleanly.
        self._conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")

    def _backup_database(self) -> None:
        backup_path = self._db_path.with_name("library.db.bak")
        self._conn.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(self._db_path, backup_path)
        logger.info("Backed up database to %s before migration", backup_path)

    # -- generations ----------------------------------------------------------

    def create_generation(
        self,
        *,
        text: str,
        voice_id: str,
        voice_name: str,
        source_type: str = "text",
        input_filename: str | None = None,
        rate: float = 1.0,
        volume: float = 1.0,
    ) -> str:
        """Insert a ``queued`` generation row and return its UUID4 id."""
        generation_id = str(uuid.uuid4())
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO generations (
                    id, created_at, status, source_type, input_text, input_filename,
                    voice_id, voice_name, rate, volume
                ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    generation_id,
                    self._next_created_at(),
                    source_type,
                    text,
                    input_filename,
                    voice_id,
                    voice_name,
                    rate,
                    volume,
                ),
            )
        return generation_id

    def set_status(
        self,
        generation_id: str,
        status: str,
        error: Mapping[str, str] | None = None,
        **result_fields: Any,
    ) -> None:
        """Update a generation's status, error pair, and result columns.

        Raises ``KeyError`` when the id does not exist and ``ValueError`` for an
        unknown result field.
        """
        updates: dict[str, Any] = {"status": status}
        if error is not None:
            missing = {"code", "message"} - set(error)
            if missing:
                raise ValueError(f"error is missing keys: {', '.join(sorted(missing))}")
            updates["error_code"] = error["code"]
            updates["error_message"] = error["message"]
        for name, value in result_fields.items():
            if name not in _RESULT_FIELDS:
                raise ValueError(f"unknown generation result field: {name}")
            updates[name] = value

        assignments = ", ".join(f"{name} = ?" for name in updates)
        with self._lock, self._conn:
            cursor = self._conn.execute(
                f"UPDATE generations SET {assignments} WHERE id = ?",
                (*updates.values(), generation_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(generation_id)

    def get(self, generation_id: str) -> dict[str, Any] | None:
        """Return one generation row as a dict, or ``None`` when it does not exist.

        JSON columns are returned as their stored strings; the API layer owns
        camelCase serialization and JSON decoding.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM generations WHERE id = ?", (generation_id,)
            ).fetchone()
        return dict(row) if row is not None else None

    def list(self, limit: int = 50, offset: int = 0) -> tuple[builtins.list[dict[str, Any]], int]:
        """Return ``(rows, total)`` newest first, plus the unpaged row count."""
        with self._lock:
            total = int(self._conn.execute("SELECT COUNT(*) FROM generations").fetchone()[0])
            rows = self._conn.execute(
                """
                SELECT * FROM generations
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows], total

    def delete(self, generation_id: str) -> bool:
        """Delete a generation row and its audio file inside one critical section.

        Returns ``False`` when the row does not exist. Raises
        ``ActiveGenerationError`` when the generation is still in flight; the
        DAL never deletes an active row (§7.7).

        The row is removed before its file so that a failure between the two
        steps can never leave a row that references a missing audio file
        (§7.7). A file the operating system refuses to remove is remembered and
        retried on the next delete, eviction, or close.
        """
        with self._lock:
            self._flush_pending_removals()
            found, audio_path = self._delete_row(generation_id)
            if not found:
                return False
            self._remove_audio(audio_path)
            return True

    def _delete_row(self, generation_id: str) -> tuple[bool, str | None]:
        """Delete one row inside a transaction; return ``(found, audio_path)``.

        Raises ``ActiveGenerationError`` when the row is still active, leaving
        the row and its file untouched.
        """
        with self._conn:
            row = self._conn.execute(
                "SELECT status, audio_path FROM generations WHERE id = ?", (generation_id,)
            ).fetchone()
            if row is None:
                return False, None
            if row["status"] in _ACTIVE_STATUSES:
                raise ActiveGenerationError(generation_id)
            self._conn.execute("DELETE FROM generations WHERE id = ?", (generation_id,))
        return True, row["audio_path"]

    def _remove_audio(self, path: str | None) -> None:
        """Remove an audio file, deferring the removal when the OS refuses."""
        if not path:
            return
        if _remove_file(path):
            self._pending_removals.discard(path)
            return
        self._pending_removals.add(path)
        logger.warning("Could not remove audio file %s; removal deferred", path)

    def _flush_pending_removals(self) -> None:
        """Retry removals deferred by an earlier operating-system refusal."""
        if not self._pending_removals:
            return
        for path in sorted(self._pending_removals):
            if _remove_file(path):
                self._pending_removals.discard(path)
        if self._pending_removals:
            logger.warning("%d audio file(s) still pending removal", len(self._pending_removals))

    def evict_to_limit(self, active_ids: set[str] | None = None) -> builtins.list[str]:
        """Delete oldest rows beyond ``history_limit`` and return their ids.

        Ids in ``active_ids`` are never evicted; the row count may therefore
        stay above the limit while they are active. The caller owns the
        active set and must pass every in-flight id, not just the new one
        (§8.5).
        """
        active = active_ids or set()
        deleted: list[str] = []
        with self._lock:
            self._flush_pending_removals()
            rows = self._conn.execute(
                "SELECT id, audio_path FROM generations ORDER BY created_at ASC, id ASC"
            ).fetchall()
            victims = []
            for row in rows:
                if len(rows) - len(deleted) <= self._history_limit:
                    break
                if row["id"] in active:
                    continue
                victims.append(row)
                deleted.append(row["id"])
            if victims:
                with self._conn:
                    self._conn.executemany(
                        "DELETE FROM generations WHERE id = ?",
                        [(victim["id"],) for victim in victims],
                    )
                for victim in victims:
                    self._remove_audio(victim["audio_path"])
        if deleted:
            logger.warning("Evicted %d generation(s): %s", len(deleted), ", ".join(deleted))
        return deleted

    # -- settings -------------------------------------------------------------

    def get_settings(self) -> dict[str, Any]:
        """Return persisted settings as a dict (empty until something is stored).

        Keys outside the §8.2 set and malformed values are ignored so the API
        always sees the documented shape.
        """
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM app_settings").fetchall()
        settings: dict[str, Any] = {}
        for row in rows:
            if row["key"] not in _SETTINGS_KEYS:
                logger.warning("Ignoring unknown app_settings key %r", row["key"])
                continue
            try:
                settings[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                logger.warning("Ignoring malformed app_settings value for %r", row["key"])
        return settings

    def put_settings(self, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Upsert a settings patch and return the full persisted settings dict.

        Only the three keys defined in §8.2 are accepted; an unknown key
        raises ``ValueError``.
        """
        unknown = set(patch) - _SETTINGS_KEYS
        if unknown:
            raise ValueError(f"unknown settings key(s): {', '.join(sorted(unknown))}")
        with self._lock, self._conn:
            for key, value in patch.items():
                self._conn.execute(
                    """
                    INSERT INTO app_settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, json.dumps(value)),
                )
        return self.get_settings()

    def seed_settings(self, default_voice_id: str) -> dict[str, Any]:
        """Write the §8.2 defaults for every key that is not stored yet.

        The DAL cannot discover voices — §7.7 limits it to ``config`` and
        stdlib ``sqlite3`` — so the caller supplies the default voice id.
        Stored values are never overwritten.
        """
        defaults: dict[str, Any] = {
            "defaultVoiceId": default_voice_id,
            "rate": DEFAULT_RATE,
            "volume": DEFAULT_VOLUME,
        }
        stored = self.get_settings()
        missing = {key: value for key, value in defaults.items() if key not in stored}
        if missing:
            self.put_settings(missing)
        return self.get_settings()
