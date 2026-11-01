"""Local TTS package."""

from .config import CONFIG_FILENAME, CONFIG_PATH, PROJECT_ROOT, load_config, save_config
from .device import _device_index, detect_device, torch_device_name
from .models import (
    _HAS_COQUI,
    _HAS_KOKORO,
    _HAS_PIPER,
    RECOMMENDED_MODELS,
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
    "CONFIG_FILENAME",
    "CONFIG_PATH",
    "PROJECT_ROOT",
    "RECOMMENDED_MODELS",
    "_HAS_COQUI",
    "_HAS_KOKORO",
    "_HAS_PIPER",
    "_device_index",
    "available_models",
    "build_app",
    "build_interface",
    "build_ui",
    "create_app",
    "create_interface",
    "create_ui",
    "detect_device",
    "ensure_default_model",
    "generate",
    "launch",
    "launch_app",
    "launch_ui",
    "list_models",
    "list_recommended",
    "list_recommended_models",
    "list_voices",
    "load_config",
    "refresh_voices",
    "run",
    "run_app",
    "run_ui",
    "save_config",
    "serve",
    "start",
    "start_app",
    "start_ui",
    "synthesize",
    "torch_device_name",
]
