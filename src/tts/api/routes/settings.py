"""Persisted speech settings endpoints (ARCHITECTURE.md section 9.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from tts.api.dependencies import get_dal
from tts.api.errors import AppError
from tts.api.schemas import SettingsPatch, SettingsResponse
from tts.config import Settings
from tts.voices import store

router = APIRouter(tags=["settings"])

_RATE_RANGE = (0.5, 2.0)
_VOLUME_RANGE = (0.0, 1.0)


def _current_settings(request: Request) -> dict[str, Any]:
    """Seed and return the complete settings object, preserving stored values."""
    settings: Settings = request.app.state.settings
    store.ensure_data_dirs(settings)
    return get_dal(request).seed_settings(settings.default_voice_id)


def _response(values: dict[str, Any]) -> SettingsResponse:
    return SettingsResponse(
        default_voice_id=str(values["defaultVoiceId"]),
        rate=float(values["rate"]),
        volume=float(values["volume"]),
    )


@router.get("/settings", response_model=SettingsResponse, summary="Read speech settings")
def read_settings(request: Request) -> SettingsResponse:
    """Return persisted settings, seeding defaults on first read."""
    return _response(_current_settings(request))


@router.put("/settings", response_model=SettingsResponse, summary="Update speech settings")
def update_settings(payload: SettingsPatch, request: Request) -> SettingsResponse:
    """Validate and persist only the settings fields supplied by the caller."""
    settings: Settings = request.app.state.settings
    store.ensure_data_dirs(settings)
    patch: dict[str, str | float | None] = payload.model_dump(
        by_alias=True,
        exclude_unset=True,
    )

    for field, value in patch.items():
        if value is None:
            raise AppError(
                "OUT_OF_RANGE",
                422,
                f"{field} cannot be null.",
                {"field": field, "reason": "a value is required"},
            )

    if "defaultVoiceId" in patch:
        voice_id = str(patch["defaultVoiceId"])
        if voice_id not in {voice.id for voice in store.list_voices()}:
            raise AppError(
                "VOICE_NOT_FOUND",
                422,
                f"Voice {voice_id!r} is not installed.",
            )

    for field, limits in (("rate", _RATE_RANGE), ("volume", _VOLUME_RANGE)):
        if field not in patch:
            continue
        raw_value = payload.rate if field == "rate" else payload.volume
        assert raw_value is not None
        value = float(raw_value)
        minimum, maximum = limits
        if not minimum <= value <= maximum:
            label = "Rate" if field == "rate" else "Volume"
            raise AppError(
                "OUT_OF_RANGE",
                422,
                f"{label} must be between {minimum} and {maximum}.",
                {"field": field, "min": minimum, "max": maximum, "value": value},
            )
        patch[field] = value

    dal = get_dal(request)
    dal.seed_settings(settings.default_voice_id)
    return _response(dal.put_settings(patch))
