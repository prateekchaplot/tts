"""Configuration helpers and paths for the TTS package."""

import json
from pathlib import Path

# PROJECT_ROOT: src/tts/config.py -> src/tts -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILENAME = ".config.json"
CONFIG_PATH = PROJECT_ROOT / CONFIG_FILENAME


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
