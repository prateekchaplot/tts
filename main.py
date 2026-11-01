"""Entry point for the local Hugging Face TTS CLI."""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

import contextlib  # noqa: E402

import soundfile as sf  # noqa: E402

from tts import (  # noqa: E402
    detect_device,
    ensure_default_model,
    list_models,
    list_recommended_models,
    list_voices,
    load_config,
    save_config,
    synthesize,
)


def _resolve_output_dir(args, cfg):
    raw = args.output_dir if getattr(args, "output_dir", None) else cfg.get("output_dir", "output")
    p = Path(raw)
    if not p.is_absolute():
        p = ROOT / p
    return p


def parse_args():
    p = argparse.ArgumentParser(description="Local TTS using Hugging Face models")
    p.add_argument("text", nargs="*", help="Text to synthesize")
    p.add_argument("--model", help="Hugging Face model id (overrides config)")
    p.add_argument("--voice", help="Voice name/preset (model-specific)")
    p.add_argument(
        "--device", default=None, choices=["auto", "cpu", "cuda"], help="Device (default: auto)"
    )
    p.add_argument("--output", "-o", help="Save WAV to this path")
    p.add_argument("--output-dir", help="Directory for generated WAV files (overrides config)")
    p.add_argument("--file", "-f", help="Read text from file")
    p.add_argument("--list-models", action="store_true", help="List locally cached models")
    p.add_argument("--recommended", action="store_true", help="List recommended models")
    p.add_argument("--list-voices", action="store_true", help="List voices for selected model")
    p.add_argument("--verbose", action="store_true", help="Verbose logging")
    p.add_argument(
        "--speed",
        "--playback-speed",
        "--rate",
        dest="speed",
        type=float,
        default=None,
        help="Playback speed factor (default: config or 1.0)",
    )
    p.add_argument("--ui", action="store_true", help="Launch the Gradio web UI")
    p.add_argument(
        "--ui-port", type=int, default=7860, help="Port for the Gradio UI (default: 7860)"
    )
    p.add_argument(
        "--ui-share", action="store_true", help="Create a public share link for the Gradio UI"
    )
    p.add_argument(
        "--mcp",
        "--mcp-server",
        dest="mcp_server",
        action="store_true",
        help="Expose the Gradio UI as an MCP server (requires `uv sync --extra mcp`)",
    )
    return p.parse_args()


def main():
    args = parse_args()

    if getattr(args, "ui", False) or getattr(args, "mcp_server", False):
        from tts.ui import launch

        launch(
            port=getattr(args, "ui_port", 7860),
            share=bool(getattr(args, "ui_share", False)),
            mcp_server=True if getattr(args, "mcp_server", False) else None,
        )
        return

    cfg = load_config()

    verbose = bool(args.verbose or cfg.get("verbose", False))

    if args.speed is not None:
        speed = float(args.speed)
    else:
        speed = cfg.get("playback_speed", cfg.get("speed", 1.0))
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        speed = 1.0
    if speed <= 0:
        print("Speed must be > 0.")
        return

    if args.list_models or args.recommended:
        if args.list_models:
            list_models()
        if args.recommended:
            list_recommended_models()
        print(
            "Note: only [TTS] models can be synthesized; see --recommended for known-good models."
        )
        return

    requested_device = args.device if args.device else cfg.get("device", "auto")
    device = detect_device(requested_device, verbose=verbose)

    model_id = ensure_default_model(cfg, args.model)

    if args.list_voices:
        voices = list_voices(model_id, device, verbose=verbose)
        if voices:
            print(f"Voices for {model_id}:")
            for v in voices:
                print(f"  {v}")
        else:
            print(f"No enumerable voices for {model_id} (model may use a default voice).")
        return

    if args.file:
        text = Path(args.file).read_text(encoding="utf-8").strip()
    elif args.text:
        text = " ".join(args.text).strip()
    else:
        try:
            text = input("Enter text: ").strip()
        except EOFError:
            text = ""
    if not text:
        print("No text provided.")
        return

    print(f"[model] {model_id}")
    print(f"[text] {text[:120]}{'...' if len(text) > 120 else ''}")

    audio, sr = synthesize(model_id, text, args.voice, device, verbose=verbose, speed=speed)
    duration = len(audio) / sr if sr else 0.0
    print(f"[audio] samples={len(audio)} sr={sr} duration={duration:.2f}s speed={speed}")

    out_path = args.output
    if not out_path:
        out_dir = _resolve_output_dir(args, cfg)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"tts_{int(time.time())}.wav")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, audio, sr)
    saved_path = str(out_path)
    print(f"[saved] {saved_path}")

    if args.output_dir:
        cfg["output_dir"] = args.output_dir
    if args.device:
        cfg["device"] = args.device
    if args.verbose:
        cfg["verbose"] = True
    if args.speed is not None:
        cfg["playback_speed"] = speed
        cfg["speed"] = speed
    if args.output_dir or args.device or args.verbose or args.speed is not None:
        with contextlib.suppress(Exception):
            save_config(cfg)


if __name__ == "__main__":
    main()
