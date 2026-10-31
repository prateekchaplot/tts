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
Note: `kokoro` and `coqui` adapters are implemented; the `piper` adapter is not yet implemented, and `bark` models run through the transformers pipeline (the extra is optional).

Run commands with `uv run`:
```powershell
uv run python main.py "Hello world"
```

## Usage
```powershell
uv run python main.py "Hello world"
uv run python main.py --model facebook/mms-tts-eng "Hello"
uv run python main.py --voice <voice> "Hello"
uv run python main.py --device cpu "Hello"
uv run python main.py --file input.txt
uv run python main.py --output out.wav
uv run python main.py --output-dir my_outputs
uv run python main.py --list-models
uv run python main.py --recommended
uv run python main.py --list-voices
uv run python main.py --verbose
```

Text can also be entered interactively when no text and no `--file` are given.

First run (when `default_model` is unset in `.config.json`) prompts for a default model and saves it. Edit `.config.json` to change defaults. Flags override config for the current run; `--device`, `--output-dir`, and `--verbose` are also persisted to config.

Generated audio is written to the configured output directory (default `output/`, resolved relative to the project root) unless `--output` specifies a path (relative paths are resolved against the current working directory).

## Config
- `default_model`: Hugging Face model id.
- `device`: `auto`, `cpu`, or `cuda`.
- `output_dir`: directory for generated WAV files (default `output`).
- `verbose`: enable verbose logging.