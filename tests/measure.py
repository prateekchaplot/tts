"""Measure latency and word-start accuracy for ARCHITECTURE.md T5.3.

The script starts the real application in a background uvicorn thread against an
isolated data directory, drives generations through the public HTTP API, and
timestamps the SSE progress events. It then reads the produced WAV, locates each
word's acoustic onset after a silent gap, and reports the deviation from the
reported timing.

Run it from the repository root with the project installed:

    python tests/measure.py --out docs/MEASUREMENTS.md

The data directory defaults to ``.venv/measure-data`` so the user's own library
is never touched. Voice files are seeded from ``.venv/tts-data/voices`` when
that directory exists; otherwise install the requested voices first:

    set TTS_DATA_DIR=.venv\\measure-data
    python -m tts add-voice en_US-lessac-medium
    python -m tts add-voice en_US-amy-medium

The resulting report is ``docs/MEASUREMENTS.md`` (AC7 tolerance, NFR-02
latency, and a manual listening checklist).
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import itertools
import json
import logging
import math
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import numpy as np
import uvicorn

from tts.app import create_app
from tts.config import Settings
from tts.jobs.manager import split_sentences
from tts.voices.store import ensure_data_dirs

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = REPO_ROOT / ".venv" / "measure-data"
DEFAULT_VOICES = ("en_US-lessac-medium", "en_US-amy-medium")

TERMINAL_EVENTS = frozenset({"succeeded", "failed", "cancelled"})

# Onset analysis. A 10 ms RMS frame is small enough to localise an attack and
# large enough to ignore single-sample noise.
FRAME_MS = 10
# A word is measurable only when the reported gap since the previous word and
# the window immediately before it are silent at this threshold.
MIN_GAP_MS = 100
SILENCE_WINDOW_MS = 100
# The onset search starts just before the reported start and ends well past it,
# so an early or late attack is still found.
SEARCH_BACK_MS = 60
SEARCH_FORWARD_MS = 350
# Speech is anything above this share of the clip's 99th-percentile frame RMS,
# with an absolute floor so a very quiet render cannot make noise pass.
SPEECH_FRACTION = 0.04
ABSOLUTE_FLOOR = 0.002

SHORT_TEXT = (
    "Hello world. This is a short measurement of local speech, written to exercise "
    "sentence boundaries. Numbers like 42 and 3.14 stay honest - even an emoji. "
    "The quick brown fox jumps over the lazy dog."
)

PARAGRAPH = (
    "Local speech synthesis keeps every word private. The quick brown fox jumps over "
    "the lazy dog while the morning light moves across the desk. Numbers like 42 and "
    "3.14 stay honest, and punctuation - dashes, commas, and full stops - gives the "
    "reader time to breathe. A second sentence follows so the measurement includes "
    "sentence boundaries and short pauses between clauses. "
)

TEXT_SIZES = (("short", 200), ("target", 2000), ("long", 5000))


@dataclass(frozen=True)
class StreamEvent:
    """One SSE frame with its arrival time relative to the POST."""

    name: str
    payload: dict[str, Any]
    elapsed_ms: float


@dataclass
class OnsetStats:
    """Acoustic-onset deviations for one generation."""

    sentence_deviations_ms: list[float] = field(default_factory=list)
    word_deviations_ms: list[float] = field(default_factory=list)
    measured: int = 0
    excluded: int = 0
    unaligned: int = 0


@dataclass
class SampleWord:
    """A word offered to the human listening checklist."""

    text: str
    start_ms: int
    end_ms: int


@dataclass
class RunMetrics:
    """Everything measured for one generation."""

    voice_id: str
    label: str
    chars: int
    sentences: int
    audio_seconds: float
    wav_bytes: int
    submit_ms: float
    started_ms: float | None
    first_sentence_ms: float | None
    succeeded_ms: float
    audio_ready_ms: float
    sentence_deltas_ms: list[float]
    word_count: int
    aligned_words: int
    onsets: OnsetStats
    checklist: list[SampleWord]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--voices",
        default=",".join(DEFAULT_VOICES),
        help="comma-separated voice ids (default: %(default)s)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="repetitions of the 2,000-character text per voice (default: 3)",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "docs" / "MEASUREMENTS.md"),
        help="markdown report to write (default: docs/MEASUREMENTS.md)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="isolated data directory (default: .venv/measure-data)",
    )
    return parser.parse_args(argv)


# -- setup -------------------------------------------------------------------


def seed_voices(data_dir: Path) -> None:
    """Copy voices from the developer store when the measurement store is empty."""
    target = data_dir / "voices"
    target.mkdir(parents=True, exist_ok=True)
    if any(target.glob("*.onnx")):
        return
    source = REPO_ROOT / ".venv" / "tts-data" / "voices"
    if not source.is_dir():
        return
    for path in source.iterdir():
        if path.is_file():
            shutil.copy2(path, target / path.name)
    print(f"Seeded voices from {source}")


def build_settings(data_dir: Path) -> Settings:
    os.environ["TTS_DATA_DIR"] = str(data_dir)
    os.environ["TTS_FAULT"] = "none"
    os.environ["TTS_LOG_LEVEL"] = "WARNING"
    return Settings.load()


def missing_voices(data_dir: Path, voices: list[str]) -> list[str]:
    voices_dir = data_dir / "voices"
    return [voice for voice in voices if not (voices_dir / f"{voice}.onnx").is_file()]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_server(settings: Settings) -> tuple[uvicorn.Server, threading.Thread, str]:
    """Run the app on an ephemeral port and wait until /api/health answers."""
    port = free_port()
    app = create_app(settings, bootstrap_on_startup=False)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    )
    thread = threading.Thread(target=server.run, name="measure-server", daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        if server.started:
            try:
                health, _ = http_json("GET", f"{base_url}/api/health", timeout=2.0)
                if health.get("status") == "ok":
                    return server, thread, base_url
            except (OSError, RuntimeError):
                pass
        if not thread.is_alive():
            raise RuntimeError("the measurement server exited before it became healthy")
        time.sleep(0.1)
    raise RuntimeError("the measurement server did not become healthy in 60 s")


def stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=15.0)


# -- HTTP --------------------------------------------------------------------


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], float]:
    """Perform a JSON request and return ``(body, elapsed_ms)``."""
    body, elapsed_ms, _ = http_json_timed(method, url, payload, timeout)
    return body, elapsed_ms


def http_json_timed(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> tuple[dict[str, Any], float, float]:
    """Like :func:`http_json`, additionally returning the perf-counter start."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {error.code} {detail}") from error
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return json.loads(raw), elapsed_ms, started


def http_bytes(url: str, timeout: float = 120.0) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read()


def stream_events(url: str, request_started: float, timeout: float = 900.0) -> list[StreamEvent]:
    """Read SSE frames until a terminal event, timestamping each arrival."""
    request = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
    events: list[StreamEvent] = []
    with urllib.request.urlopen(request, timeout=timeout) as response:
        name = ""
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8").rstrip("\r\n")
            if line.startswith("event: "):
                name = line[len("event: ") :]
                continue
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: ") :])
            events.append(
                StreamEvent(
                    name=name,
                    payload=payload,
                    elapsed_ms=(time.perf_counter() - request_started) * 1000.0,
                )
            )
            if name in TERMINAL_EVENTS:
                break
    return events


# -- one generation ----------------------------------------------------------


def run_generation(base_url: str, voice_id: str, text: str, label: str) -> RunMetrics:
    request_body = {"text": text, "voiceId": voice_id, "rate": 1.0, "volume": 1.0}
    created, submit_ms, request_started = http_json_timed(
        "POST", f"{base_url}/api/generations", request_body
    )
    generation_id = str(created["generationId"])

    events = stream_events(f"{base_url}/api/generations/{generation_id}/events", request_started)
    if not events:
        raise RuntimeError(f"{label}/{voice_id}: the event stream closed without a result")
    terminal = events[-1]
    if terminal.name == "failed":
        raise RuntimeError(
            f"{label}/{voice_id}: generation failed with {terminal.payload.get('error')}"
        )
    succeeded = next((event for event in events if event.name == "succeeded"), None)
    if succeeded is None:
        raise RuntimeError(f"{label}/{voice_id}: no succeeded event before {terminal.name}")

    progress = [event for event in events if event.name == "progress"]
    started = next((event for event in progress if "sentenceIndex" in event.payload), None)
    completions = [event for event in progress if int(event.payload.get("sentenceIndex", 0)) >= 1]
    deltas: list[float] = []
    for previous, current in itertools.pairwise(completions):
        deltas.append(current.elapsed_ms - previous.elapsed_ms)
    first_sentence_ms = completions[0].elapsed_ms if completions else None

    detail, _ = http_json("GET", f"{base_url}/api/generations/{generation_id}")
    audio_bytes = http_bytes(f"{base_url}/api/generations/{generation_id}/audio")
    audio_ready_ms = (time.perf_counter() - request_started) * 1000.0

    timings = detail.get("wordTimings") or []
    onsets = analyze_onsets(audio_bytes, timings)
    aligned = sum(1 for timing in timings if bool(timing.get("aligned")))
    return RunMetrics(
        voice_id=voice_id,
        label=label,
        chars=len(text),
        sentences=len(split_sentences(text)),
        audio_seconds=float(detail.get("durationSeconds") or 0.0),
        wav_bytes=len(audio_bytes),
        submit_ms=submit_ms,
        started_ms=started.elapsed_ms if started is not None else None,
        first_sentence_ms=first_sentence_ms,
        succeeded_ms=succeeded.elapsed_ms,
        audio_ready_ms=audio_ready_ms,
        sentence_deltas_ms=deltas,
        word_count=len(timings),
        aligned_words=aligned,
        onsets=onsets,
        checklist=checklist_samples(timings),
    )


def checklist_samples(timings: list[dict[str, Any]]) -> list[SampleWord]:
    """Pick up to four aligned words spread through the generation."""
    aligned = [
        SampleWord(
            text=str(timing.get("text") or ""),
            start_ms=int(timing.get("startMs") or 0),
            end_ms=int(timing.get("endMs") or 0),
        )
        for timing in timings
        if bool(timing.get("aligned")) and int(timing.get("startMs") or 0) >= 1000
    ]
    if not aligned:
        return []
    step = max(1, len(aligned) // 4)
    return aligned[::step][:4]


# -- signal analysis ---------------------------------------------------------


def analyze_onsets(wav_bytes: bytes, timings: list[dict[str, Any]]) -> OnsetStats:
    """Compare each measurable word's reported start with its acoustic onset.

    A word is measurable when it is aligned, at least :data:`MIN_GAP_MS` of the
    reported span before it is silent, and a frame above the speech threshold
    appears within the search window. Everything else is counted as excluded or
    unaligned rather than dropped.
    """
    stats = OnsetStats()
    if not timings:
        return stats
    samples, sample_rate = read_wav(wav_bytes)
    frame_length = max(1, round(sample_rate * FRAME_MS / 1000))
    # 22,050 Hz does not divide into whole 10 ms frames (220.5 samples), so a
    # frame is slightly shorter than FRAME_MS. Converting frame indexes with
    # the exact frame duration keeps a long file from accumulating a scale
    # error: at 115 s, mislabelling a 220-sample frame as 10 ms would invent a
    # 260 ms late drift out of nothing.
    frame_ms = frame_length * 1000.0 / sample_rate
    frames = frame_rms(samples, frame_length)
    if frames.size == 0:
        return stats
    threshold = max(float(np.percentile(frames, 99.0)) * SPEECH_FRACTION, ABSOLUTE_FLOOR)

    sentence_starts = sentence_start_indexes(timings)
    previous_end = 0
    for index, timing in enumerate(timings):
        start_ms = int(timing.get("startMs") or 0)
        end_ms = int(timing.get("endMs") or 0)
        aligned = bool(timing.get("aligned"))
        gap_ms = start_ms - previous_end
        previous_end = max(previous_end, end_ms)
        if not aligned:
            stats.unaligned += 1
            continue
        if index > 0 and gap_ms < MIN_GAP_MS:
            stats.excluded += 1
            continue

        silence_start = max(0, floor_ms(start_ms - SILENCE_WINDOW_MS, frame_ms))
        silence_end = max(silence_start, floor_ms(start_ms, frame_ms))
        silence = frames[silence_start:silence_end]
        if silence.size == 0 or float(np.max(silence)) >= threshold:
            stats.excluded += 1
            continue

        onset_ms = first_frame_above(frames, start_ms, threshold, frame_ms)
        if onset_ms is None:
            stats.excluded += 1
            continue
        deviation_ms = onset_ms - start_ms
        if deviation_ms < -SEARCH_BACK_MS:
            stats.excluded += 1
            continue
        stats.measured += 1
        stats.word_deviations_ms.append(deviation_ms)
        if index in sentence_starts:
            stats.sentence_deviations_ms.append(deviation_ms)
    return stats


def floor_ms(value_ms: float, frame_ms: float) -> int:
    """Convert milliseconds to a frame index, rounding toward zero."""
    return max(0, int(value_ms / frame_ms))


def sentence_start_indexes(timings: list[dict[str, Any]]) -> set[int]:
    """Find the first timing of each sentence by the punctuation before it.

    Word timings keep the source tokens in order and carry their trailing
    punctuation, so a token ending a sentence marks where the next one starts.
    A collapsed (unaligned) sentence entry covers the whole sentence text and
    still ends with that punctuation, which keeps the mapping correct.
    """
    indexes = {0}
    for index in range(1, len(timings)):
        if _ends_sentence(str(timings[index - 1].get("text") or "")):
            indexes.add(index)
    return indexes


def _ends_sentence(text: str) -> bool:
    return text.rstrip("\"'”’)]}").endswith((".", "!", "?", "…"))


def read_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode a 16-bit mono PCM WAV into float samples in ``[-1, 1]``."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        raw = wav_file.readframes(wav_file.getnframes())
    if channels != 1 or sample_width != 2:
        raise RuntimeError(
            f"expected 16-bit mono WAV, got {channels} channel(s) / {sample_width * 8} bit"
        )
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    return samples, frame_rate


def frame_rms(samples: np.ndarray, frame_length: int) -> np.ndarray:
    count = samples.size // frame_length
    if count == 0:
        return np.empty(0, dtype=np.float64)
    trimmed = samples[: count * frame_length].reshape(count, frame_length)
    return np.sqrt(np.mean(np.square(trimmed), axis=1))


def first_frame_above(
    frames: np.ndarray, start_ms: int, threshold: float, frame_ms: float
) -> float | None:
    """Return the first frame's millisecond position above ``threshold``."""
    low = floor_ms(start_ms - SEARCH_BACK_MS, frame_ms)
    high = min(frames.size, floor_ms(start_ms + SEARCH_FORWARD_MS, frame_ms))
    window = frames[low:high]
    above = np.nonzero(window > threshold)[0]
    if above.size == 0:
        return None
    return (low + int(above[0])) * frame_ms


# -- report ------------------------------------------------------------------


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def median_or_none(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def format_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f}"


def package_version(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return "not installed"


def git_revision() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def cpu_name() -> str:
    identifier = os.environ.get("PROCESSOR_IDENTIFIER")
    if identifier:
        return identifier
    processor = platform.processor()
    if processor:
        return processor
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.machine() or "unknown"


def total_ram_gib() -> float | None:
    if sys.platform == "win32":

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return float(status.ullTotalPhys) / (1024.0**3)
        return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, ValueError, OSError):
        return None
    return float(pages * page_size) / (1024.0**3)


def voice_fingerprint(data_dir: Path, voice_id: str) -> str:
    path = data_dir / "voices" / f"{voice_id}.onnx"
    digest = hashlib.sha256()
    with path.open("rb") as voice_file:
        for chunk in iter(lambda: voice_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{path.stat().st_size / (1024.0**2):.1f} MB, sha256 {digest.hexdigest()[:16]}"


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|")


def build_report(
    *,
    runs: list[RunMetrics],
    voices: list[str],
    data_dir: Path,
    texts: dict[str, str],
    repetitions: int,
) -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    ram = total_ram_gib()
    lines: list[str] = [
        "# Measurements",
        "",
        (
            "Generated by `tests/measure.py` (ARCHITECTURE.md T5.3) on "
            f"{generated} at revision `{git_revision()}`."
        ),
        "",
        "## Environment",
        "",
        "| Item | Value |",
        "|---|---|",
        f"| OS | {platform.platform()} |",
        f"| CPU | {cpu_name()} |",
        f"| Logical cores | {os.cpu_count() or 'unknown'} |",
        f"| RAM | {'unknown' if ram is None else f'{ram:.1f} GiB'} |",
        f"| Python | {platform.python_version()} |",
        f"| piper-tts | {package_version('piper-tts')} |",
        f"| onnxruntime | {package_version('onnxruntime')} |",
        f"| numpy | {package_version('numpy')} |",
        "| Server | uvicorn on 127.0.0.1 (ephemeral port), one process, CPU inference |",
        f"| Data directory | `{data_dir}` (isolated from the user library) |",
    ]
    for voice in voices:
        lines.append(f"| Voice `{voice}` | {voice_fingerprint(data_dir, voice)} |")
    lines.extend(
        [
            "",
            "## Method",
            "",
            (
                "- The real application (`create_app`) runs in a background uvicorn thread "
                "with `TTS_FAULT=none`, rate 1.0, and volume 1.0."
            ),
            (
                "- A generation is driven entirely through the HTTP API. Timestamps use "
                "`time.perf_counter()`: submit = POST send to the 202 response; started = "
                "the first `progress` event; first sentence = the first `progress` event "
                "with `sentenceIndex >= 1`; total = POST send to the `succeeded` event; "
                "audio ready = POST send to the completed audio download (the point where "
                "the UI can play)."
            ),
            (
                "- Per-sentence latency is the gap between consecutive completion events; "
                "the first sentence is reported separately because it includes queueing "
                "and model work."
            ),
            "- One warm-up generation per voice loads the model and is excluded.",
            (
                f"- Each voice runs the short text once, the target text {repetitions} "
                "times, and the long text once."
            ),
            (
                "- Word-start deviation: the WAV is split into RMS frames of "
                f"{FRAME_MS} ms rounded to whole samples (220 samples, 9.977 ms, at "
                "22,050 Hz) and the speech threshold is "
                f"{SPEECH_FRACTION:.0%} of the clip's 99th-percentile "
                f"frame RMS (floor {ABSOLUTE_FLOOR}). Frame positions are converted with "
                "the exact frame duration, not a nominal 10 ms, so a long file cannot "
                "accumulate a scale error. A word is measurable when it is "
                f"aligned, at least {MIN_GAP_MS} ms have passed since the previous word, "
                f"and the {SILENCE_WINDOW_MS} ms before its reported start is silent. The "
                "first frame above the threshold between "
                f"{SEARCH_BACK_MS} ms before and {SEARCH_FORWARD_MS} ms after the "
                "reported start is the acoustic onset. Deviation = onset minus reported "
                "start (positive means the highlight leads the voice)."
            ),
            (
                "- Connected speech rarely leaves a silent gap between neighbouring "
                "words, so most measurable words start a sentence or follow a pause. "
                "Sentence-initial words (the previous token ends a sentence) are also "
                "reported separately. Words without a silence gap are counted as "
                "excluded, never silently dropped."
            ),
            (
                "- This is a signal-based proxy for audibility; the manual listening "
                "checklist below is the AC7 human spot-check."
            ),
            "",
            "## Generation latency (one row per run)",
            "",
            (
                "| Voice | Text | Chars | Sentences | Audio s | Submit ms | Started ms | "
                "First sentence ms | Total ms | Audio ready ms | WAV MB | Aligned % |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    for run in runs:
        aligned_percent = 100.0 * run.aligned_words / run.word_count if run.word_count else 0.0
        lines.append(
            f"| `{run.voice_id}` | {run.label} | {run.chars} | {run.sentences} | "
            f"{run.audio_seconds:.2f} | {run.submit_ms:.0f} | "
            f"{format_ms(run.started_ms)} | {format_ms(run.first_sentence_ms)} | "
            f"{run.succeeded_ms:.0f} | {run.audio_ready_ms:.0f} | "
            f"{run.wav_bytes / (1024.0**2):.2f} | {aligned_percent:.1f} |"
        )

    target_label = "target"
    target_chars = len(texts[target_label])
    lines.extend(
        [
            "",
            "## NFR-02 targets",
            "",
            (
                f"Target text: {target_chars} characters, generated {repetitions} times "
                "per voice. The first run of each voice includes any remaining model "
                "warm-up, so medians are reported."
            ),
            "",
            (
                "| Voice | Runs | Audio ready median ms | Total median ms | First sentence "
                "median ms | Per-sentence median ms | Per-sentence p95 ms |"
            ),
            "|---|---|---|---|---|---|---|",
        ]
    )
    for voice in voices:
        target_runs = [run for run in runs if run.voice_id == voice and run.label == target_label]
        if not target_runs:
            continue
        sentence_deltas = [value for run in target_runs for value in run.sentence_deltas_ms]
        p95 = percentile(sentence_deltas, 0.95) if sentence_deltas else None
        lines.append(
            f"| `{voice}` | {len(target_runs)} | "
            f"{format_ms(median_or_none([run.audio_ready_ms for run in target_runs]))} | "
            f"{format_ms(median_or_none([run.succeeded_ms for run in target_runs]))} | "
            f"{format_ms(median_or_none([run.first_sentence_ms for run in target_runs]))} | "
            f"{format_ms(median_or_none(sentence_deltas))} | {format_ms(p95)} |"
        )

    all_deltas = [value for run in runs for value in run.sentence_deltas_ms]
    pooled_p95 = percentile(all_deltas, 0.95) if all_deltas else None
    audio_ready_medians = [
        (
            f"`{voice}` "
            f"{format_ms(median_or_none([run.audio_ready_ms for run in runs if run.voice_id == voice and run.label == target_label]))}"
            " ms"
        )
        for voice in voices
        if any(run.voice_id == voice and run.label == target_label for run in runs)
    ]
    long_totals = [
        (
            f"`{voice}` "
            f"{format_ms(median_or_none([run.succeeded_ms for run in runs if run.voice_id == voice and run.label == 'long']))}"
            " ms"
        )
        for voice in voices
        if any(run.voice_id == voice and run.label == "long" for run in runs)
    ]
    lines.extend(
        [
            "",
            "### NFR-02 verdict",
            "",
            (
                f"- SSE progress latency: pooled p95 {format_ms(pooled_p95)} ms over "
                f"{len(all_deltas)} sentence intervals (median "
                f"{format_ms(median_or_none(all_deltas))} ms); ARCHITECTURE.md section 11 "
                "asks for under 250 ms per sentence."
            ),
            (
                f"- Time-to-first-audio for the {target_chars}-character text: "
                + ", ".join(audio_ready_medians)
                + ". The app serves the finished WAV, so this is also the total synthesis "
                "time; the `First sentence ms` column shows when the first progress event "
                "arrives, which is what the UI displays while the job runs."
            ),
            (
                f"- Long text ({len(texts['long'])} characters, one run per voice): "
                + ", ".join(long_totals)
                + "."
            ),
            "",
            (
                "The main thread is never blocked by synthesis: the work runs in the "
                "server process and the highlight loop is a requestAnimationFrame binary "
                "search. T5.1's AC8 and AC15 specs exercise that in Chromium."
            ),
            "",
            "## Word-start accuracy",
            "",
            (
                "| Voice | Words | Aligned | Measured | Excluded | Unaligned | Mean signed "
                "ms | Median abs ms | p95 abs ms | Max abs ms |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
    )
    pooled_abs: list[float] = []
    pooled_sentence_abs: list[float] = []
    for voice in voices:
        voice_runs = [run for run in runs if run.voice_id == voice]
        deviations = [value for run in voice_runs for value in run.onsets.word_deviations_ms]
        sentence_deviations = [
            value for run in voice_runs for value in run.onsets.sentence_deviations_ms
        ]
        abs_deviations = [abs(value) for value in deviations]
        pooled_abs.extend(abs_deviations)
        pooled_sentence_abs.extend(abs(value) for value in sentence_deviations)
        lines.append(
            f"| `{voice}` | {sum(run.word_count for run in voice_runs)} | "
            f"{sum(run.aligned_words for run in voice_runs)} | "
            f"{sum(run.onsets.measured for run in voice_runs)} | "
            f"{sum(run.onsets.excluded for run in voice_runs)} | "
            f"{sum(run.onsets.unaligned for run in voice_runs)} | "
            f"{format_ms(statistics.mean(deviations) if deviations else None)} | "
            f"{format_ms(median_or_none(abs_deviations))} | "
            f"{format_ms(percentile(abs_deviations, 0.95) if abs_deviations else None)} | "
            f"{format_ms(max(abs_deviations) if abs_deviations else None)} |"
        )
    if pooled_abs:
        lines.append(
            f"| **Pooled** | | | {len(pooled_abs)} | | | | "
            f"{format_ms(median_or_none(pooled_abs))} | "
            f"{format_ms(percentile(pooled_abs, 0.95))} | "
            f"{format_ms(max(pooled_abs))} |"
        )

    target_tolerance = 100.0
    verdict = tolerance_verdict(pooled_abs, pooled_sentence_abs, target_tolerance)
    lines.extend(
        [
            "",
            "### A-3 tolerance verdict",
            "",
            verdict,
            "",
            "## Manual listening checklist (AC7)",
            "",
            (
                "Status: **pending human review**. Play the target text in the app, open "
                "the subtitle word list, and check the words below. The automated table "
                "above measures the same property from the WAV; a large disagreement "
                "between the two is worth investigating."
            ),
            "",
            "| Voice | Word | Start ms | End ms | Within 100 ms? |",
            "|---|---|---|---|---|",
        ]
    )
    for voice in voices:
        candidates = [run for run in runs if run.voice_id == voice and run.label == target_label]
        if not candidates:
            continue
        for sample in candidates[0].checklist:
            lines.append(
                f"| `{voice}` | {escape_cell(sample.text)} | {sample.start_ms} | "
                f"{sample.end_ms} | [ ] |"
            )
    lines.extend(
        [
            "",
            "## Reproduction",
            "",
            "```",
            "set TTS_DATA_DIR=.venv\\measure-data",
            "python -m tts add-voice en_US-lessac-medium",
            "python -m tts add-voice en_US-amy-medium",
            "python tests/measure.py --out docs/MEASUREMENTS.md",
            "```",
            "",
            (
                "On this Windows checkout the command runs from the repository root with "
                "`.venv\\Scripts\\python.exe`. The script seeds the measurement data "
                "directory from `.venv/tts-data/voices` when it is empty and never touches "
                "the user's `%LOCALAPPDATA%\\tts` library."
            ),
            "",
            "## Notes and caveats",
            "",
            (
                "- Piper's duration predictor is stochastic (T1.2 measured about 1.73x "
                "instead of the nominal 2x at rate 0.5), so latency and duration vary run "
                "to run; medians are reported, not single samples."
            ),
            (
                "- The onset detector needs a silent gap, so it measures words that start a "
                "sentence or follow a pause far more often than words inside a clause. "
                "Excluded words are counted in the table rather than hidden."
            ),
            (
                "- Words whose phonemes do not reconcile are `aligned=false` with a "
                "zero-width span and are counted as unaligned, not as a measurement."
            ),
            (
                "- Measurements are CPU-only and single-process, with the voice cache warm "
                "after the per-voice warm-up run. A busy machine shifts the latency columns."
            ),
            (
                "- The tolerance verdict is signal-based, not a human judgement; the "
                "checklist above remains the AC7 manual step."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def tolerance_verdict(pooled_abs: list[float], sentence_abs: list[float], target_ms: float) -> str:
    """Explain whether A-3's word-start tolerance is confirmed."""
    if not pooled_abs:
        return (
            f"No word had a measurable silent gap, so the tolerance stays at A-3's "
            f"+-{target_ms:.0f} ms pending the human listening check."
        )
    p95 = percentile(pooled_abs, 0.95)
    sentence_p95 = percentile(sentence_abs, 0.95) if sentence_abs else None
    detail = (
        f"{len(pooled_abs)} measurable words (sentence-initial p95 {format_ms(sentence_p95)} ms)"
    )
    if p95 <= target_ms:
        return (
            f"A-3's +-{target_ms:.0f} ms word-start tolerance is confirmed: the pooled "
            f"p95 absolute deviation is {p95:.0f} ms over {detail}."
        )
    suggested = math.ceil(p95 / 25.0) * 25
    return (
        f"A-3's +-{target_ms:.0f} ms tolerance is not confirmed: the pooled p95 absolute "
        f"deviation is {p95:.0f} ms over {detail}. Revise the target upward (for example "
        f"to +-{suggested:.0f} ms) with this table as the justification, and update "
        "`tests/e2e/support/env.ts` in a follow-up."
    )


# -- main --------------------------------------------------------------------


def build_texts(repetitions: int) -> list[tuple[str, str, int]]:
    return [
        (label, repeat_to(PARAGRAPH, size), repetitions if label == "target" else 1)
        for label, size in TEXT_SIZES
    ]


def repeat_to(paragraph: str, target_chars: int) -> str:
    parts: list[str] = []
    length = 0
    while length < target_chars:
        parts.append(paragraph)
        length += len(paragraph)
    joined = " ".join(parts).strip()
    if len(joined) <= target_chars:
        return joined
    cut = joined.rfind(". ", 0, target_chars)
    return joined[: cut + 1] if cut != -1 else joined[:target_chars]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    seed_voices(data_dir)
    voices = [voice.strip() for voice in args.voices.split(",") if voice.strip()]
    missing = missing_voices(data_dir, voices)
    if missing:
        print(
            "Missing voices in the measurement store: "
            + ", ".join(missing)
            + "\nInstall them with:\n  set TTS_DATA_DIR="
            + str(data_dir)
            + "\n  python -m tts add-voice "
            + " ".join("<name>" for _ in missing),
            file=sys.stderr,
        )
        return 2
    if args.runs < 1:
        print("--runs must be at least 1", file=sys.stderr)
        return 2

    settings = build_settings(data_dir)
    ensure_data_dirs(settings)
    server, thread, base_url = start_server(settings)
    runs: list[RunMetrics] = []
    texts = build_texts(args.runs)
    text_lookup = {label: text for label, text, _ in texts}
    try:
        print(f"Measuring against {base_url} (voices: {', '.join(voices)})")
        for voice in voices:
            print(f"  warm-up: {voice}")
            run_generation(base_url, voice, SHORT_TEXT, "warm-up")
        for voice in voices:
            for label, text, repetitions in texts:
                for index in range(repetitions):
                    print(f"  {voice} / {label} / run {index + 1}")
                    runs.append(run_generation(base_url, voice, text, label))
    finally:
        stop_server(server, thread)

    report = build_report(
        runs=runs,
        voices=voices,
        data_dir=data_dir,
        texts=text_lookup,
        repetitions=args.runs,
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8", newline="\n")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
