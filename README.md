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

Run commands with `uv run`:
```powershell
uv run python main.py "Hello world"
```

## Usage
```powershell
python main.py "Hello world"
python main.py --model facebook/mms-tts-eng "Hello"
python main.py --file input.txt
python main.py --output out.wav
python main.py --output-dir my_outputs
python main.py --list-models
python main.py --recommended
python main.py --list-voices
```

First run (no `.config.json`) prompts for a default model and saves it. Edit `.config.json` to change defaults. Flags override config.

Generated audio is written to the configured output directory (default `output/`) unless `--output` specifies a path.

## Config
- `default_model`: Hugging Face model id.
- `device`: `auto`, `cpu`, or `cuda`.
- `output_dir`: directory for generated WAV files (default `output`).
- `verbose`: enable verbose logging.