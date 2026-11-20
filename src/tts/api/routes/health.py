"""Health endpoint (ARCHITECTURE.md section 9.2)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from tts import __version__
from tts.api.dependencies import get_dal
from tts.api.schemas import HealthResponse
from tts.config import Settings

router = APIRouter(tags=["health"])


def _count_installed_voices(voices_dir: Path) -> int:
    """Count voice models in the local store without loading the voice stack."""
    try:
        return sum(1 for path in voices_dir.glob("*.onnx") if path.is_file())
    except OSError:
        return 0


@router.get("/health", response_model=HealthResponse, summary="Report process health")
def get_health(request: Request) -> HealthResponse:
    """Return process health plus the voice count used by the no-voice UI."""
    settings: Settings = request.app.state.settings
    default_settings = get_dal(request).seed_settings(settings.default_voice_id)
    return HealthResponse(
        version=__version__,
        voices_installed=_count_installed_voices(settings.data_dir / "voices"),
        default_voice_id=str(default_settings["defaultVoiceId"]),
    )
