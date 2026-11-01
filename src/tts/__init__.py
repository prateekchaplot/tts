"""Local TTS package."""

from .config import CONFIG_FILENAME, CONFIG_PATH, PROJECT_ROOT, load_config, save_config
from .device import _device_index, detect_device, torch_device_name
from .models import (
    RECOMMENDED_MODELS,
    _HAS_COQUI,
    _HAS_KOKORO,
    _HAS_PIPER,
    ensure_default_model,
    list_models,
    list_recommended,
    list_recommended_models,
    list_voices,
)
from .synthesize import synthesize

# Optional UI layer (gradio). Imported lazily so the core package stays importable
# even when gradio is not installed.
try:
    from .ui import (
        available_models,
        build_app,
        build_interface,
        build_ui,
        create_app,
        create_interface,
        create_ui,
        generate,
        launch,
        launch_app,
        launch_ui,
        refresh_voices,
        run,
        run_app,
        run_ui,
        serve,
        start,
        start_app,
        start_ui,
    )
except Exception:
    available_models = None  # type: ignore[assignment]
    build_app = None  # type: ignore[assignment]
    build_interface = None  # type: ignore[assignment]
    build_ui = None  # type: ignore[assignment]
    create_app = None  # type: ignore[assignment]
    create_interface = None  # type: ignore[assignment]
    create_ui = None  # type: ignore[assignment]
    generate = None  # type: ignore[assignment]
    launch = None  # type: ignore[assignment]
    launch_app = None  # type: ignore[assignment]
    launch_ui = None  # type: ignore[assignment]
    refresh_voices = None  # type: ignore[assignment]
    run = None  # type: ignore[assignment]
    run_app = None  # type: ignore[assignment]
    run_ui = None  # type: ignore[assignment]
    serve = None  # type: ignore[assignment]
    start = None  # type: ignore[assignment]
    start_app = None  # type: ignore[assignment]
    start_ui = None  # type: ignore[assignment]

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
    "torch_device_name",
    "ensure_default_model",
    "list_models",
    "list_recommended",
    "list_recommended_models",
    "list_voices",
    "synthesize",
    "available_models",
    "build_app",
    "build_ui",
    "build_interface",
    "create_app",
    "create_ui",
    "create_interface",
    "generate",
    "launch",
    "launch_ui",
    "launch_app",
    "refresh_voices",
    "run",
    "run_ui",
    "run_app",
    "serve",
    "start",
    "start_ui",
    "start_app",
]
