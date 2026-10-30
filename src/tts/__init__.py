"""Local TTS package."""

# Re-exported implementation (moved from src/tts.py)
import json
import sys
from pathlib import Path

# PROJECT_ROOT: src/tts/__init__.py -> src/tts -> src -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILENAME = ".config.json"
CONFIG_PATH = PROJECT_ROOT / CONFIG_FILENAME

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


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def detect_device(requested="auto", verbose=False):
    requested = (requested or "auto").lower()
    try:
        import torch
    except Exception as e:
        print(f"[device] torch not available ({e}); forcing cpu")
        return "cpu"
    if requested == "auto":
        if torch.cuda.is_available():
            dev = "cuda"
        else:
            dev = "cpu"
    else:
        dev = requested
    print(f"[device] requested={requested} -> {dev}")
    if dev == "cuda":
        try:
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
            print(f"[device] GPU: {name} ({vram:.1f} GB VRAM)")
        except Exception as e:
            print(f"[device] GPU info unavailable: {e}")
    else:
        print("[device] running on CPU")
    return dev


def _device_index(device):
    if device == "cuda":
        return 0
    return -1


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
            extra = " (optional: pip install kokoro)"
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


def synthesize(model_id, text, voice, device, verbose=False):
    try:
        import numpy as np
    except Exception as e:
        raise RuntimeError(f"numpy not available: {e}")
    lid = (model_id or "").lower()
    device_idx = _device_index(device)

    if "kokoro" in lid:
        if not _HAS_KOKORO:
            raise RuntimeError("Kokoro model selected but 'kokoro' not installed. pip install kokoro")
        try:
            from kokoro import KPipeline
            pl = KPipeline(lang_code="a")
            audio_chunks = []
            sr = 24000
            for _gs, _ps, audio in pl(text, voice=voice or "af_heart"):
                audio_chunks.append(np.asarray(audio))
            if not audio_chunks:
                raise RuntimeError("Kokoro produced no audio")
            audio = np.concatenate(audio_chunks).astype(np.float32)
            return audio, sr
        except Exception as e:
            raise RuntimeError(f"Kokoro synthesis failed: {e}")

    if ("xtts" in lid or lid.startswith("tts_models/")) and _HAS_COQUI:
        try:
            from TTS.api import TTS as CoquiTTS
            tts = CoquiTTS(model_id)
            wav = tts.tts(text=text)
            audio = np.asarray(wav, dtype=np.float32)
            return audio, 22050
        except Exception as e:
            raise RuntimeError(f"Coqui synthesis failed: {e}")

    if "piper" in lid and _HAS_PIPER:
        raise RuntimeError("Piper adapter not fully implemented; use a transformers-compatible model.")

    try:
        from transformers import pipeline
    except Exception as e:
        raise RuntimeError(f"transformers not available: {e}")

    try:
        pipe = pipeline("text-to-speech", model=model_id, device=device_idx)
    except Exception as e:
        raise RuntimeError(f"Failed to load model '{model_id}': {e}")

    out = None
    if voice:
        for key in ("voice_preset", "voice", "speaker", "description"):
            try:
                out = pipe(text, **{key: voice})
                if verbose:
                    print(f"[synth] used voice kwarg: {key}")
                break
            except Exception:
                out = None
                continue
    if out is None:
        try:
            out = pipe(text)
        except Exception as e:
            raise RuntimeError(f"Synthesis failed for '{model_id}': {e}")

    if not isinstance(out, dict) or "audio" not in out:
        raise RuntimeError(f"Unexpected pipeline output: {type(out)}")

    audio = np.asarray(out["audio"]).squeeze().astype(np.float32)
    sr = int(out.get("sampling_rate", 16000))
    return audio, sr