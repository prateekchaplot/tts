"""Derive sentence-level subtitle cues from word timings."""

from __future__ import annotations

from tts.types import Cue, WordTiming

MAX_CUE_CHARS = 84
MAX_CUE_MS = 5_000
MIN_CUE_MS = 1_200


def build_cues(
    words: list[WordTiming],
    sentences: list[tuple[int, int, int]],
    audio_duration_ms: int,
) -> list[Cue]:
    """Group words into caption cues bounded by sentence, length, and duration.

    ``sentences`` holds ``(char_start, char_end, first_word_idx)`` triplets. The
    character offsets are informational — cue text comes from the word timings —
    while ``first_word_idx`` marks where each sentence starts. A cue never spans
    two sentences, and each cue stays within :data:`MAX_CUE_CHARS` characters and
    :data:`MAX_CUE_MS` milliseconds. Every cue is extended to at least
    :data:`MIN_CUE_MS` without overlapping the following cue, and the final cue
    is clamped to the audio duration.
    """
    cues: list[Cue] = []
    for window in _sentence_windows(words, sentences):
        for group in _split_window(window):
            cues.append(
                Cue(
                    index=len(cues) + 1,
                    start_ms=group[0].start_ms,
                    end_ms=group[-1].end_ms,
                    text=" ".join(word.text for word in group),
                )
            )
    return _extend_short_cues(cues, audio_duration_ms)


def _sentence_windows(
    words: list[WordTiming], sentences: list[tuple[int, int, int]]
) -> list[list[WordTiming]]:
    """Slice ``words`` into one window per non-empty sentence."""
    windows: list[list[WordTiming]] = []
    for position, sentence in enumerate(sentences):
        next_start = sentences[position + 1][2] if position + 1 < len(sentences) else len(words)
        start = _clamp_index(sentence[2], len(words))
        end = _clamp_index(max(next_start, start), len(words))
        if end > start:
            windows.append(words[start:end])
    return windows


def _clamp_index(index: int, limit: int) -> int:
    return max(0, min(index, limit))


def _split_window(window: list[WordTiming]) -> list[list[WordTiming]]:
    """Split one sentence's words into cues that respect the size limits.

    A single word that exceeds a limit is kept whole: splitting it would alter
    its text, which caption output must never do.
    """
    groups: list[list[WordTiming]] = []
    current: list[WordTiming] = []
    for word in window:
        if current:
            candidate_chars = (
                sum(len(item.text) for item in current) + len(current) + len(word.text)
            )
            candidate_ms = word.end_ms - current[0].start_ms
            if candidate_chars > MAX_CUE_CHARS or candidate_ms > MAX_CUE_MS:
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def _extend_short_cues(cues: list[Cue], audio_duration_ms: int) -> list[Cue]:
    """Give every cue a readable minimum duration without overlapping the next cue."""
    extended: list[Cue] = []
    last = len(cues) - 1
    for position, cue in enumerate(cues):
        start = cue.start_ms
        end = max(start, min(cue.end_ms, audio_duration_ms)) if position == last else cue.end_ms
        if end - start < MIN_CUE_MS:
            limit = audio_duration_ms if position == last else cues[position + 1].start_ms
            end = min(start + MIN_CUE_MS, max(limit, start))
        extended.append(Cue(index=cue.index, start_ms=start, end_ms=end, text=cue.text))
    return extended
