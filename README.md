# tts

Local text to speech with synchronized subtitles.

tts is a single-user web application that runs entirely on your computer. Paste or upload
plain text, choose an offline voice, and get a WAV file with word-level timings and SRT/WebVTT
subtitles. Play the audio in the browser while the current word is highlighted, seek by clicking
a word or sentence, download the files, and reopen recent generations from History.

Nothing is uploaded. The server binds to `127.0.0.1`, and the only network access is the
one-time voice download during setup.

- [Install](#install)
- [First run](#first-run)
- [Use it](#use-it)
- [Configuration](#configuration)
- [Where your data lives](#where-your-data-lives)
- [Troubleshooting](#troubleshooting)
- [Development](#development)
- [Documentation](#documentation)

## Install

### What you need

| Requirement | Details |
|---|---|
| Operating system | **Tested:** Windows 10/11 (x64) and Linux (x64, glibc 2.28+). **Expected to work:** Linux arm64 and macOS 14+ on Apple Silicon. macOS on Intel is not supported by the pinned ONNX Runtime wheel. |
| Python | **3.12.x only** (`>=3.12,<3.13`). Python 3.13 is not supported by the pinned `piper-tts`/`onnxruntime` stack. |
| Node.js | 22 LTS, only to build the web interface from source. |
| Disk space | About 1 GB for Python dependencies plus about 60 MB per installed voice. Generated audio is kept for the 20 most recent generations. |
| Network | Needed once, to install dependencies and download the first voice. After that the full workflow runs offline. |
| Windows extra | The [Microsoft Visual C++ 2015–2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe) must be installed and current. The pinned ONNX Runtime crashes on startup with an older redistributable. |

This release is installed **from source**. It is not published as a package on PyPI. Use the
editable install shown below (`pip install -e .`): a non-editable `pip install .` installs the
API but not the built web interface in this release.

### Steps

The commands below are for Windows PowerShell; the POSIX equivalents are shown after them.

```powershell
git clone https://github.com/prateekchaplot/tts.git
cd tts

py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .

cd frontend
npm ci
npm run build
cd ..

tts
```

On macOS or Linux:

```bash
git clone https://github.com/prateekchaplot/tts.git
cd tts

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

cd frontend
npm ci
npm run build
cd ..

tts
```

`tts` starts the server on `http://127.0.0.1:8321` and opens your browser. Press `Ctrl+C` in
the terminal to stop it. Generation history, settings, and voices are kept in the data directory,
so they survive restarts.

If your shell refuses to run the PowerShell activation script, run
`Set-ExecutionPolicy -Scope Process RemoteSigned` in that terminal first, or call
`.venv\Scripts\tts.exe` directly without activating.

### Alternative: run without activating the environment

```powershell
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\tts.exe
```

Nothing is installed system-wide; deleting the checkout's `.venv` folder removes the Python
environment. Your generated audio lives outside the checkout, in the data directory described
below.

## First run

On first start, if no voice is installed, tts downloads the default voice
`en_US-lessac-medium` (about 60 MB) and logs one line about it. This is the only time the
application uses the network by itself.

If the download fails (for example you are offline), the app still starts and shows a
"no voices installed" message. Install a voice later from the same environment:

```bash
tts add-voice en_US-lessac-medium
```

Reload the page after installing a voice. Other Piper voice names can be used, for example
`en_US-amy-medium` or `de_DE-thorsten-medium`; the voice catalogue is at
<https://huggingface.co/rhasspy/piper-voices>. Voice installation needs internet access once;
afterwards synthesis is fully offline.

## Use it

1. Paste text, or choose a plain `.txt` file with **Upload plain text**. Uploaded text appears
   in the editor for review before anything is generated.
2. Pick a voice and, if you like, adjust **Speaking rate** (0.5–2.0) and **Volume** (0.0–1.0).
   **Preview voice** plays a short sample. Settings are saved when a control loses focus.
3. Choose **Generate audio**. Progress shows how many sentences are done, and you can
   **Cancel generation** at any time; a cancelled generation leaves no audio behind.
4. When the status says **Audio ready**, play the audio. The current word is highlighted and
   the view follows it. Click any word or sentence to jump there.
5. Download the audio (**WAV**) or subtitles (**SRT** or **VTT**). Files are named after the
   first words of the input and the time of generation, so repeated generations stay distinct.
6. Open **History** to restore or delete recent generations. It keeps the 20 most recent.

The full walkthrough, keyboard shortcuts, and error explanations are in the
[User Guide](docs/USER_GUIDE.md).

## Configuration

All settings are optional environment variables. Read once at startup.

| Variable | Default | Meaning |
|---|---|---|
| `TTS_HOST` | `127.0.0.1` | Bind address. A non-loopback address requires `--i-know-this-is-lan`. |
| `TTS_PORT` | `8321` | Port for the web interface and API. |
| `TTS_DATA_DIR` | See below | Where voices, audio, the database, and logs are stored. |
| `TTS_MAX_INPUT_CHARS` | `50000` | Maximum input length accepted by the API. |
| `TTS_HISTORY_LIMIT` | `20` | Number of generations kept; the oldest is evicted. |
| `TTS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |
| `TTS_DEFAULT_VOICE` | `en_US-lessac-medium` | Voice downloaded on first run and preselected. |
| `TTS_FAULT` | `none` | Test-only fault injection (`engine` makes a generation fail). Leave unset in normal use. |

Command-line flags override the host and port:

```text
tts [--host ADDRESS] [--port PORT] [--no-open] [--i-know-this-is-lan]
tts add-voice NAME
tts --version
```

Examples:

```bash
tts --port 9000              # a different port
tts --no-open                # do not launch a browser
TTS_DATA_DIR=/tmp/tts-demo tts
```

Binding to anything other than a loopback address exposes unauthenticated access to your
library. Only do that on a network you trust, with `--i-know-this-is-lan`.

## Where your data lives

| Platform | Default data directory |
|---|---|
| Windows | `%LOCALAPPDATA%\tts` |
| macOS | `~/Library/Application Support/tts` |
| Linux | `~/.local/share/tts` |

Inside it:

| Path | Contents |
|---|---|
| `voices/` | Installed Piper voice files (`.onnx` and `.onnx.json`). |
| `generations/` | Completed WAV files. Deleted when a generation is deleted or evicted. |
| `library.db` | SQLite database with generation history and saved settings. |
| `logs/tts.log` | Rotating diagnostic log (10 MB, five files). |

Back up `library.db` and the `generations/` folder together: a history row refers to its WAV.
To reset the app, stop it and delete the whole data directory; the next start recreates it and
downloads the default voice again.

## Troubleshooting

| Symptom | What to do |
|---|---|
| `tts` exits with a DLL/access-violation error on Windows | Install the current [VC++ 2015–2022 x64 redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe) and restart the terminal. |
| Browser shows a blank page or only JSON | The frontend was not built. Run `cd frontend && npm ci && npm run build` in the checkout, then restart `tts`. The log line "Frontend build not found; serving the API only" confirms this. |
| "No voices installed" | Run `tts add-voice en_US-lessac-medium` in the same environment (needs internet once), then reload. |
| Port 8321 is already in use | Stop the other process, or start with `tts --port 8322`. |
| Voice download fails | Check your network/proxy, then retry `tts add-voice en_US-lessac-medium`. The app keeps running without a voice; generation is disabled until one is installed. |
| First-run voice download hangs | Stop with `Ctrl+C`, check connectivity or a proxy, then run `tts add-voice en_US-lessac-medium` explicitly. A partial download is never used as a voice. |
| Generation fails | Read the on-screen reason, then check `logs/tts.log` in the data directory. Try a shorter text or a different voice. Failed generations leave no partial audio. |
| Audio downloads but does not play | The file is a standard 16-bit PCM mono WAV. Try a desktop player; browsers without WAV support cannot play it. |
| Upload rejected | Only `.txt` files up to 2 MB are accepted, encoded as UTF-8 or UTF-16. Save the text as plain UTF-8 and retry. |
| Long text feels slow | Synthesis is CPU-only and runs one generation at a time. A 2,000-character text takes roughly 3 seconds on the measured machine; 5,000 characters took about 7–8 seconds. See [Measurements](docs/MEASUREMENTS.md). |
| Word highlighting skips a word | Some words cannot be aligned to their phonemes; they are marked unaligned and the highlight pauses instead of inventing a time. This is expected. |
| Need diagnostics | `logs/tts.log` contains generation start/finish, failures with reasons, and eviction; input text is never logged beyond an 80-character preview. |

## Development

```bash
pip install -e ".[dev]"
(cd frontend && npm ci)
(cd frontend && npm run build)

pytest tests/unit
pytest tests/integration        # needs a real voice; see docs/TASKS.md
(cd frontend && npm test)
(cd frontend && npm run lint && npm run typecheck)
```

For UI work, run the API and Vite separately:

```bash
uvicorn tts.app:create_app --factory --reload --port 8321
cd frontend && npm run dev
```

Vite serves the UI on its own port and proxies `/api` to 8321. `VITE_API_MODE=mock` runs the
UI against in-memory sample data without the backend.

The acceptance suite is Playwright, driven from `frontend/` with the config in `tests/e2e`:

```bash
cd frontend
npx playwright install chromium
npx playwright test --config ../tests/e2e/playwright.config.ts
```

## Documentation

- [User Guide](docs/USER_GUIDE.md) — the workflow, keyboard shortcuts, and error messages.
- [Known Limitations](docs/KNOWN_LIMITATIONS.md) — supported platforms, timing tolerance, retention, and caveats.
- [Measurements](docs/MEASUREMENTS.md) — performance and word-timing numbers with the hardware used.
- [Product Requirements](docs/PRD.md) — what the product must do.
- [Architecture](docs/ARCHITECTURE.md) — how it is built.

## Privacy

The server listens on loopback only and sends no telemetry. Synthesis, storage, playback, and
downloads all happen locally. The one deliberate network use is the voice download during
first-run setup, or when you explicitly run `tts add-voice`.
