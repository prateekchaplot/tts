"""Voice listing and preview endpoints (ARCHITECTURE.md section 9.2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response

from tts.api.errors import AppError
from tts.api.schemas import Voice, VoiceList, VoicePreviewRequest
from tts.config import Settings
from tts.voices import store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voices"])

NO_VOICES_MESSAGE = (
    "No voices are installed. Run `tts add-voice en_US-lessac-medium` "
    "(needs internet once), then reload."
)


def _settings(request: Request) -> Settings:
    """Initialize the voice store for this app's settings (idempotent)."""
    settings: Settings = request.app.state.settings
    store.ensure_data_dirs(settings)
    return settings


@router.get("/voices", response_model=VoiceList, summary="List installed voices")
def list_installed_voices(request: Request) -> VoiceList:
    """List local voices sorted by language then id, with the configured default."""
    settings = _settings(request)
    voices = store.list_voices()
    return VoiceList(
        items=[
            Voice(
                id=voice.id,
                name=voice.name,
                language=voice.language,
                gender=voice.gender,
                sample_rate=voice.sample_rate,
            )
            for voice in voices
        ],
        total=len(voices),
        default_voice_id=settings.default_voice_id,
    )


@router.post("/voices/preview", summary="Preview a voice")
def preview_voice(payload: VoicePreviewRequest, request: Request) -> Response:
    """Render the fixed preview phrase as WAV in the requested voice."""
    _settings(request)
    if not store.list_voices():
        raise AppError("NO_VOICES_INSTALLED", 409, NO_VOICES_MESSAGE)

    try:
        wav = store.preview_wav(payload.voice_id)
    except store.VoiceNotFoundError as error:
        raise AppError(
            "VOICE_NOT_FOUND",
            422,
            f"Voice {payload.voice_id!r} is not installed.",
        ) from error
    except Exception as error:
        logger.exception("Voice preview failed for %s", payload.voice_id)
        raise AppError(
            "ENGINE_ERROR",
            500,
            "The speech engine could not render a preview.",
        ) from error

    return Response(content=wav, media_type="audio/wav")
