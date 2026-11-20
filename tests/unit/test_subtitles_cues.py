"""Unit tests for the subtitle cue builder."""

from __future__ import annotations

from tts.subtitles.cues import MAX_CUE_CHARS, MAX_CUE_MS, MIN_CUE_MS, build_cues
from tts.types import WordTiming


def _word(text: str, start_ms: int, end_ms: int, *, aligned: bool = True) -> WordTiming:
    return WordTiming(text=text, start_ms=start_ms, end_ms=end_ms, aligned=aligned)


def _words(*specs: tuple[str, int, int]) -> list[WordTiming]:
    return [_word(text, start, end) for text, start, end in specs]


def test_empty_input_yields_no_cues() -> None:
    assert build_cues([], [], 0) == []


def test_words_without_sentences_yield_no_cues() -> None:
    words = _words(("Hello", 0, 400), ("world", 400, 900))

    assert build_cues(words, [], 900) == []


def test_cue_never_crosses_a_sentence_boundary() -> None:
    words = _words(
        ("Hello", 0, 400),
        ("there.", 400, 900),
        ("General", 1400, 1900),
        ("Kenobi!", 1900, 2400),
    )
    sentences = [(0, 12, 0), (13, 27, 2)]

    cues = build_cues(words, sentences, 2400)

    assert [cue.text for cue in cues] == ["Hello there.", "General Kenobi!"]
    assert [cue.index for cue in cues] == [1, 2]


def test_empty_sentence_triplet_is_skipped() -> None:
    words = _words(("Hello", 0, 400), ("world", 400, 900))
    sentences = [(0, 5, 0), (6, 11, 0)]

    cues = build_cues(words, sentences, 900)

    assert len(cues) == 1
    assert cues[0].text == "Hello world"


def test_sentence_index_beyond_word_count_is_ignored() -> None:
    words = _words(("Hello", 0, 400))
    sentences = [(0, 5, 7)]

    assert build_cues(words, sentences, 400) == []


def test_long_sentence_splits_at_word_boundaries_under_char_limit() -> None:
    words = [_word(f"word{index:02d}", index * 200, index * 200 + 200) for index in range(14)]
    sentences = [(0, 14 * 7, 0)]

    cues = build_cues(words, sentences, 2800)

    word_starts = {word.start_ms for word in words}
    assert len(cues) > 1
    assert all(len(cue.text) <= MAX_CUE_CHARS for cue in cues)
    assert " ".join(cue.text for cue in cues) == " ".join(word.text for word in words)
    assert all(cue.start_ms in word_starts for cue in cues)
    assert cues[0].start_ms == words[0].start_ms
    assert cues[-1].end_ms == words[-1].end_ms


def test_long_sentence_splits_under_duration_limit() -> None:
    words = [_word(f"word{index}", index * 1000, index * 1000 + 1000) for index in range(6)]
    sentences = [(0, 30, 0)]

    cues = build_cues(words, sentences, 6000)

    assert len(cues) == 2
    assert all(cue.end_ms - cue.start_ms <= MAX_CUE_MS for cue in cues)
    assert [cue.text for cue in cues] == ["word0 word1 word2 word3 word4", "word5"]


def test_short_cue_is_extended_to_minimum_duration() -> None:
    words = _words(("Hi", 0, 200))

    cues = build_cues(words, [(0, 2, 0)], 2000)

    assert cues[0].start_ms == 0
    assert cues[0].end_ms == MIN_CUE_MS


def test_extension_is_capped_at_next_cue_start() -> None:
    words = _words(("Hi", 0, 200), ("there", 500, 900))
    sentences = [(0, 2, 0), (3, 8, 1)]

    cues = build_cues(words, sentences, 2000)

    assert cues[0].end_ms == 500
    assert cues[0].end_ms == cues[1].start_ms


def test_last_cue_is_capped_at_audio_duration() -> None:
    words = _words(("Hi", 0, 900))

    cues = build_cues(words, [(0, 2, 0)], 800)

    assert cues[0].start_ms == 0
    assert cues[0].end_ms == 800


def test_last_cue_extension_is_capped_at_audio_duration() -> None:
    words = _words(("Hi", 0, 900))

    cues = build_cues(words, [(0, 2, 0)], 1000)

    assert cues[0].end_ms == 1000


def test_oversized_single_word_is_not_split() -> None:
    long_word = "x" * (MAX_CUE_CHARS + 20)
    words = _words((long_word, 0, 6000))

    cues = build_cues(words, [(0, len(long_word), 0)], 6000)

    assert len(cues) == 1
    assert cues[0].text == long_word
    assert cues[0].end_ms == 6000


def test_degraded_zero_width_words_are_kept_in_cue_text() -> None:
    words = [
        _word("Hello", 0, 400),
        _word("🙂", 400, 400, aligned=False),
        _word("world", 400, 900, aligned=False),
    ]

    cues = build_cues(words, [(0, 13, 0)], 900)

    assert cues[0].text == "Hello 🙂 world"
