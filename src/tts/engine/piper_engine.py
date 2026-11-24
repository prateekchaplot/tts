"""Synthesize text into PCM sentences with per-phoneme sample counts."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

from tts.types import SentenceAudio, SynthesisResult

if TYPE_CHECKING:
    from piper import AudioChunk, SynthesisConfig

    from tts.voices.store import LoadedVoice


def synthesize(
    voice: LoadedVoice,
    text: str,
    char_offset_map: list[tuple[int, int]],
    rate: float,
    volume: float,
    cancel_event: threading.Event,
    on_sentence: Callable[[SentenceAudio], None],
) -> SynthesisResult:
    """Synthesize each caller-supplied sentence span of ``text`` in order.

    ``char_offset_map`` is the sentence segmentation: one ``(char_start,
    char_end)`` pair per sentence, in source order. The engine never splits
    text itself; invalid or overlapping spans raise :class:`ValueError`.

    ``cancel_event`` is checked before each sentence, so an event set before
    the first sentence yields an empty result and a later event returns the
    sentences produced so far.
    """
    from piper import SynthesisConfig

    _validate_offsets(text, char_offset_map)
    syn_config = SynthesisConfig(length_scale=1.0 / rate, volume=volume)

    sentences: list[SentenceAudio] = []
    for char_start, char_end in char_offset_map:
        if cancel_event.is_set():
            break
        sentence_text = text[char_start:char_end]
        samples, sample_rate, alignments, supports_alignments = _synthesize_segment(
            voice, sentence_text, syn_config
        )
        sentence = SentenceAudio(
            text=sentence_text,
            char_start=char_start,
            char_end=char_end,
            samples=samples,
            sample_rate=sample_rate,
            phoneme_alignments=alignments,
            supports_alignments=supports_alignments,
        )
        sentences.append(sentence)
        on_sentence(sentence)

    return SynthesisResult(
        sentences=sentences,
        total_samples=sum(len(sentence.samples) for sentence in sentences),
        sample_rate=voice.voice.config.sample_rate,
        supports_alignments=voice.supports_alignments,
    )


def _validate_offsets(text: str, char_offset_map: list[tuple[int, int]]) -> None:
    """Reject a segmentation that is empty, out of bounds, or overlapping."""
    previous_end = 0
    for char_start, char_end in char_offset_map:
        if not 0 <= char_start < char_end <= len(text):
            raise ValueError(
                f"invalid sentence span ({char_start}, {char_end}) for text of length {len(text)}"
            )
        if char_start < previous_end:
            raise ValueError(f"overlapping sentence span ({char_start}, {char_end})")
        previous_end = char_end


def _synthesize_segment(
    voice: LoadedVoice, text: str, syn_config: SynthesisConfig
) -> tuple[np.ndarray, int, list[tuple[str, int]], bool]:
    """Render one sentence span, combining chunks if piper yields more than one."""
    sample_arrays: list[np.ndarray] = []
    alignments: list[tuple[str, int]] = []
    sample_rate = voice.voice.config.sample_rate
    supports_alignments = voice.supports_alignments

    for chunk in voice.voice.synthesize(text, syn_config=syn_config, include_alignments=True):
        sample_arrays.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
        sample_rate = chunk.sample_rate
        chunk_alignments = _chunk_alignments(chunk)
        if chunk_alignments:
            alignments.extend(chunk_alignments)
        else:
            supports_alignments = False

    if not sample_arrays:
        supports_alignments = False
        samples = np.zeros(0, dtype=np.float32)
    else:
        samples = np.concatenate(sample_arrays)

    return samples, sample_rate, alignments, supports_alignments


def _chunk_alignments(chunk: AudioChunk) -> list[tuple[str, int]]:
    """Return every phoneme sample count, boundary markers included.

    Piper's BOS/EOS/pad entries carry the leading and trailing silence of a
    sentence. ``timing/reconcile`` skips them when matching words but still
    advances its sample cursor by their durations, so dropping them here would
    shift every word of the sentence earlier by the leading silence.
    """
    if not chunk.phoneme_alignments:
        return []
    return [
        (alignment.phoneme, int(alignment.num_samples)) for alignment in chunk.phoneme_alignments
    ]
