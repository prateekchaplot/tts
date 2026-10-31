# Contributing

Thanks for your interest in contributing to this project.

## Setup

See the [Setup](README.md#setup) and [Usage](README.md#usage) sections of the README for environment and run instructions. In short:

```powershell
uv sync
uv run main.py "Hello world"
```

Optional extras (note: the Piper adapter is not yet implemented; `kokoro` and `coqui` are):

```powershell
uv sync --extra kokoro
uv sync --extra piper
uv sync --extra coqui
uv sync --extra bark
```

## Development workflow

1. Create a branch for your change.
2. Make focused, minimal changes consistent with the existing structure and style.
3. Run the CLI to verify your changes (e.g. `uv run main.py "Hello world"`).
4. Submit a pull request with a clear description of the change.

## Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/). Every commit message must follow this format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Allowed types:

- `feat`: a new feature
- `fix`: a bug fix
- `docs`: documentation only changes
- `style`: formatting, no code change
- `refactor`: code change that neither fixes a bug nor adds a feature
- `perf`: performance improvement
- `test`: adding or correcting tests
- `build`: build system or dependency changes
- `ci`: CI configuration changes
- `chore`: other changes that don't modify src or test files
- `revert`: reverts a previous commit

Examples:

```
feat: add piper adapter
fix(device): handle missing CUDA gracefully
docs: update README usage examples
chore: regenerate uv.lock
```

Rules:

- Use the imperative mood in the description ("add", not "added").
- Keep the first line under 72 characters.
- Reference issues in the footer when applicable (e.g. `Closes #12`).
- Breaking changes must be indicated with `!` after the type/scope and described in the footer (e.g. `feat!: drop Python 3.11 support`).

## Code style

- Keep changes consistent with existing naming and module layout under `src/tts/`.
- Do not create a conflicting `src/tts.py`.
- Prefer the transformers-native recommended model list; adapters are optional and should only be used when installed.
- Print device detection on load; default to auto (CUDA if available).

## Reporting issues

Please include reproduction steps, expected vs. actual behavior, and your environment (Python version, device, model id).