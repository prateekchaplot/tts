"""Synthesis engine."""

from .device import _device_index
from .models import _HAS_COQUI, _HAS_KOKORO, _HAS_PIPER


def synthesize(model_id, text, voice, device, verbose=False):
    try:
        import numpy as np
    except Exception as e:
        raise RuntimeError(f"numpy not available: {e}")
    lid = (model_id or "").lower()
    device_idx = _device_index(device)

    if "kokoro" in lid:
        if not _HAS_KOKORO:
            raise RuntimeError("Kokoro model selected but 'kokoro' not installed. Run: uv sync --extra kokoro")
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
