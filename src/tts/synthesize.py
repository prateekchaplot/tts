"""Synthesis engine."""

from .device import _device_index, torch_device_name
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
            torch_dev = torch_device_name(device)
            try:
                pl = KPipeline(lang_code="a", device=torch_dev)
            except TypeError:
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
            torch_dev = torch_device_name(device)
            try:
                tts.to(torch_dev)
            except Exception:
                pass
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

    if getattr(pipe, "sampling_rate", None) is None:
        raise RuntimeError(
            f"Model '{model_id}' does not appear to be a text-to-speech model "
            f"(no sampling rate). Use --recommended or a cached [TTS] model."
        )

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

    sr_raw = out.get("sampling_rate", None)
    if sr_raw is None:
        sr_raw = getattr(pipe, "sampling_rate", None)
    try:
        sr = int(sr_raw)
    except (TypeError, ValueError):
        raise RuntimeError(
            f"Model '{model_id}' did not return a valid sampling rate ({sr_raw!r}); "
            f"it may not be a text-to-speech model."
        )
    if sr <= 0:
        raise RuntimeError(f"Model '{model_id}' returned an invalid sampling rate: {sr}")

    audio = np.asarray(out["audio"]).squeeze()
    if audio.size == 0 or not np.issubdtype(audio.dtype, np.number):
        raise RuntimeError(f"Model '{model_id}' returned no usable audio.")
    if not np.all(np.isfinite(audio)):
        raise RuntimeError(f"Model '{model_id}' returned non-finite audio.")
    if audio.ndim != 1:
        raise RuntimeError(
            f"Model '{model_id}' returned unexpected audio shape {tuple(audio.shape)}; "
            f"it may not be a text-to-speech model."
        )
    audio = audio.astype(np.float32)
    return audio, sr
