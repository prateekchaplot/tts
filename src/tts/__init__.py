"""Local TTS package."""

from .config import CONFIG_FILENAME, CONFIG_PATH, PROJECT_ROOT, load_config, save_config
from .device import _device_index, detect_device
from .models import (
    RECOMMENDED_MODELS,
    _HAS_COQUI,
    _HAS_KOKORO,
    _HAS_PIPER,
    ensure_default_model,
    list_models,
    list_voices,
)
from .synthesize import synthesize

__all__ = [
    "PROJECT_ROOT",
    "CONFIG_FILENAME",
    "CONFIG_PATH",
    "RECOMMENDED_MODELS",
    "_HAS_KOKORO",
    "_HAS_PIPER",
    "_HAS_COQUI",
    "load_config",
    "save_config",
    "detect_device",
    "_device_index",
    "ensure_default_model",
    "list_models",
    "list_voices",
    "synthesize",
]
