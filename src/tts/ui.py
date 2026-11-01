"""Gradio UI layer for the local TTS package."""

from __future__ import annotations

import time
from pathlib import Path

from .config import PROJECT_ROOT, load_config, save_config
from .device import detect_device
from .models import RECOMMENDED_MODELS, _is_probably_tts, _scan_cached_models, list_voices
from .synthesize import synthesize

try:
    import gradio as gr
except Exception:  # pragma: no cover - optional at import time
    gr = None

try:
    import soundfile as sf
except Exception:  # pragma: no cover
    sf = None


def _require_gradio():
    if gr is None:
        raise RuntimeError(
            "gradio is not installed. Install it with: uv sync "
            "(gradio is a core dependency of this project)."
        )
    return gr


def _resolve_output_dir(raw):
    p = Path(raw or "output")
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


def available_models():
    """Return a list of model ids for the UI dropdown (recommended + cached TTS)."""
    ids = []
    seen = set()
    for m in RECOMMENDED_MODELS:
        mid = m["id"]
        if mid not in seen:
            seen.add(mid)
            ids.append(mid)
    try:
        repos, _ = _scan_cached_models()
    except Exception:
        repos = None
    if repos:
        for r in repos:
            rid = r["repo_id"]
            try:
                is_tts = _is_probably_tts(rid)
            except Exception:
                is_tts = True
            if is_tts and rid not in seen:
                seen.add(rid)
                ids.append(rid)
    return ids


def refresh_voices(model_id):
    """Gradio update callback: populate voice dropdown for a model."""
    g = _require_gradio()
    voices = None
    try:
        voices = list_voices(model_id, "cpu", verbose=False)
    except Exception:
        voices = None
    choices = list(voices) if voices else []
    value = choices[0] if choices else None
    return g.update(choices=choices, value=value)


def generate(text, file_obj, model_choice, custom_model, voice_choice,
            custom_voice, device_choice, output_dir, verbose):
    """Generate audio and return (audio_path_or_None, status_text)."""
    g = _require_gradio()
    # Resolve text from textbox or uploaded file.
    if (not text or not str(text).strip()) and file_obj is not None:
        path = None
        if hasattr(file_obj, "name"):
            path = file_obj.name
        elif isinstance(file_obj, (str, Path)):
            path = file_obj
        if path is not None:
            try:
                text = Path(path).read_text(encoding="utf-8")
            except Exception:
                try:
                    text = Path(path).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    text = ""
        elif hasattr(file_obj, "read"):
            try:
                data = file_obj.read()
                text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else str(data)
            except Exception:
                text = ""
    text = (text or "").strip()
    if not text:
        return None, "No text provided."

    model_id = (custom_model or "").strip() or (model_choice or "").strip()
    if not model_id:
        return None, "No model selected."

    voice = (custom_voice or "").strip() or (voice_choice or "").strip() or None
    verbose = bool(verbose)

    try:
        dev = detect_device(device_choice or "auto", verbose=verbose)
    except Exception as e:
        return None, f"Device detection failed: {e}"

    try:
        audio, sr = synthesize(model_id, text, voice, dev, verbose=verbose)
    except Exception as e:
        return None, f"Synthesis failed: {e}"

    out_dir = _resolve_output_dir(output_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return None, f"Could not create output directory: {e}"

    out_path = out_dir / f"tts_{int(time.time())}.wav"
    if sf is None:
        try:
            import soundfile as _sf
            _sf.write(out_path, audio, sr)
        except Exception as e:
            return None, f"soundfile unavailable: {e}"
    else:
        try:
            sf.write(out_path, audio, sr)
        except Exception as e:
            return None, f"Failed to save audio: {e}"

    # Persist config (best effort).
    try:
        cfg = load_config()
        cfg["default_model"] = model_id
        cfg["device"] = device_choice or cfg.get("device", "auto")
        cfg["output_dir"] = output_dir
        cfg["verbose"] = verbose
        save_config(cfg)
    except Exception:
        pass

    duration = (len(audio) / sr) if sr else 0.0
    return str(out_path), f"Saved {out_path} ({duration:.2f}s, {sr} Hz)."


def build_app():
    """Build and return the Gradio Blocks app."""
    g = _require_gradio()

    models = available_models()
    cfg = load_config()
    default_model = cfg.get("default_model")
    if default_model and default_model not in models:
        models = [default_model] + [m for m in models if m != default_model]
    if not models:
        models = [m["id"] for m in RECOMMENDED_MODELS]
    if default_model not in models:
        default_model = models[0] if models else None

    default_device = cfg.get("device", "auto")
    if default_device not in ("auto", "cpu", "cuda"):
        default_device = "auto"
    default_output_dir = cfg.get("output_dir", "output")
    default_verbose = bool(cfg.get("verbose", False))

    with g.Blocks(title="Local TTS") as demo:
        g.Markdown("# Local TTS\nGenerate speech from text using local Hugging Face models.")
        with g.Row():
            text = g.Textbox(label="Text", lines=5, placeholder="Enter text to synthesize...")
            file_input = g.File(label="Or read text from file", type="filepath")
        with g.Row():
            model_dd = g.Dropdown(choices=models, value=default_model, label="Model")
            custom_model = g.Textbox(label="Custom model id (overrides dropdown)",
                                    placeholder="org/model-name")
        with g.Row():
            voice_dd = g.Dropdown(choices=[], value=None, label="Voice")
            custom_voice = g.Textbox(label="Custom voice (overrides dropdown)",
                                    placeholder="voice name / preset")
        with g.Row():
            device_dd = g.Dropdown(choices=["auto", "cpu", "cuda"], value=default_device,
                                 label="Device")
            output_dir_tb = g.Textbox(value=default_output_dir, label="Output directory")
            verbose_cb = g.Checkbox(value=default_verbose, label="Verbose")
        generate_btn = g.Button("Generate", variant="primary")
        with g.Row():
            audio_out = g.Audio(label="Generated audio", type="filepath")
            status = g.Textbox(label="Status", interactive=False)

        model_dd.change(fn=refresh_voices, inputs=model_dd, outputs=voice_dd)
        generate_btn.click(
            fn=generate,
            inputs=[text, file_input, model_dd, custom_model, voice_dd, custom_voice,
                    device_dd, output_dir_tb, verbose_cb],
            outputs=[audio_out, status],
        )
        demo.load(fn=refresh_voices, inputs=model_dd, outputs=voice_dd)

    return demo


def launch(port=7860, share=False, **kwargs):
    """Build and launch the Gradio app."""
    g = _require_gradio()
    app = build_app()
    return app.launch(server_port=port, share=share, **kwargs)


def main():
    launch()


# Aliases for discoverability.
build_ui = build_app
create_app = build_app
create_ui = build_app
build_interface = build_app
create_interface = build_app
make_app = build_app
make_ui = build_app
get_app = build_app
get_ui = build_app

launch_ui = launch
launch_app = launch
run = launch
run_ui = launch
run_app = launch
start = launch
start_ui = launch
start_app = launch
serve = launch


if __name__ == "__main__":
    main()
