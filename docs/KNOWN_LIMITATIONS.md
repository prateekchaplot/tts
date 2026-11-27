# Known Limitations

This document records what tts does not do, the measured limits behind its defaults, and the
platform caveats. The numbers come from [Measurements](MEASUREMENTS.md), produced by
`tests/measure.py` on the hardware described there.

## Pitch control

**Pitch is not adjustable.** The PRD listed rate, volume, and pitch; the architecture's approved
deviation **D-1** omits pitch because the Piper engine exposes no pitch parameter. The API, UI,
and database have no pitch field. Speaking rate and volume are fully supported. See the note
under FR-03 in the [PRD](PRD.md#fr-03-speech-settings).

If pitch control is added later, it would require a DSP pitch-shift stage between synthesis and
file writing, plus one API field; it is not part of the MVP.

## Timing tolerance

The agreed tolerance for word-start alignment is **±100 ms**. It was confirmed by measurement:

| Measure | Result |
|---|---|
| Pooled p95 absolute deviation | **15 ms** |
| Median absolute deviation | 5 ms |
| Maximum absolute deviation | 32 ms |
| Measurable word onsets | 160 (of 3,656 word instances across both voices and all runs) |

Only words preceded by sufficient silence can be measured from the waveform (3,005 word
instances were excluded for lacking a silent gap; 491 were unaligned by design). Connected
speech rarely pauses between words, so the sample is biased toward sentence-initial words and
words after punctuation. Every exclusion is counted in
[Measurements](MEASUREMENTS.md#word-start-accuracy); nothing is silently dropped.

The automated figure is a signal-based proxy, not a human judgement. The manual listening
checklist in [Measurements](MEASUREMENTS.md#manual-listening-checklist-ac7) remains the human
spot-check for AC7.

### Words that cannot be aligned

Word timings are derived by reconciling synthesized phonemes with the input tokens. Some tokens
do not reconcile: numbers the engine expands ("42" → "forty two"), symbols, unusual punctuation,
or words pronounced differently from their spelling. Those words are stored as `aligned=false`
with a zero-width estimated time. During playback the highlight pauses instead of showing an
invented position, and the UI reports the percentage of words that were timed. Audio and
subtitles still work. This is the FR-05 honest-degradation path, not a defect.

A sentence with too few aligned words collapses to a single unaligned entry. In that case the
word highlight is empty for the whole sentence and the sentence cue carries the text.

## Performance

Synthesis is CPU-only, single-process, and one generation runs at a time. Numbers on the
measurement machine (16 logical cores, 15.8 GiB RAM, Windows 11, Python 3.12.2, piper-tts 1.8.0,
ONNX Runtime 1.32.0):

| Input | Voice | Audio length | Time until audio is ready (median) |
|---|---|---|---|
| 139 characters | `en_US-lessac-medium` | 7.7 s | 0.42 s |
| 1,999 characters | `en_US-lessac-medium` | 115 s | 2.96 s |
| 1,999 characters | `en_US-amy-medium` | 135 s | 3.21 s |
| 4,975 characters | `en_US-lessac-medium` | 286 s | 6.94 s |
| 4,975 characters | `en_US-amy-medium` | 335 s | 7.82 s |

- Progress events arrived with a pooled p95 gap of **191 ms** between sentences (median 129 ms),
  inside the 250 ms target.
- The UI is not blocked while synthesis runs: work happens in the server process and the
  highlight loop is a binary search per animation frame.
- A slower or busier machine will take longer. The defaults are deliberately conservative; see
  [Configuration](../README.md#configuration) for the environment variables.
- There is no progress percentage inside a sentence, no streaming playback before completion,
  and no priority queue: the WAV is served only after the whole text finishes.
- Submitting while a generation is active is rejected with `GENERATION_BUSY`; cancel the current
  run first.

## History retention and disk use

- History keeps the **20 most recent** generations by default, including failed and cancelled
  attempts. `TTS_HISTORY_LIMIT` changes the number.
- When the limit is exceeded, the oldest row and its WAV are deleted. Active generations are
  never evicted.
- Deleting an entry deletes its audio. There is no trash or undo; the inline confirmation is the
  only guard.
- The database stores the full input text for each generation so History can restore it. Resetting
  the app means deleting the whole data directory.

## Audio format and file size

- The only output format is **16-bit PCM mono WAV** at the voice's sample rate (usually
  22,050 Hz). There are no bitrate, codec, or format options, and no MP3 export.
- Size is roughly **2.6 MB per minute** at 22,050 Hz. Measured files: 4.85 MB for 115 s,
  12.05 MB for 286 s. A maximum-length 50,000-character input can produce a WAV well over
  100 MB; the browser loads the whole blob only for the generation you open.
- Subtitles are generated at sentence-cue granularity for export (SRT and VTT); word timings
  are used for the on-screen highlight but are not exported as word-level captions.
- There is no hand editing of cue boundaries and no burn-in/video rendering.

## Input limits

- Maximum input length: **50,000 characters** (`TTS_MAX_INPUT_CHARS`). The counter warns before
  generation and the server rejects longer input with `INPUT_TOO_LONG`.
- The in-page counter and pre-flight warning mirror the **default** 50,000-character limit. If
  `TTS_MAX_INPUT_CHARS` is changed, the server enforces the new value, but the counter keeps
  showing 50,000; trust the server's `INPUT_TOO_LONG` response in that case.
- Uploads: **`.txt` only**, at most **2 MB**, UTF-8 or UTF-16 with a BOM. PDF, DOCX, EPUB,
  Markdown structure, HTML, and rich text are not parsed; save the plain text first.
- Empty or whitespace-only input is rejected.
- Only voices installed in the app's voice folder are listed. Operating-system voices
  (SAPI, NSSpeechSynthesizer, espeak-ng) are not used.
- Voice installation is a command (`tts add-voice`), not part of the UI.

## First-run setup and network use

- The first start with an empty voice folder downloads the default voice,
  `en_US-lessac-medium`, about **60 MB**, from the Piper voice catalogue. This is the only time
  the application uses the network on its own. Installing or updating dependencies is also an
  online step, done by you with `pip`/`npm`.
- An offline first run is supported: tts starts, generation is disabled, and the page shows the
  exact remedy (`tts add-voice en_US-lessac-medium`). Run it when you have connectivity, then
  reload.
- If the voice download stalls (no file appears in `voices/`), stop the app with `Ctrl+C`, check
  connectivity or a proxy, and run `tts add-voice en_US-lessac-medium` explicitly. A partial
  download is not treated as an installed voice.
- After a voice is installed, input → generate → play → download works with the network
  disconnected. AC14 tests this with request interception.
- Voices are stored under the app's data directory, not shared with other Piper installations
  unless you copy the files.

## Platforms

| Platform | Status | Notes |
|---|---|---|
| Windows 10/11 x64 | **Tested** (local runs and CI unit tests) | Requires the current Microsoft Visual C++ 2015–2022 Redistributable (x64); an old redist crashes ONNX Runtime at import. |
| Linux x64 (glibc 2.28+) | **Tested** (CI unit, integration, and E2E) | The pinned wheels are `manylinux_2_28`. |
| Linux arm64 | Expected to work | `piper-tts` and `onnxruntime` publish arm64 wheels; no CI run yet. |
| macOS 14+ on Apple Silicon | Expected to work | Both wheels exist for arm64; no CI or manual run yet. |
| macOS on Intel | **Not supported** | ONNX Runtime 1.32.0 publishes no macOS x86_64 wheel for Python 3.12. |

- Python **3.12.x only**. Python 3.13 and older versions are outside the pinned stack.
- The frontend is built with Node.js 22 and Vite 7.
- Browsers: the acceptance suite uses Chromium. Current Firefox and Safari are expected to work
  (the app uses standard `EventSource`, `fetch`, and `<audio>`), but they are not covered by CI.
  The browser must support WAV playback.

## Distribution and installation

- This release is installed **from source**. It is not published on PyPI, and a prebuilt wheel
  with the web interface included is not part of this release.
- Use the editable install (`pip install -e .`) from the checkout. A non-editable
  `pip install .` installs the Python package but not the built web interface, so the page is
  blank.
- A source install requires Node.js once to build the interface. Without `frontend/dist`,
  `tts` serves the API only and the page is blank.
- Dependencies are pinned for Python 3.12 and Node 22; newer major versions are untested.
- Upgrades do not rewrite the data directory except for forward-only schema changes. Back up
  `library.db` and `generations/` before downgrading; a database written by a newer version may
  not open in an older one.
- The app manages its own voice folder under the data directory. Voices are not shared with
  other Piper installations unless you copy the files.

## Security and multi-user use

- Single user, no accounts, no authentication, no authorization. The server binds to
  `127.0.0.1` and refuses non-loopback addresses unless `--i-know-this-is-lan` is passed.
- With that flag, anyone who can reach the port can read, generate, download, and delete your
  library. Do not expose it on an untrusted network.
- There is no CSRF token, rate limiting, or per-user isolation; the loopback boundary is the
  security model (architecture A-4).
- Local malware running as your user is outside the threat model.

## Observability and diagnostics

- Logs go to stdout and to `logs/tts.log` (10 MB, five rotations) in the data directory.
- Input text is never logged in full: only an 80-character preview and its length. Timing arrays
  and uploaded file contents are not logged.
- There is no metrics endpoint, no telemetry, and no remote logging.

## Things the MVP deliberately leaves out

- Third-party HTTP API, CLI automation, and SDKs (the UI uses the internal API, but it is not a
  supported public interface).
- Cloud or online voices, voice cloning, and multi-language auto-detection.
- Batch conversion of multiple files.
- Video rendering, burned-in subtitles, or subtitle editing.
- Multi-user access, hosted deployment, and authentication.
- Audio format conversion (MP3, OGG, FLAC) and sample-rate selection.
- Pitch, emphasis, and SSML markup.

See the [PRD](PRD.md) for the product scope and the [Architecture](ARCHITECTURE.md) for the
technical decisions behind these limits.
