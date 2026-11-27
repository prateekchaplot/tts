# tts User Guide

This guide covers the day-to-day workflow: starting tts, turning text into audio, reading the
subtitles, and exporting files. For installation, see the [README](../README.md).

## Start and stop

Start tts from the environment where it was installed:

```bash
tts
```

It opens `http://127.0.0.1:8321` in your browser. If you do not want a browser window, run
`tts --no-open` and open the address yourself. To use another port, pass `--port`:

```bash
tts --port 8322
```

Stop the server with `Ctrl+C` in the terminal. History, settings, and installed voices survive
restarts because they are stored in the data directory, not in the browser.

On first start, tts installs the default voice (`en_US-lessac-medium`, about 60 MB) if the
voice folder is empty. That download needs internet once. If it fails, the app still opens and
shows how to install a voice with `tts add-voice`.

## The screen

The page is one column, top to bottom:

1. **Text** — paste or type text, or upload a plain-text file.
2. **Voice and settings** — choose an installed voice and adjust rate and volume.
3. **Generate** — start, watch, or cancel a generation.
4. **Playback and subtitles** — play the finished audio with live word highlighting.
5. **History** — reopen or delete recent generations.

Errors appear in a banner above the text area. The banner states what went wrong and what you
can do about it; **Dismiss** closes it.

## Generate audio

### Type or paste text

Click the text box and paste or type. Paragraph breaks are preserved. The counter under the
box shows the current length and the 50,000-character limit. Empty or whitespace-only input is
rejected before a request is sent.

### Upload a text file

Choose **Upload plain text** and pick a `.txt` file. The file's contents replace the editor so
you can review and edit them before generating. Accepted files:

- extension `.txt`;
- plain text content type (or an unknown binary type reported as `application/octet-stream`);
- at most 2 MB;
- UTF-8 (with or without a BOM) or UTF-16 (with a BOM).

Other files are rejected with a message naming the accepted types. PDF, DOCX, Markdown
structure, and other document formats are not supported.

### Choose a voice

The **Voice** list shows every voice installed in the app's voice folder, with its language.
The app's saved default (initially `en_US-lessac-medium`) is preselected. **Preview voice**
plays a short built-in phrase in the selected voice, so you can compare voices before
generating.

If the list is empty, generation is disabled and the page explains how to install a voice.
Voices are installed outside the UI:

```bash
tts add-voice en_US-lessac-medium
```

Voice names come from the Piper catalogue at <https://huggingface.co/rhasspy/piper-voices>.
Reload the page after installing one.

### Adjust rate and volume

| Control | Range | Default | Effect |
|---|---|---|---|
| **Speaking rate** | 0.5–2.0 | 1.0 | Higher is faster. |
| **Volume** | 0.0–1.0 | 1.0 | Output level; 0 is silent. |

Settings are saved when a control loses focus and are reused the next time the app starts.
Values outside the ranges are clamped by the controls and rejected by the server with a
plain-language message; generation never proceeds with an out-of-range value.

Pitch is not adjustable. See [Known Limitations](KNOWN_LIMITATIONS.md#pitch-control).

### Start, watch, and cancel

Choose **Generate audio**. The status line moves through:

| Status | Meaning |
|---|---|
| `Queued. Waiting for the worker.` | Accepted; the single synthesis worker will pick it up. |
| `Generating: N of M sentences done.` | Synthesis is running; the progress bar tracks sentences. |
| `Audio ready.` | The WAV and timings are complete and playable. |
| `Generation failed. See the message above.` | Synthesis failed; no partial audio is kept. |
| `Generation cancelled. No audio was saved.` | You cancelled it, or it was cancelled before finishing. |

Only one generation runs at a time. While it runs, the rest of the page remains usable:
you can read the text, change settings for the next run, or cancel. **Cancel generation**
discards partial output; neither History nor Downloads receives an incomplete file.

A failed or cancelled generation leaves earlier history entries untouched.

## Playback and subtitles

When a generation succeeds, the **Playback and subtitles** section shows:

- **Play/Pause**, **Back 5 s**, **Forward 5 s**, and a seek bar;
- the text with each word as a clickable span;
- a **Sentences** list of caption cues.

### Follow the highlight

During playback the word being spoken is highlighted, and the view scrolls to keep it visible.
Click any word to seek to its start. Click a sentence in the **Sentences** list to jump to that
cue. After the audio ends, the highlight resets.

Some words cannot be aligned to the synthesized phonemes (numbers, symbols, unusual
punctuation, or words the engine pronounces differently). Those words are marked `unaligned`
with an estimated, zero-width time: the highlight pauses rather than showing an invented
position. The line "N% of words timed" reports how much of the generation was aligned. If a
generation has no alignment data at all, the page says so and keeps audio and downloads
available.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Move through controls, including the skip link at the top. |
| `Enter` / `Space` | Activate the focused button or link. |
| `Space` | Play or pause when focus is outside an input, text area, select, or button. |
| `Left` / `Right` arrow | Seek back or forward 5 seconds under the same condition. |
| `Enter` on a sentence cue | Jump to that sentence. |

The browser's native audio controls also respond to the keyboard when focused. Word spans are
mouse targets; the sentence cues are the keyboard path for seeking.

## Downloads

After a generation succeeds, the **Downloads** section offers:

| Button | File |
|---|---|
| **Download audio (WAV)** | 16-bit PCM mono WAV at the voice's sample rate (usually 22,050 Hz). |
| **Download subtitles (SRT)** | SubRip captions with sentence-level cues. |
| **Download subtitles (VTT)** | WebVTT captions with the same cues. |

Names are built from the first up to six words of the input plus the UTC creation time, for
example `hello-world-this-is-a-live_20261123-125257.wav`. Repeated generations of the same text
therefore get distinct names. Cue timings come from the same word timings shown in the
playback view. Downloaded files are complete files; a failed generation produces no downloads.

## History

**History** lists recent generations with an input preview, voice, status, and time. The heading
shows how many are saved. The list keeps the 20 most recent; when you start a new generation,
the oldest entry and its audio file are removed if the limit is exceeded.

- **Open** restores a finished generation's audio and subtitles without regenerating. It does
  not overwrite the text or settings you are currently editing.
- **Delete** starts an inline confirmation: choose **Confirm delete** to remove the entry and
  its audio, or **Keep** to leave it alone. The rest of the list is untouched.
- Failed and cancelled entries stay visible and can be deleted, but not opened. Entries still
  queued or generating cannot be deleted until they finish or are cancelled.

History is stored on the machine, not in the browser, so clearing browser data does not remove
it.

## Errors

Every error banner shows the problem, the server's message, and "What you can do". Common ones:

| Code or message | Meaning and next step |
|---|---|
| `EMPTY_INPUT` | The text is empty or only whitespace. Add text and generate again. |
| `INPUT_TOO_LONG` | The text exceeds 50,000 characters. Shorten it or split it into two generations. |
| `OUT_OF_RANGE` | Rate or volume is outside its range. Use the sliders' allowed values. |
| `VOICE_NOT_FOUND` | The saved voice is no longer installed. Pick another voice, or install it and reload. |
| `NO_VOICES_INSTALLED` | The voice folder is empty. Run `tts add-voice <name>`, then reload. |
| `UNSUPPORTED_FILE_TYPE` | Upload a plain `.txt` file. |
| `FILE_TOO_LARGE` | The upload is over 2 MB. Paste the text or use a smaller file. |
| `DECODE_FAILED` | The file is not UTF-8 or UTF-16 text. Re-save it as UTF-8 and retry. |
| `GENERATION_NOT_READY` | Audio is requested before synthesis finishes. Wait for "Audio ready". |
| `GENERATION_BUSY` | Delete or start was attempted while a generation is active. Finish or cancel it first. |
| `ENGINE_ERROR` | The speech engine failed. Try a shorter text or another voice, then check the log. |
| `INTERNAL_ERROR` | An unexpected server error. Reload and retry; check the log if it repeats. |

The detailed troubleshooting table is in the [README](../README.md#troubleshooting). Logs are in
`logs/tts.log` inside the data directory (`%LOCALAPPDATA%\tts` on Windows,
`~/Library/Application Support/tts` on macOS, `~/.local/share/tts` on Linux).

## Privacy and offline use

Everything after setup runs on your machine: synthesis, timings, playback, and file downloads.
The server accepts connections from loopback only and sends no telemetry. Keep the app offline
after the first-run voice download and the workflow still works.

The only network use is the initial dependency install and voice download, or an explicit
`tts add-voice`. If you need to verify the offline claim, disconnect the network after setup and
repeat input → generate → play → download.

## Managing your data

| Task | Action |
|---|---|
| See where files are kept | Read the [data directory table](../README.md#where-your-data-lives). |
| Free space | Delete old entries in History; eviction also removes audio files. |
| Move to another machine | Copy the whole data directory, including `library.db` and `generations/`, while tts is stopped. |
| Reset everything | Stop tts and delete the data directory. The next start recreates it and reinstalls the default voice. |
| Change the data location | Set `TTS_DATA_DIR` before starting tts. |
