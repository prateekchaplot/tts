"""Unit tests for phoneme-alignment reconciliation into word timings."""

from __future__ import annotations

import itertools

import numpy as np
import pytest

from tts.timing.reconcile import derive_word_timings, split_words
from tts.types import SentenceAudio, SynthesisResult
from tts.voices.store import LoadedVoice

SAMPLE_RATE = 1000  # one sample is one millisecond, keeping the arithmetic readable

HELLO = ["h", "ə", "l", "ˈoʊ"]
WORLD = ["w", "ɜː", "l", "d", "."]


class FakeVoice:
    """Re-phonemize words from a fixed table; unknown words yield no phonemes."""

    def __init__(self, phonemes_by_word: dict[str, list[str]]) -> None:
        self.phonemes_by_word = phonemes_by_word
        self.calls: list[str] = []

    def phonemize(self, text: str) -> list[list[str]]:
        self.calls.append(text)
        return [list(self.phonemes_by_word.get(text, []))]


def _loaded(voice: FakeVoice) -> LoadedVoice:
    return LoadedVoice(voice=voice, supports_alignments=True)  # type: ignore[arg-type]


def _sentence(
    text: str,
    alignments: list[tuple[str, int]],
    *,
    sample_count: int | None = None,
    sample_rate: int = SAMPLE_RATE,
    supports_alignments: bool = True,
    char_start: int = 0,
) -> SentenceAudio:
    if sample_count is None:
        sample_count = sum(count for _, count in alignments)
    return SentenceAudio(
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
        samples=np.zeros(sample_count, dtype=np.float32),
        sample_rate=sample_rate,
        phoneme_alignments=alignments,
        supports_alignments=supports_alignments,
    )


def _result(sentences: list[SentenceAudio], *, supports_alignments: bool = True) -> SynthesisResult:
    return SynthesisResult(
        sentences=sentences,
        total_samples=sum(len(sentence.samples) for sentence in sentences),
        sample_rate=SAMPLE_RATE,
        supports_alignments=supports_alignments,
    )


def _hello_world_alignments(scale: int = 100) -> list[tuple[str, int]]:
    return [
        ("h", scale),
        ("ə", scale),
        ("l", scale),
        ("ˈoʊ", scale),
        (" ", scale),
        ("w", scale),
        ("ɜː", scale),
        ("l", scale),
        ("d", scale),
        (".", scale),
    ]


def test_maps_words_to_their_phoneme_spans() -> None:
    voice = FakeVoice({"Hello": HELLO, "world.": WORLD})
    sentence = _sentence("Hello world.", _hello_world_alignments())

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hello", 0, 400, True),
        ("world.", 500, 1000, True),
    ]
    assert ratio == pytest.approx(1.0)
    assert voice.calls == ["Hello", "world."]


def test_boundary_phonemes_offset_words_into_their_real_audio() -> None:
    """Piper's BOS/EOS silence must move word starts, not be discarded.

    Regression: the engine used to drop ``^``/``$``/``_`` alignments, which
    made every word of a sentence start early by the leading silence.
    """
    voice = FakeVoice({"Hello": HELLO, "world.": WORLD})
    sentence = _sentence(
        "Hello world.",
        [
            ("^", 150),
            ("h", 100),
            ("ə", 100),
            ("l", 100),
            ("ˈoʊ", 100),
            (" ", 100),
            ("w", 100),
            ("ɜː", 100),
            ("l", 100),
            ("d", 100),
            (".", 100),
            ("$", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hello", 150, 550, True),
        ("world.", 650, 1150, True),
    ]
    assert ratio == pytest.approx(1.0)


def test_timings_stay_monotonic_across_sentences() -> None:
    voice = FakeVoice({"Hello": HELLO, "world.": WORLD})
    first = _sentence("Hello world.", _hello_world_alignments())
    second = _sentence("Hello world.", _hello_world_alignments(50), char_start=13)

    timings, ratio = derive_word_timings(_loaded(voice), _result([first, second]))

    assert [(word.start_ms, word.end_ms) for word in timings] == [
        (0, 400),
        (500, 1000),
        (1000, 1200),
        (1250, 1500),
    ]
    assert ratio == pytest.approx(1.0)
    assert all(word.aligned for word in timings)
    assert all(earlier.end_ms <= later.start_ms for earlier, later in itertools.pairwise(timings))


def test_expanded_number_matches_as_one_word() -> None:
    voice = FakeVoice(
        {
            "Call": ["k", "ɔː", "l"],
            "42.": ["fˈɔːɹti", "tˈuː", "."],
        }
    )
    sentence = _sentence(
        "Call 42.",
        [
            ("k", 100),
            ("ɔː", 100),
            ("l", 100),
            (" ", 100),
            ("fˈɔːɹti", 100),
            (" ", 100),
            ("tˈuː", 100),
            (".", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Call", 0, 300, True),
        ("42.", 400, 800, True),
    ]
    assert ratio == pytest.approx(1.0)


def test_punctuation_only_token_is_zero_width_after_the_previous_word() -> None:
    voice = FakeVoice({"Hi": ["h", "aɪ"], "—": [], "there.": ["ð", "ɛː", "ɹ", "."]})
    sentence = _sentence(
        "Hi — there.",
        [
            ("h", 100),
            ("aɪ", 100),
            (" ", 100),
            ("ð", 100),
            ("ɛː", 100),
            ("ɹ", 100),
            (".", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hi", 0, 200, True),
        ("—", 200, 200, False),
        ("there.", 300, 700, True),
    ]
    assert ratio == pytest.approx(2 / 3)


def test_emoji_token_is_unaligned_without_inventing_time() -> None:
    voice = FakeVoice({"Party": ["p", "ɑː", "ɾ", "i"], "🎉": [], "time": ["t", "aɪ", "m"]})
    sentence = _sentence(
        "Party 🎉 time",
        [
            ("p", 100),
            ("ɑː", 100),
            ("ɾ", 100),
            ("i", 100),
            (" ", 100),
            ("t", 100),
            ("aɪ", 100),
            ("m", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    emoji = timings[1]
    assert (emoji.text, emoji.start_ms, emoji.end_ms, emoji.aligned) == ("🎉", 400, 400, False)
    assert [word.aligned for word in timings] == [True, False, True]
    assert ratio == pytest.approx(2 / 3)


def test_mismatched_case_degrades_only_the_unmappable_word() -> None:
    voice = FakeVoice(
        {
            "HELLO": ["ʒ", "ʒ", "ʒ"],
            "brave": ["b", "ɹ", "eɪ", "v"],
            "new": ["n", "uː"],
            "world": ["w", "ɜː", "l", "d"],
            "today": ["t", "uː", "d", "eɪ"],
        }
    )
    sentence = _sentence(
        "HELLO brave new world today",
        [
            ("h", 100),
            ("ə", 100),
            ("l", 100),
            ("oʊ", 100),
            (" ", 100),
            ("b", 100),
            ("ɹ", 100),
            ("eɪ", 100),
            ("v", 100),
            (" ", 100),
            ("n", 100),
            ("uː", 100),
            (" ", 100),
            ("w", 100),
            ("ɜː", 100),
            ("l", 100),
            ("d", 100),
            (" ", 100),
            ("t", 100),
            ("uː", 100),
            ("d", 100),
            ("eɪ", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [word.aligned for word in timings] == [False, True, True, True, True]
    assert (timings[0].start_ms, timings[0].end_ms) == (0, 0)
    assert ratio == pytest.approx(0.8)


def test_corrupted_alignments_collapse_the_sentence() -> None:
    voice = FakeVoice({"Hello": HELLO, "world.": WORLD})
    sentence = _sentence(
        "Hello world.",
        [("k", 100), ("k", 100), (" ", 100), ("k", 100)],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hello world.", 0, 400, False)
    ]
    assert ratio == pytest.approx(0.0)


def test_threshold_is_inclusive_at_sixty_percent() -> None:
    voice = FakeVoice(
        {"a": ["a"], "b": ["b"], "c": ["c"], "d": ["x"], "e": ["y"]},
    )
    sentence = _sentence(
        "a b c d e",
        [
            ("a", 100),
            (" ", 100),
            ("b", 100),
            (" ", 100),
            ("c", 100),
            (" ", 100),
            ("d", 100),
            (" ", 100),
            ("e", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert len(timings) == 5
    assert [word.aligned for word in timings] == [True, True, True, False, False]
    assert ratio == pytest.approx(0.6)


def test_below_threshold_collapses_and_ratio_counts_every_token() -> None:
    voice = FakeVoice(
        {
            "Hello": HELLO,
            "world.": WORLD,
            "Bad": ["x"],
            "words": ["y"],
        }
    )
    good = _sentence("Hello world.", _hello_world_alignments())
    bad = _sentence(
        "Bad words",
        [("k", 100), (" ", 100), ("k", 100)],
        char_start=13,
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([good, bad]))

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hello", 0, 400, True),
        ("world.", 500, 1000, True),
        ("Bad words", 1000, 1300, False),
    ]
    assert ratio == pytest.approx(0.5)


def test_whole_synthesis_without_alignments_returns_minus_one() -> None:
    voice = FakeVoice({})
    first = _sentence("Hello world.", [], sample_count=500, supports_alignments=False)
    second = _sentence(
        "Hello world.", [], sample_count=250, supports_alignments=False, char_start=13
    )

    timings, ratio = derive_word_timings(
        _loaded(voice), _result([first, second], supports_alignments=False)
    )

    assert [(word.text, word.start_ms, word.end_ms, word.aligned) for word in timings] == [
        ("Hello world.", 0, 500, False),
        ("Hello world.", 500, 750, False),
    ]
    assert ratio == -1.0
    assert voice.calls == []


def test_empty_synthesis_returns_no_timings() -> None:
    timings, ratio = derive_word_timings(_loaded(FakeVoice({})), _result([]))

    assert timings == []
    assert ratio == -1.0


def test_phonemizer_failure_degrades_only_that_word() -> None:
    class FailingVoice(FakeVoice):
        def phonemize(self, text: str) -> list[list[str]]:
            if text == "bad":
                raise RuntimeError("g2p exploded")
            return super().phonemize(text)

        def __init__(self) -> None:
            super().__init__({"good": ["g", "ʊ", "d"], "bad": [], "word": ["w", "ɜː", "d"]})

    voice = FailingVoice()
    sentence = _sentence(
        "good bad word",
        [
            ("g", 100),
            ("ʊ", 100),
            ("d", 100),
            (" ", 100),
            ("w", 100),
            ("ɜː", 100),
            ("d", 100),
        ],
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([sentence]))

    assert [(word.text, word.aligned) for word in timings] == [
        ("good", True),
        ("bad", False),
        ("word", True),
    ]
    assert (timings[1].start_ms, timings[1].end_ms) == (300, 300)
    assert ratio == pytest.approx(2 / 3)


def test_rounding_keeps_timings_monotonic_with_non_integral_sample_rates() -> None:
    voice = FakeVoice({"aaa": ["a", "a", "a"]})
    first = _sentence("aaa", [("a", 1), ("a", 1), ("a", 1)], sample_count=3, sample_rate=3)
    second = _sentence(
        "aaa",
        [("a", 1), ("a", 1), ("a", 1)],
        sample_count=3,
        sample_rate=7,
        char_start=4,
    )

    timings, ratio = derive_word_timings(_loaded(voice), _result([first, second]))

    assert ratio == pytest.approx(1.0)
    assert all(word.start_ms <= word.end_ms for word in timings)
    assert all(earlier.end_ms <= later.start_ms for earlier, later in itertools.pairwise(timings))


def test_split_words_preserves_input_tokens() -> None:
    assert split_words("Hello, world!  🎉  42") == ["Hello,", "world!", "🎉", "42"]
    assert split_words("   ") == []
