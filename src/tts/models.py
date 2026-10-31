"""Recommended models and model/voice helpers."""

import json
import os
import sys
from pathlib import Path

from .config import CONFIG_PATH, save_config
from .device import _device_index

RECOMMENDED_MODELS = [
    {"id": "facebook/mms-tts-eng", "label": "MMS English (fast, lightweight)"},
    {"id": "suno/bark-small", "label": "Bark small (expressive, slower)"},
    {"id": "suno/bark", "label": "Bark full (high quality, slow)"},
    {"id": "parler-tts/parler-tts-mini-v1", "label": "Parler-TTS mini (voice descriptions)"},
    {"id": "microsoft/speecht5_tts", "label": "SpeechT5 (classic)"},
    {"id": "hexgrad/Kokoro-82M", "label": "Kokoro 82M (needs kokoro extra)"},
]

_HAS_KOKORO = False
_HAS_PIPER = False
_HAS_COQUI = False
try:
    import kokoro  # noqa: F401
    _HAS_KOKORO = True
except Exception:
    pass
try:
    import piper  # noqa: F401
    _HAS_PIPER = True
except Exception:
    pass
try:
    from TTS.api import TTS as _CoquiTTS  # noqa: F401
    _HAS_COQUI = True
except Exception:
    pass


def ensure_default_model(cfg, args_model):
    if args_model:
        return args_model
    if "default_model" in cfg and cfg["default_model"]:
        return cfg["default_model"]
    print("\nNo default model configured. Choose one:")
    for i, m in enumerate(RECOMMENDED_MODELS, 1):
        print(f"  {i}. {m['id']} - {m['label']}")
    print(f"  {len(RECOMMENDED_MODELS) + 1}. Enter a custom Hugging Face model id")
    choice = None
    try:
        choice = input("Selection: ").strip()
    except EOFError:
        choice = ""
    model_id = None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(RECOMMENDED_MODELS):
            model_id = RECOMMENDED_MODELS[idx - 1]["id"]
        elif idx == len(RECOMMENDED_MODELS) + 1:
            try:
                model_id = input("Hugging Face model id: ").strip()
            except EOFError:
                model_id = ""
    if not model_id:
        model_id = RECOMMENDED_MODELS[0]["id"]
        print(f"[config] no selection; defaulting to {model_id}")
    cfg["default_model"] = model_id
    try:
        save_config(cfg)
        print(f"[config] saved default model to {CONFIG_PATH}")
    except Exception as e:
        print(f"[config] could not save config: {e}")
    return model_id


_KNOWN_TTS_MODEL_TYPES = {
    "vits", "bark", "speecht5", "parler_tts", "musicgen", "musicgen_melody",
    "csm", "dia", "encodec", "mimi", "fastspeech2_conformer_with_hifigan",
    "univnet",
}
_TTS_NAME_TOKENS = (
    "tts", "speech", "bark", "parler", "kokoro", "mms", "vits", "xtts",
    "audio", "tortoise", "piper", "melotts", "cosyvoice", "chat-tts", "f5",
    "styletts", "orpheus", "chatterbox",
)


def _cache_root(cache_dir=None):
    if cache_dir is not None:
        return Path(cache_dir)
    env = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if env:
        return Path(env)
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _is_probably_tts(repo_id, cache_dir=None):
    root = _cache_root(cache_dir)
    repo_dir = root / ("models--" + (repo_id or "").replace("/", "--"))
    if repo_dir.exists():
        for cfg_path in repo_dir.rglob("config.json"):
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            sr = data.get("sampling_rate", data.get("sample_rate"))
            if sr is not None:
                return True
            if "codec_config" in data:
                return True
            mt = data.get("model_type")
            if isinstance(mt, str) and mt.lower() in _KNOWN_TTS_MODEL_TYPES:
                return True
    low = (repo_id or "").lower()
    return any(tok in low for tok in _TTS_NAME_TOKENS)


def _human_size(num):
    if not num:
        return ""
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def _scan_cached_models(cache_dir=None):
    """Return (list_of_dicts, error_message_or_None) for cached HF models."""
    try:
        from huggingface_hub import scan_cache_dir
    except Exception as e:
        return None, f"huggingface_hub unavailable: {e}"
    try:
        info = scan_cache_dir(cache_dir) if cache_dir is not None else scan_cache_dir()
    except Exception as e:
        return None, str(e)

    recommended_ids = {m["id"] for m in RECOMMENDED_MODELS}
    repos = []
    for r in getattr(info, "repos", []) or []:
        if getattr(r, "repo_type", None) != "model":
            continue
        size = getattr(r, "size_on_disk", 0) or 0
        if not size:
            continue
        repos.append(
            {
                "repo_id": r.repo_id,
                "size_bytes": size,
                "size_human": getattr(r, "size_on_disk_str", None) or _human_size(size),
                "complete": bool(getattr(r, "revisions", None)) and bool(getattr(r, "refs", None)),
                "recommended": r.repo_id in recommended_ids,
            }
        )
    repos.sort(key=lambda x: x["repo_id"])
    return repos, None


def list_models(cache_dir=None, tts_only=False):
    """List models available in the local Hugging Face cache."""
    repos, err = _scan_cached_models(cache_dir)
    if err is not None:
        print(f"Could not scan local model cache: {err}", file=sys.stderr)
        return []
    if not repos:
        print("No locally cached models found.")
        return []
    tts_flags = {r["repo_id"]: _is_probably_tts(r["repo_id"], cache_dir) for r in repos}
    if tts_only:
        repos = [r for r in repos if tts_flags[r["repo_id"]]]
    print("Locally available models:")
    for r in repos:
        suffix = " [recommended]" if r["recommended"] else ""
        tts_tag = " [TTS]" if tts_flags[r["repo_id"]] else " [not TTS]"
        print(f"  {r['repo_id']}  ({r['size_human']}){suffix}{tts_tag}")
    return repos


def list_recommended_models(show_cached=True, cache_dir=None):
    """List recommended models, annotated with cache status when possible."""
    cached_ids = set()
    if show_cached:
        repos, _ = _scan_cached_models(cache_dir)
        if repos:
            cached_ids = {r["repo_id"] for r in repos}

    print("Recommended models:")
    result = []
    for m in RECOMMENDED_MODELS:
        extra = m.get("extra", "")
        if not extra and "Kokoro" in m.get("label", ""):
            extra = " (optional: uv sync --extra kokoro)"
        cached = ""
        if show_cached:
            cached = " [cached]" if m["id"] in cached_ids else " [not cached]"
        print(f"  {m['id']} - {m['label']}{extra}{cached}")
        result.append(dict(m))
    return result


# Backwards-compatible alias.
list_recommended = list_recommended_models


def list_voices(model_id, device, verbose=False):
    lid = (model_id or "").lower()
    if "kokoro" in lid:
        try:
            from kokoro import KPipeline  # noqa: F401
            voices = ["af_heart", "af_alloy", "af_aoede", "af_bella", "af_jessica",
                      "af_kore", "af_nicole", "af_nova", "af_river", "af_sarah",
                      "af_sky", "am_adam", "am_echo", "am_eric", "am_fenrir",
                      "am_liam", "am_michael", "am_onyx", "am_puck", "am_santa",
                      "bf_emma", "bf_isabella", "bm_george", "bm_lewis", "bm_daniel"]
            return voices
        except Exception as e:
            if verbose:
                print(f"[voices] kokoro load failed: {e}")
    if "bark" in lid:
        presets = [f"v2/en_speaker_{i}" for i in range(10)]
        presets += ["v2/zh_speaker_0", "v2/zh_speaker_1", "v2/zh_speaker_2",
                    "v2/zh_speaker_3", "v2/zh_speaker_4", "v2/zh_speaker_5",
                    "v2/zh_speaker_6", "v2/zh_speaker_7", "v2/zh_speaker_8",
                    "v2/zh_speaker_9", "v2/fr_speaker_0", "v2/de_speaker_0",
                    "v2/hi_speaker_0", "v2/it_speaker_0", "v2/ja_speaker_0",
                    "v2/ko_speaker_0", "v2/pl_speaker_0", "v2/pt_speaker_0",
                    "v2/ru_speaker_0", "v2/es_speaker_0", "v2/tr_speaker_0"]
        return presets
    try:
        from transformers import pipeline
        pipe = pipeline("text-to-speech", model=model_id, device=_device_index(device))
        model = getattr(pipe, "model", None)
        voices = None
        if model is not None:
            for attr in ("speakers", "voices", "speaker_ids"):
                v = getattr(model, attr, None)
                if v:
                    voices = list(v)
                    break
            if voices is None:
                cfg = getattr(model, "config", None)
                if cfg is not None:
                    for attr in ("speakers", "voices"):
                        v = getattr(cfg, attr, None)
                        if v:
                            voices = list(v)
                            break
        return voices
    except Exception as e:
        if verbose:
            print(f"[voices] could not enumerate: {e}")
        return None
