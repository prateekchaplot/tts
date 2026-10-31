"""Recommended models and model/voice helpers."""

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


def list_models():
    print("Recommended models:")
    for m in RECOMMENDED_MODELS:
        extra = ""
        if "Kokoro" in m["label"]:
            extra = " (optional: uv sync --extra kokoro)"
        print(f"  {m['id']} - {m['label']}{extra}")


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
