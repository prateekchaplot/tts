# Contributing

Thanks for your interest in contributing to this project.

## Setup

See the [Setup](README.md#setup) and [Usage](README.md#usage) sections of the README for environment and run instructions. In short:

```powershell
uv sync
uv run main.py "Hello world"
```

Launch the Gradio web UI:
```powershell
uv run main.py --ui
```

Optional extras (note: `kokoro` and `coqui` adapters are implemented; `piper` is not yet implemented; `bark` runs through the transformers pipeline):

```powershell
uv sync --extra kokoro
uv sync --extra piper
uv sync --extra coqui
uv sync --extra bark
```

## Development workflow

1. Create a branch for your change.
2. Install dev tools and git hooks:
   ```powershell
   uv sync
   uv run python scripts/setup_dev.py
   ```
   (Re-running `setup_dev.py` is safe.)
3. Make focused, minimal changes consistent with the existing structure and style.
4. Run lint/format checks and the CLI to verify your changes:
   ```powershell
   uv run --group dev ruff check .
   uv run --group dev ruff format --check .
   uv run main.py "Hello world"
   ```
5. Submit a pull request with a clear description of the change.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) briefly: `feat: ...`, `fix: ...`, `docs: ...`. Keep the first line under 72 characters. Breaking changes should be noted with `!`.

## Code style

- Keep changes consistent with existing naming and module layout under `src/tts/`.
- Run Ruff (`uv run --group dev ruff check .` and `ruff format --check .`) before committing; pre-commit hooks are installed by `scripts/setup_dev.py`.
- Do not create a conflicting `src/tts.py`.
- Prefer the transformers-native recommended model list; adapters are optional and should only be used when installed.
- Playback has been removed; audio is always saved. Default output directory is `output/` (project root). Config `.config.json` uses CLI > config > defaults precedence. No `--cache-dir`. No voice cloning in this iteration.

## Reporting issues

Please include reproduction steps, expected vs. actual behavior, and your environment (Python version, device, model id).