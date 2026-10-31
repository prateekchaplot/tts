# Project instructions (tts)

- Environment: Python 3.12; managed with uv (`.python-version`). Dependencies in `pyproject.toml` (lockfile `uv.lock`); install with `uv sync` (user runs it; do not auto-install).
- Entry point: `uv run main.py ...` at repo root. Implementation lives in the `src/tts/` package. Do not create a conflicting `src/tts.py`.
- Config: `.config.json` at project root. Precedence: CLI args > config > defaults. First run creates it.
- Device: default auto (CUDA if available); print detection on load.
- Playback removed; audio is always saved. Outputs go to configured `output_dir` (default `output/`).
- Text input: positional arg or `--file`.
- Models: prefer transformers-native recommended list; optional adapters (Kokoro/Piper/Coqui) only if installed, with install hints.
- No voice cloning in first iteration. No `--cache-dir`.
- Keep changes consistent with existing structure, naming, and style.