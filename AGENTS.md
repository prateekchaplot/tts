# Project instructions (Text-to-Speech, TTS)

- Environment: Python 3.12; managed with uv (`.python-version`). Dependencies in `pyproject.toml` (lockfile `uv.lock`); install with `uv sync` (user runs it; do not auto-install).
- Entry point: `uv run main.py ...` at repo root. Implementation lives in the `src/tts/` package. Do not create a conflicting `src/tts.py`.
- Config: `.config.json` at project root. Precedence: CLI args > config > defaults. It is created on first model selection or settings save (not automatically on startup).
- Device: default auto (CUDA if available); print detection on load.
- Playback removed; audio is always saved. Outputs go to configured `output_dir` (default `output/`).
- Text input: positional arg or `--file`.
- Models: prefer transformers-native recommended list; optional adapters (Kokoro/Piper/Coqui) only if installed, with install hints (`uv sync --extra <name>`). `bark` runs through the transformers pipeline.
- No voice cloning in first iteration. No `--cache-dir`.
- Keep changes consistent with existing structure, naming, and style.
- Never run Python code (including `uv run main.py`, tests, or snippets); if code output is required, ask the user to run it and provide the output.