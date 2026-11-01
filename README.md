# Local TTS (Hugging Face)

CLI to run text-to-speech locally with models downloaded from Hugging Face.

## Setup
```powershell
uv sync
```
Optional extras:
```powershell
uv sync --extra kokoro
uv sync --extra piper
uv sync --extra coqui
uv sync --extra bark
```
Note: `kokoro` and `coqui` adapters are implemented; `piper` is not yet implemented; `bark` runs through the transformers pipeline (not as a dedicated adapter).

Run commands with `uv run`:
```powershell
uv run main.py "Hello world"
```

## Usage
```powershell
uv run main.py "Hello world"
uv run main.py --model facebook/mms-tts-eng "Hello"
uv run main.py --voice <voice> "Hello"
uv run main.py --device cpu "Hello"
uv run main.py --speed 1.25 "Hello"
uv run main.py --file input.txt
uv run main.py --output out.wav
uv run main.py --output-dir my_outputs
uv run main.py --list-models
uv run main.py --recommended
uv run main.py --list-voices
uv run main.py --verbose
```

Launch the Gradio web UI:
```powershell
uv run main.py --ui
uv run main.py --ui --ui-port 7860 --ui-share
```

Text can also be entered interactively when no text and no `--file` are given.

First run (when `default_model` is unset in `.config.json`) prompts for a default model and saves it. Edit `.config.json` to change defaults. Flags override config for the current run; `--device`, `--output-dir`, and `--verbose` are also persisted to config.

Playback has been removed; audio is always saved. Generated audio is written to the configured output directory (default `output/`, resolved relative to the project root) unless `--output` specifies a path (relative paths are resolved against the current working directory). Device detection (`auto` / CUDA / CPU) is printed on load.

## Config
- `default_model`: Hugging Face model id.
- `device`: `auto`, `cpu`, or `cuda`.
- `output_dir`: directory for generated WAV files (default `output`).
- `verbose`: enable verbose logging.
- `playback_speed` / `speed`: playback speed factor (default 1.0).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, workflow, and commit-message conventions (this project uses Conventional Commits).