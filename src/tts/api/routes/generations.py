"""Generation endpoints: create, list, detail, media, SSE, cancel, delete.

Everything here is wiring and contract mapping. Synthesis, timing, and cue
logic live in ``jobs`` and its dependencies (§7.9); this module only validates
requests, maps domain errors to the §9.1 envelope, and serializes rows from the
DAL into the §9.1 schemas.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from tts.api.dependencies import get_dal, get_jobs
from tts.api.errors import AppError
from tts.api.schemas import (
    CueSchema,
    GenerationCreateRequest,
    GenerationDetail,
    GenerationError,
    GenerationList,
    GenerationState,
    GenerationStatus,
    GenerationSummary,
    SourceType,
    WordTimingSchema,
)
from tts.config import Settings
from tts.history.dal import ActiveGenerationError, Dal
from tts.jobs.manager import (
    GenerationNotCancellableError,
    GenerationNotFoundError,
    JobManager,
)
from tts.jobs.sse import RETRY_LINE, Subscriber
from tts.subtitles.srt import render_srt
from tts.subtitles.vtt import render_vtt
from tts.types import Cue
from tts.voices import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generations"])

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_NOT_FOUND_MESSAGE = "That generation does not exist."
_NOT_READY_MESSAGE = "The audio is not ready yet. Please wait for generation to finish."
_NO_VOICES_MESSAGE = (
    "No voices are installed. Run `tts add-voice en_US-lessac-medium` "
    "(needs internet once), then reload."
)
_RATE_RANGE = (0.5, 2.0)
_VOLUME_RANGE = (0.0, 1.0)
# -- app-scoped services -----------------------------------------------------


def _dal(request: Request) -> Dal:
    """Return the shared application DAL."""
    return get_dal(request)


def _jobs(request: Request) -> JobManager:
    """Return the shared application job manager."""
    return get_jobs(request)


# -- small helpers -----------------------------------------------------------


def _validate_id(generation_id: str) -> str:
    """Reject anything that is not a UUID4 before it can reach a path join."""
    if not _UUID_RE.fullmatch(str(generation_id)):
        raise AppError("GENERATION_NOT_FOUND", 404, _NOT_FOUND_MESSAGE)
    return str(generation_id)


def _row_or_404(dal: Dal, generation_id: str) -> dict[str, Any]:
    row = dal.get(generation_id)
    if row is None:
        raise AppError("GENERATION_NOT_FOUND", 404, _NOT_FOUND_MESSAGE)
    return row


def _ready_row(dal: Dal, generation_id: str) -> dict[str, Any]:
    row = _row_or_404(dal, generation_id)
    if row["status"] != "succeeded":
        raise AppError("GENERATION_NOT_READY", 409, _NOT_READY_MESSAGE)
    return row


def _json_list(value: object) -> list[dict[str, Any]]:
    """Decode a JSON column, degrading to an empty list rather than failing."""
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        logger.warning("Ignoring malformed generation JSON column")
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _error_info(row: dict[str, Any]) -> GenerationError | None:
    code = row["error_code"]
    if not code:
        return None
    return GenerationError(code=str(code), message=str(row["error_message"] or ""))


def _summary(row: dict[str, Any]) -> GenerationSummary:
    """Map a stored row to the camelCase GenerationSummary contract."""
    return GenerationSummary(
        generation_id=str(row["id"]),
        status=cast(GenerationState, str(row["status"])),
        created_at=str(row["created_at"]),
        source_type=cast(SourceType, str(row["source_type"])),
        input_preview=str(row["input_text"] or "")[:120],
        input_filename=row["input_filename"],
        voice_id=str(row["voice_id"]),
        voice_name=str(row["voice_name"]),
        rate=float(row["rate"]),
        volume=float(row["volume"]),
        duration_seconds=row["duration_seconds"],
        error=_error_info(row),
    )


def _detail(row: dict[str, Any]) -> GenerationDetail:
    """Map a stored row to GenerationDetail; pending values stay null."""
    detail = GenerationDetail(**_summary(row).model_dump())
    if row["status"] not in ("queued", "running", "cancelling"):
        detail.text = str(row["input_text"] or "")
    if row["status"] == "succeeded":
        detail.sample_rate = row["sample_rate"]
        detail.aligned_word_ratio = row["aligned_word_ratio"]
        detail.word_timings = [
            WordTimingSchema(
                text=str(word.get("text", "")),
                start_ms=int(word.get("startMs", 0)),
                end_ms=int(word.get("endMs", 0)),
                aligned=bool(word.get("aligned", False)),
            )
            for word in _json_list(row["word_timings_json"])
        ]
        detail.cues = [
            CueSchema(
                index=int(cue.get("index", 0)),
                start_ms=int(cue.get("startMs", 0)),
                end_ms=int(cue.get("endMs", 0)),
                text=str(cue.get("text", "")),
            )
            for cue in _json_list(row["cues_json"])
        ]
    return detail


def _download_stem(row: dict[str, Any]) -> str:
    """Build the §9.2 ``{slug}_{timestamp}`` download name."""
    words = re.findall(r"[A-Za-z0-9]+", str(row["input_text"] or ""))[:6]
    slug = re.sub(r"[^a-z0-9-]", "", "-".join(words).lower()).strip("-") or "speech"
    try:
        created = datetime.fromisoformat(str(row["created_at"]))
    except ValueError:
        created = datetime.now(UTC)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    stamp = created.astimezone(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{slug}_{stamp}"


def _download_headers(row: dict[str, Any], suffix: str) -> dict[str, str]:
    name = f"{_download_stem(row)}.{suffix}"
    return {"Content-Disposition": f'attachment; filename="{name}"'}


def _audio_path(row: dict[str, Any], settings: Settings) -> Path:
    """Resolve a stored audio path, refusing anything outside the generations dir."""
    value = row["audio_path"]
    if not value:
        raise AppError("GENERATION_NOT_READY", 409, _NOT_READY_MESSAGE)
    generations_dir = (settings.data_dir / "generations").resolve()
    try:
        path = Path(str(value)).resolve()
    except OSError as error:
        raise AppError("GENERATION_NOT_READY", 409, _NOT_READY_MESSAGE) from error
    if not path.is_relative_to(generations_dir) or not path.is_file():
        raise AppError("GENERATION_NOT_READY", 409, _NOT_READY_MESSAGE)
    return path


def _cue_objects(row: dict[str, Any]) -> list[Cue]:
    return [
        Cue(
            index=int(cue.get("index", 0)),
            start_ms=int(cue.get("startMs", 0)),
            end_ms=int(cue.get("endMs", 0)),
            text=str(cue.get("text", "")),
        )
        for cue in _json_list(row["cues_json"])
    ]


def _stream(subscriber: Subscriber) -> Iterator[str]:
    """Send the reconnect hint, then named SSE frames until the terminal event."""
    yield RETRY_LINE
    for event in subscriber.events():
        if event is None:
            return
        yield event.to_wire()
        if event.terminal:
            return


def _settings_defaults(dal: Dal, settings: Settings) -> dict[str, Any]:
    """Seed and read §8.2 settings so omitted request fields get stored defaults."""
    dal.seed_settings(settings.default_voice_id)
    values = dal.get_settings()
    return {
        "defaultVoiceId": str(values.get("defaultVoiceId", settings.default_voice_id)),
        "rate": float(values.get("rate", 1.0)),
        "volume": float(values.get("volume", 1.0)),
    }


def _range_check(field: str, value: float, bounds: tuple[float, float]) -> None:
    low, high = bounds
    if not low <= value <= high:
        raise AppError(
            "OUT_OF_RANGE",
            422,
            f"{field} must be between {low} and {high}.",
            {"field": field, "min": low, "max": high, "value": value},
        )


# -- routes ------------------------------------------------------------------


@router.post(
    "/generations", status_code=202, response_model=GenerationStatus, summary="Queue a generation"
)
def create_generation(payload: GenerationCreateRequest, request: Request) -> GenerationStatus:
    """Validate the request, then hand it to the single-worker job manager."""
    settings: Settings = request.app.state.settings
    store.ensure_data_dirs(settings)

    text = payload.text
    if text is None or not text.strip():
        raise AppError(
            "EMPTY_INPUT",
            422,
            "Please type or upload some text before generating.",
        )
    if len(text) > settings.max_input_chars:
        raise AppError(
            "INPUT_TOO_LONG",
            422,
            f"Input is {len(text):,} characters; the limit is {settings.max_input_chars:,}.",
            {"maxChars": settings.max_input_chars, "receivedChars": len(text)},
        )

    # T1.6 contract: an empty store wins over an unknown voice so the UI can
    # show the no-voice remedy (§10.4).
    voices = store.list_voices()
    if not voices:
        raise AppError("NO_VOICES_INSTALLED", 409, _NO_VOICES_MESSAGE)

    defaults = _settings_defaults(_dal(request), settings)
    voice_id = payload.voice_id if payload.voice_id is not None else defaults["defaultVoiceId"]
    if voice_id not in {voice.id for voice in voices}:
        raise AppError("VOICE_NOT_FOUND", 422, f"Voice {voice_id!r} is not installed.")

    rate = payload.rate if payload.rate is not None else defaults["rate"]
    volume = payload.volume if payload.volume is not None else defaults["volume"]
    _range_check("rate", rate, _RATE_RANGE)
    _range_check("volume", volume, _VOLUME_RANGE)

    try:
        generation_id = _jobs(request).submit(
            voice_id=voice_id,
            text=text,
            source_type="text",
            rate=rate,
            volume=volume,
        )
    except store.VoiceNotFoundError as error:
        raise AppError("VOICE_NOT_FOUND", 422, f"Voice {voice_id!r} is not installed.") from error
    except Exception as error:
        logger.exception("Could not queue generation")
        raise AppError("INTERNAL_ERROR", 500, "The generation could not be started.") from error

    return GenerationStatus(generation_id=generation_id, status="queued")


@router.get("/generations", response_model=GenerationList, summary="List generation history")
def list_generations(
    request: Request,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenerationList:
    """Return newest-first summaries with a stable total count."""
    settings: Settings = request.app.state.settings
    effective_limit = min(limit or settings.history_limit, 100)
    rows, total = _dal(request).list(limit=effective_limit, offset=offset)
    return GenerationList(items=[_summary(row) for row in rows], total=total)


@router.get(
    "/generations/{generation_id}", response_model=GenerationDetail, summary="Get generation detail"
)
def get_generation(generation_id: str, request: Request) -> GenerationDetail:
    """Return the full record; result fields stay null until success."""
    row = _row_or_404(_dal(request), _validate_id(generation_id))
    return _detail(row)


@router.get("/generations/{generation_id}/audio", summary="Download generated audio")
def get_audio(generation_id: str, request: Request) -> FileResponse:
    """Serve the completed WAV with the §9.2 attachment name."""
    settings: Settings = request.app.state.settings
    row = _ready_row(_dal(request), _validate_id(generation_id))
    path = _audio_path(row, settings)
    return FileResponse(
        path,
        media_type="audio/wav",
        headers=_download_headers(row, "wav"),
    )


@router.get("/generations/{generation_id}/subtitles", summary="Download subtitles")
def get_subtitles(
    generation_id: str,
    request: Request,
    format: Annotated[str | None, Query()] = None,
) -> PlainTextResponse:
    """Render completed cues as SRT or WebVTT."""
    row = _ready_row(_dal(request), _validate_id(generation_id))
    if format == "srt":
        body = render_srt(_cue_objects(row))
    elif format == "vtt":
        body = render_vtt(_cue_objects(row))
    else:
        raise AppError(
            "SUBTITLE_FORMAT_UNKNOWN",
            400,
            "Unknown subtitle format; accepted values are srt and vtt.",
        )
    return PlainTextResponse(body, headers=_download_headers(row, format))


@router.get("/generations/{generation_id}/events", summary="Stream generation events")
def generation_events(generation_id: str, request: Request) -> StreamingResponse:
    """Expose the manager's event queue as an SSE stream with reconnect replay."""
    generation_id = _validate_id(generation_id)
    try:
        subscriber = _jobs(request).subscribe(generation_id)
    except GenerationNotFoundError as error:
        raise AppError("GENERATION_NOT_FOUND", 404, _NOT_FOUND_MESSAGE) from error
    return StreamingResponse(
        _stream(subscriber),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/generations/{generation_id}/cancel",
    response_model=GenerationStatus,
    summary="Cancel a generation",
)
def cancel_generation(generation_id: str, request: Request) -> GenerationStatus:
    """Cancel a queued or running job; an already-cancelling job answers cancelled."""
    generation_id = _validate_id(generation_id)
    row = _row_or_404(_dal(request), generation_id)
    status = str(row["status"])
    if status in ("succeeded", "failed", "cancelled"):
        raise AppError("GENERATION_BUSY", 409, "This generation has already finished.")

    if status == "cancelling":
        # §9.2 pins the answer for an already-cancelling job, while jobs.cancel
        # truthfully keeps reporting "cancelling" until the worker confirms.
        return GenerationStatus(generation_id=generation_id, status="cancelled")

    try:
        result = _jobs(request).cancel(generation_id)
    except GenerationNotFoundError as error:
        raise AppError("GENERATION_NOT_FOUND", 404, _NOT_FOUND_MESSAGE) from error
    except GenerationNotCancellableError as error:
        raise AppError("GENERATION_BUSY", 409, "This generation has already finished.") from error
    return GenerationStatus(generation_id=generation_id, status=result)


@router.delete("/generations/{generation_id}", status_code=204, summary="Delete a generation")
def delete_generation(generation_id: str, request: Request) -> Response:
    """Delete a finished generation's row and WAV atomically (§8.5)."""
    generation_id = _validate_id(generation_id)
    dal = _dal(request)
    _row_or_404(dal, generation_id)
    try:
        deleted = dal.delete(generation_id)
    except ActiveGenerationError as error:
        raise AppError(
            "GENERATION_BUSY",
            409,
            "Please cancel this generation before deleting it.",
        ) from error
    if not deleted:
        raise AppError("GENERATION_NOT_FOUND", 404, _NOT_FOUND_MESSAGE)
    return Response(status_code=204)
