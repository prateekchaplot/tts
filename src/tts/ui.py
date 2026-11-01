"""Gradio UI layer for the local TTS package."""

from __future__ import annotations

import time
from pathlib import Path

from .config import PROJECT_ROOT, load_config, save_config
from .device import detect_device
from .models import (
    RECOMMENDED_MODELS,
    _is_probably_tts,
    _scan_cached_models,
    list_voices,
    KOKORO_LANGUAGES,
    languages_for_model,
)
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


def _require_mcp():
    try:
        import mcp  # noqa: F401
    except Exception as e:
        raise RuntimeError(
            "The `mcp` package is required for MCP support. Install it with: uv sync --extra mcp"
        ) from e
    return True


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


def _voices_for(model_id, language=None):
    """Return voice choices for a model, optionally filtered by language code."""
    try:
        voices = list_voices(model_id, "cpu", verbose=False)
    except Exception:
        voices = None
    choices = list(voices) if voices else []
    if language and "kokoro" in (model_id or "").lower():
        lang = str(language).strip().lower()
        if lang:
            choices = [v for v in choices if (v or "")[:1].lower() == lang]
    return choices


def refresh_voices(model_id, language=None):
    """Gradio update callback: populate voice dropdown for a model/language."""
    g = _require_gradio()
    choices = _voices_for(model_id, language)
    value = choices[0] if choices else None
    return g.update(choices=choices, value=value)


def available_languages(model_id):
    """Return (name, code) choices for the language dropdown."""
    g = _require_gradio()
    choices = []
    if "kokoro" in (model_id or "").lower():
        choices.append(("All languages", ""))
        for code in languages_for_model(model_id):
            choices.append((KOKORO_LANGUAGES.get(code, code), code))
    return choices


def refresh_model(model_id):
    """Gradio update callback: populate language + voice dropdowns for a model."""
    g = _require_gradio()
    lang_choices = available_languages(model_id)
    lang_value = "" if lang_choices else None
    voices = _voices_for(model_id, lang_value)
    voice_value = voices[0] if voices else None
    return (
        g.update(choices=lang_choices, value=lang_value, interactive=bool(lang_choices)),
        g.update(choices=voices, value=voice_value),
    )


def generate(
    text,
    file_obj=None,
    model_choice=None,
    custom_model="",
    voice_choice=None,
    custom_voice="",
    device_choice="auto",
    output_dir=None,
    verbose=False,
    speed=1.0,
):
    """Generate audio and return (audio_path_or_None, status_text)."""
    _require_gradio()
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
        try:
            cfg = load_config()
            model_id = (cfg.get("default_model") or "").strip()
        except Exception:
            model_id = ""
    if not model_id:
        try:
            models = available_models()
            model_id = (models[0] if models else "").strip()
        except Exception:
            model_id = ""
    if not model_id:
        return None, "No model selected."

    voice = (custom_voice or "").strip() or (voice_choice or "").strip() or None
    verbose = bool(verbose)
    try:
        speed = float(speed) if speed is not None else 1.0
    except (TypeError, ValueError):
        speed = 1.0
    if speed <= 0:
        speed = 1.0

    try:
        dev = detect_device(device_choice or "auto", verbose=verbose)
    except Exception as e:
        return None, f"Device detection failed: {e}"

    try:
        audio, sr = synthesize(model_id, text, voice, dev, verbose=verbose, speed=speed)
    except Exception as e:
        return None, f"Synthesis failed: {e}"

    if output_dir is None:
        try:
            output_dir = load_config().get("output_dir", "output")
        except Exception:
            output_dir = "output"
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
        cfg["playback_speed"] = speed
        cfg["speed"] = speed
        save_config(cfg)
    except Exception:
        pass

    duration = (len(audio) / sr) if sr else 0.0
    return str(out_path), f"Saved {out_path} ({duration:.2f}s, {sr} Hz)."


# Mark `generate` as an MCP tool so it is exposed when the Gradio app runs as an
# MCP server (see launch(mcp_server=True)).
try:
    generate._mcp_type = "tool"
    generate._mcp_name = "generate"
    generate._mcp_structured_output = False
    generate._mcp_meta = None
    generate._mcp_description = (
        "Generate speech audio from text using a local TTS model. "
        "Returns the path to the saved WAV file and a status message."
    )
except Exception:
    pass


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
    default_speed = cfg.get("playback_speed", cfg.get("speed", 1.0))
    try:
        default_speed = float(default_speed)
    except (TypeError, ValueError):
        default_speed = 1.0
    if default_speed <= 0:
        default_speed = 1.0

    with g.Blocks(title="Local TTS") as demo:
        g.Markdown("# Local TTS\nGenerate speech from text using local Hugging Face models.")
        with g.Row():
            text = g.Textbox(label="Text", lines=5, placeholder="Enter text to synthesize...")
            file_input = g.File(label="Or read text from file", type="filepath")
        with g.Row():
            model_dd = g.Dropdown(choices=models, value=default_model, label="Model")
            custom_model = g.Textbox(
                label="Custom model id (overrides dropdown)", placeholder="org/model-name"
            )
        with g.Row():
            lang_dd = g.Dropdown(choices=[], value=None, label="Language")
            voice_dd = g.Dropdown(choices=[], value=None, label="Voice")
            custom_voice = g.Textbox(
                label="Custom voice (overrides dropdown)", placeholder="voice name / preset"
            )
        with g.Row():
            device_dd = g.Dropdown(
                choices=["auto", "cpu", "cuda"], value=default_device, label="Device"
            )
            output_dir_tb = g.Textbox(value=default_output_dir, label="Output directory")
            verbose_cb = g.Checkbox(value=default_verbose, label="Verbose")
            speed_slider = g.Slider(
                minimum=0.5, maximum=2.0, value=default_speed, step=0.05, label="Playback speed"
            )
        generate_btn = g.Button("Generate", variant="primary")
        with g.Row():
            audio_out = g.Audio(label="Generated audio", type="filepath")
            status = g.Textbox(label="Status", interactive=False)

        model_dd.change(
            fn=refresh_model, inputs=model_dd, outputs=[lang_dd, voice_dd], api_visibility="private"
        )
        lang_dd.change(
            fn=refresh_voices, inputs=[model_dd, lang_dd], outputs=voice_dd, api_visibility="private"
        )
        generate_btn.click(
            fn=generate,
            inputs=[
                text,
                file_input,
                model_dd,
                custom_model,
                voice_dd,
                custom_voice,
                device_dd,
                output_dir_tb,
                verbose_cb,
                speed_slider,
            ],
            outputs=[audio_out, status],
        )
        demo.load(fn=refresh_model, inputs=model_dd, outputs=[lang_dd, voice_dd], api_visibility="private")

    return demo


def launch(port=7860, share=False, mcp_server=None, **kwargs):
    """Build and launch the Gradio app.

    Pass ``mcp_server=True`` (or set the ``GRADIO_MCP_SERVER`` env var) to
    expose the app as an MCP server.
    """
    _require_gradio()
    if mcp_server:
        _require_mcp()
    # Gradio prints a hammer emoji when the MCP server starts, which can crash on
    # Windows consoles using a legacy code page. Force UTF-8 output to be safe.
    try:
        import sys

        for _stream in (sys.stdout, sys.stderr):
            if hasattr(_stream, "reconfigure"):
                _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    app = build_app()
    return app.launch(server_port=port, share=share, mcp_server=mcp_server, **kwargs)


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
