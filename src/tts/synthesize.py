"""Synthesis engine."""

import contextlib

from .device import _device_index, torch_device_name
from .models import _HAS_COQUI, _HAS_KOKORO, _HAS_PIPER


def _apply_speed(audio, sr, speed):
    """Time-scale 1-D audio by ``speed`` (speed>1 = faster/shorter) keeping sr."""
    try:
        import numpy as np
    except Exception:
        return audio, sr
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    if not speed or speed <= 0 or speed == 1.0:
        return audio, sr
    try:
        arr = np.asarray(audio).reshape(-1)
        n = arr.shape[0]
        if n < 2:
            return audio, sr
        new_n = max(1, round(n / speed))
        if new_n == n:
            return np.asarray(audio), sr
        x_old = np.arange(n)
        x_new = np.linspace(0, n - 1, new_n)
        out = np.interp(x_new, x_old, arr).astype(np.float32)
        return out, sr
    except Exception:
        return audio, sr


def synthesize(
    model_id, text, voice, device, verbose=False, speed=1.0, playback_speed=None, rate=None
):
    if playback_speed is not None:
        speed = playback_speed
    if rate is not None:
        speed = rate
    try:
        speed = float(speed) if speed is not None else 1.0
    except (TypeError, ValueError):
        speed = 1.0
    try:
        import numpy as np
    except Exception as e:
        raise RuntimeError(f"numpy not available: {e}") from e
    lid = (model_id or "").lower()
    device_idx = _device_index(device)

    if "kokoro" in lid:
        if not _HAS_KOKORO:
            raise RuntimeError(
                "Kokoro model selected but 'kokoro' not installed. Run: uv sync --extra kokoro"
            )
        try:
            from kokoro import KPipeline

            # Kokoro voice names are prefixed by language code (e.g. "jf_alpha" -> "j").
            # Derive the pipeline language from the (first) selected voice.
            voice_name = (voice or "af_heart").strip()
            first_voice = voice_name.split(",")[0].strip() if voice_name else "af_heart"
            lang_code = first_voice[:1].lower() if first_voice else "a"
            if lang_code not in ("a", "b", "e", "f", "h", "i", "j", "p", "z"):
                lang_code = "a"

            torch_dev = torch_device_name(device)
            try:
                pl = KPipeline(lang_code=lang_code, device=torch_dev)
            except TypeError:
                pl = KPipeline(lang_code=lang_code)
            audio_chunks = []
            sr = 24000
            for _gs, _ps, audio in pl(text, voice=voice_name or "af_heart"):
                audio_chunks.append(np.asarray(audio))
            if not audio_chunks:
                raise RuntimeError("Kokoro produced no audio")
            audio = np.concatenate(audio_chunks).astype(np.float32)
            return _apply_speed(audio, sr, speed)
        except Exception as e:
            raise RuntimeError(f"Kokoro synthesis failed: {e}") from e

    if ("xtts" in lid or lid.startswith("tts_models/")) and _HAS_COQUI:
        try:
            from TTS.api import TTS as CoquiTTS

            tts = CoquiTTS(model_id)
            torch_dev = torch_device_name(device)
            with contextlib.suppress(Exception):
                tts.to(torch_dev)
            wav = tts.tts(text=text)
            audio = np.asarray(wav, dtype=np.float32)
            return _apply_speed(audio, 22050, speed)
        except Exception as e:
            raise RuntimeError(f"Coqui synthesis failed: {e}") from e

    if "piper" in lid and _HAS_PIPER:
        raise RuntimeError(
            "Piper adapter not fully implemented; use a transformers-compatible model."
        )

    try:
        from transformers import pipeline
    except Exception as e:
        raise RuntimeError(f"transformers not available: {e}") from e

    try:
        pipe = pipeline("text-to-speech", model=model_id, device=device_idx)
    except Exception as e:
        raise RuntimeError(f"Failed to load model '{model_id}': {e}") from e

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
            raise RuntimeError(f"Synthesis failed for '{model_id}': {e}") from e

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
        ) from None
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
    return _apply_speed(audio, sr, speed)
