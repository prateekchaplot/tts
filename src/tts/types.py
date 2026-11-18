"""Shared in-process data structures exchanged between components."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class SentenceAudio:
    """PCM audio for one sentence plus its raw phoneme sample counts."""

    text: str
    char_start: int
    char_end: int
    samples: np.ndarray
    sample_rate: int
    phoneme_alignments: list[tuple[str, int]]
    supports_alignments: bool


@dataclass(frozen=True)
class SynthesisResult:
    """Full synthesis output for one generation or preview."""

    sentences: list[SentenceAudio]
    total_samples: int
    sample_rate: int
    supports_alignments: bool


@dataclass(frozen=True)
class WordTiming:
    """Word-level timing in milliseconds; serialized with camelCase field names."""

    text: str
    start_ms: int
    end_ms: int
    aligned: bool


@dataclass(frozen=True)
class Cue:
    """Sentence-level subtitle cue; serialized with camelCase field names."""

    index: int
    start_ms: int
    end_ms: int
    text: str
