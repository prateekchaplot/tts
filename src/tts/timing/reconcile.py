"""Convert per-phoneme sample counts into honest word-level timings."""

from __future__ import annotations

import difflib
import logging
import math
import re
from typing import TYPE_CHECKING

from tts.types import SentenceAudio, SynthesisResult, WordTiming

if TYPE_CHECKING:
    from tts.voices.store import LoadedVoice

logger = logging.getLogger(__name__)

# A word token is a run of non-whitespace; punctuation and emoji stay attached
# to the tokens they belong to so subtitle text matches the input exactly.
_WORD_PATTERN = re.compile(r"\S+")

# Piper's BOS/EOS/pad markers and espeak's word separator never correspond to
# spoken text; dropping the separator keeps number expansions ("42" becomes two
# espeak words) matchable as one contiguous run.
_SKIPPED_PHONEMES = frozenset({"^", "$", "_", " "})

# A sentence whose words cannot be mapped below this share of its tokens is
# collapsed to one unaligned entry instead of showing a drifting highlight.
MIN_SENTENCE_ALIGNMENT_RATIO = 0.6

# Share of a word's phonemes that must match the sentence's alignment run
# before the word counts as aligned.
MIN_WORD_MATCH_RATIO = 0.6


def split_words(text: str) -> list[str]:
    """Split text into word tokens using the same rule as the reconciler."""
    return _WORD_PATTERN.findall(text)


def derive_word_timings(
    voice: LoadedVoice, result: SynthesisResult
) -> tuple[list[WordTiming], float]:
    """Map phoneme sample counts to word timings in milliseconds.

    Returned timings are ordered, monotonic, and confined to their sentence's
    audio span. Words that cannot be placed honestly are emitted with
    ``aligned=False`` and a zero-width span after the previous word; a sentence
    whose words cannot be mapped below ``MIN_SENTENCE_ALIGNMENT_RATIO``
    collapses to one unaligned entry spanning that sentence. The second value
    is the aligned word ratio in ``[0, 1]``, or ``-1.0`` when the whole
    synthesis ran without alignments.
    """
    if not result.sentences:
        return [], -1.0

    timings: list[WordTiming] = []
    aligned_words = 0
    total_words = 0
    previous_end_ms = 0
    elapsed_ms = 0.0

    for sentence in result.sentences:
        words = split_words(sentence.text)
        total_words += len(words)

        duration_ms = _duration_ms(sentence)
        sentence_start_ms = _round_ms(elapsed_ms)
        elapsed_ms += duration_ms
        sentence_end_ms = _round_ms(elapsed_ms)

        sentence_timings: list[WordTiming]
        sentence_aligned: int
        if result.supports_alignments:
            sentence_timings, sentence_aligned = _sentence_timings(
                voice, sentence, sentence_start_ms, sentence_end_ms, words
            )
        else:
            # The engine reported degraded output: never fabricate placements.
            sentence_timings, sentence_aligned = [], 0
        ratio = sentence_aligned / len(words) if words else 1.0
        if not words or ratio < MIN_SENTENCE_ALIGNMENT_RATIO:
            sentence_timings = [
                _collapsed_sentence_timing(sentence, sentence_start_ms, sentence_end_ms)
            ]
            sentence_aligned = 0

        for timing in sentence_timings:
            start_ms = max(timing.start_ms, previous_end_ms)
            end_ms = max(timing.end_ms, start_ms)
            timings.append(
                WordTiming(
                    text=timing.text,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    aligned=timing.aligned,
                )
            )
            previous_end_ms = end_ms
        aligned_words += sentence_aligned

    if not result.supports_alignments:
        aligned_ratio = -1.0
    elif total_words == 0:
        aligned_ratio = 0.0
    else:
        aligned_ratio = aligned_words / total_words

    logger.debug(
        "Reconciled %d/%d words across %d sentences (ratio %.3f)",
        aligned_words,
        total_words,
        len(result.sentences),
        aligned_ratio,
    )
    return timings, aligned_ratio


def _duration_ms(sentence: SentenceAudio) -> float:
    if sentence.sample_rate <= 0:
        return 0.0
    return len(sentence.samples) * 1000.0 / sentence.sample_rate


def _round_ms(value: float) -> int:
    return math.floor(value + 0.5)


def _samples_to_ms(samples: int, sample_rate: int) -> int:
    return _round_ms(samples * 1000.0 / sample_rate)


def _collapsed_sentence_timing(sentence: SentenceAudio, start_ms: int, end_ms: int) -> WordTiming:
    text = sentence.text.strip() or sentence.text
    return WordTiming(text=text, start_ms=start_ms, end_ms=end_ms, aligned=False)


def _sentence_timings(
    voice: LoadedVoice,
    sentence: SentenceAudio,
    sentence_start_ms: int,
    sentence_end_ms: int,
    words: list[str],
) -> tuple[list[WordTiming], int]:
    """Place each word of one sentence; return its timings and aligned count."""
    if not words or not _has_usable_alignments(sentence):
        return [], 0

    phoneme_texts: list[str] = []
    phoneme_starts: list[int] = []
    phoneme_ends: list[int] = []
    cursor_samples = 0
    for phoneme, sample_count in sentence.phoneme_alignments:
        count = max(0, sample_count)
        if phoneme not in _SKIPPED_PHONEMES:
            phoneme_texts.append(phoneme)
            phoneme_starts.append(cursor_samples)
            phoneme_ends.append(cursor_samples + count)
        cursor_samples += count
    if cursor_samples <= 0:
        return [], 0

    timings: list[WordTiming] = []
    aligned_count = 0
    cursor = 0
    previous_end_ms = sentence_start_ms

    for word in words:
        word_phonemes = _phonemize_word(voice, word)
        matched = False
        start_ms = previous_end_ms
        end_ms = previous_end_ms

        if word_phonemes and cursor < len(phoneme_texts):
            matcher = difflib.SequenceMatcher(
                None, phoneme_texts[cursor:], word_phonemes, autojunk=False
            )
            match = matcher.find_longest_match(
                0, len(phoneme_texts) - cursor, 0, len(word_phonemes)
            )
            required = max(1, math.ceil(len(word_phonemes) * MIN_WORD_MATCH_RATIO))
            if match.size >= required:
                first = cursor + match.a
                last = first + match.size - 1
                start_ms = sentence_start_ms + _samples_to_ms(
                    phoneme_starts[first], sentence.sample_rate
                )
                end_ms = sentence_start_ms + _samples_to_ms(
                    phoneme_ends[last], sentence.sample_rate
                )
                cursor = first + match.size
                matched = True

        start_ms = max(start_ms, previous_end_ms)
        end_ms = min(max(end_ms, start_ms), max(sentence_end_ms, start_ms))
        timings.append(WordTiming(text=word, start_ms=start_ms, end_ms=end_ms, aligned=matched))
        if matched:
            aligned_count += 1
        previous_end_ms = end_ms

    return timings, aligned_count


def _has_usable_alignments(sentence: SentenceAudio) -> bool:
    return (
        sentence.supports_alignments
        and bool(sentence.phoneme_alignments)
        and len(sentence.samples) > 0
        and sentence.sample_rate > 0
    )


def _phonemize_word(voice: LoadedVoice, word: str) -> list[str]:
    """Re-phonemize one word in isolation, using the voice's own G2P."""
    try:
        groups = voice.voice.phonemize(word)
    except Exception:  # noqa: BLE001 - a failed word degrades instead of aborting
        logger.debug("Word skipped because phonemization failed")
        return []
    return [phoneme for group in groups for phoneme in group if phoneme not in _SKIPPED_PHONEMES]
