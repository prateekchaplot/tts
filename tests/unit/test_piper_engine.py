"""Unit tests for the Piper engine wrapper using a fake voice."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from types import ModuleType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from tts.engine.piper_engine import synthesize
from tts.types import SentenceAudio
from tts.voices.store import LoadedVoice

SAMPLE_RATE = 22_050


@pytest.fixture(autouse=True)
def fake_piper(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests off onnxruntime; the integration suite uses the real piper."""
    module = ModuleType("piper")

    @dataclass(frozen=True)
    class SynthesisConfig:
        length_scale: float | None = None
        noise_scale: float | None = None
        noise_w_scale: float | None = None
        normalize_audio: bool = True
        volume: float = 1.0

    module.SynthesisConfig = SynthesisConfig  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "piper", module)


@dataclass(frozen=True)
class FakeAlignment:
    phoneme: str
    num_samples: int


@dataclass(frozen=True)
class FakeChunk:
    audio_float_array: np.ndarray
    phoneme_alignments: list[FakeAlignment] | None
    sample_rate: int = SAMPLE_RATE
    sample_width: int = 2
    sample_channels: int = 1


class FakeVoice:
    """Stands in for PiperVoice: one list of chunks per input text."""

    def __init__(self, chunks_by_text: dict[str, list[FakeChunk]]) -> None:
        self.chunks_by_text = chunks_by_text
        self.config = SimpleNamespace(sample_rate=SAMPLE_RATE)
        self.calls: list[tuple[str, Any, bool]] = []

    def synthesize(
        self,
        text: str,
        syn_config: Any = None,
        include_alignments: bool = False,
    ) -> Any:
        self.calls.append((text, syn_config, include_alignments))
        yield from self.chunks_by_text.get(text, [])


def _loaded(voice: FakeVoice, supports_alignments: bool = True) -> LoadedVoice:
    return LoadedVoice(voice=voice, supports_alignments=supports_alignments)  # type: ignore[arg-type]


def _chunk(samples: list[float], alignments: list[FakeAlignment] | None) -> FakeChunk:
    return FakeChunk(
        audio_float_array=np.array(samples, dtype=np.float32), phoneme_alignments=alignments
    )


def test_maps_each_segment_to_a_sentence_with_offsets() -> None:
    text = "Hello. World!"
    voice = FakeVoice(
        {
            "Hello.": [
                _chunk(
                    [0.1, 0.2],
                    [
                        FakeAlignment("^", 1),
                        FakeAlignment("h", 1),
                        FakeAlignment("$", 1),
                    ],
                )
            ],
            "World!": [_chunk([0.3, 0.4, 0.5], [FakeAlignment("w", 3)])],
        }
    )
    seen: list[SentenceAudio] = []

    result = synthesize(
        _loaded(voice),
        text,
        [(0, 6), (7, 13)],
        rate=1.0,
        volume=1.0,
        cancel_event=threading.Event(),
        on_sentence=seen.append,
    )

    assert [sentence.text for sentence in result.sentences] == ["Hello.", "World!"]
    assert [(sentence.char_start, sentence.char_end) for sentence in result.sentences] == [
        (0, 6),
        (7, 13),
    ]
    assert [sentence.sample_rate for sentence in result.sentences] == [SAMPLE_RATE, SAMPLE_RATE]
    assert [len(sentence.samples) for sentence in result.sentences] == [2, 3]
    assert result.total_samples == 5
    assert result.sample_rate == SAMPLE_RATE
    assert result.supports_alignments is True
    assert seen == result.sentences
    assert all(sentence.samples.dtype == np.float32 for sentence in result.sentences)

    assert result.sentences[0].phoneme_alignments == [("h", 1)]
    assert result.sentences[0].supports_alignments is True
    assert result.sentences[1].phoneme_alignments == [("w", 3)]


def test_combines_multiple_chunks_for_one_segment() -> None:
    voice = FakeVoice(
        {
            "One sentence.": [
                _chunk([0.1], [FakeAlignment("w", 1)]),
                _chunk([0.2, 0.3], [FakeAlignment("x", 2), FakeAlignment("_", 1)]),
            ]
        }
    )

    result = synthesize(
        _loaded(voice),
        "One sentence.",
        [(0, 13)],
        rate=1.0,
        volume=1.0,
        cancel_event=threading.Event(),
        on_sentence=lambda sentence: None,
    )

    sentence = result.sentences[0]
    assert sentence.samples.tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert sentence.phoneme_alignments == [("w", 1), ("x", 2)]
    assert result.total_samples == 3


def test_segment_without_audio_is_kept_as_empty_sentence() -> None:
    voice = FakeVoice({})

    result = synthesize(
        _loaded(voice),
        "...",
        [(0, 3)],
        rate=1.0,
        volume=1.0,
        cancel_event=threading.Event(),
        on_sentence=lambda sentence: None,
    )

    sentence = result.sentences[0]
    assert sentence.text == "..."
    assert sentence.samples.size == 0
    assert sentence.samples.dtype == np.float32
    assert sentence.phoneme_alignments == []
    assert sentence.supports_alignments is False
    assert result.total_samples == 0


def test_marks_sentence_degraded_when_alignment_is_missing() -> None:
    voice = FakeVoice({"Hi.": [_chunk([0.1], None)]})

    result = synthesize(
        _loaded(voice),
        "Hi.",
        [(0, 3)],
        rate=1.0,
        volume=1.0,
        cancel_event=threading.Event(),
        on_sentence=lambda sentence: None,
    )

    assert result.sentences[0].supports_alignments is False
    assert result.sentences[0].phoneme_alignments == []
    assert result.supports_alignments is True


def test_cancel_before_first_segment_returns_empty_result() -> None:
    voice = FakeVoice({"Hello.": [_chunk([0.1], [FakeAlignment("h", 1)])]})
    cancel_event = threading.Event()
    cancel_event.set()
    seen: list[SentenceAudio] = []

    result = synthesize(
        _loaded(voice),
        "Hello.",
        [(0, 6)],
        rate=1.0,
        volume=1.0,
        cancel_event=cancel_event,
        on_sentence=seen.append,
    )

    assert result.sentences == []
    assert result.total_samples == 0
    assert seen == []
    assert voice.calls == []


def test_cancel_between_segments_returns_partial_result() -> None:
    voice = FakeVoice(
        {
            "Hello.": [_chunk([0.1, 0.2], [FakeAlignment("h", 2)])],
            "World.": [_chunk([0.3], [FakeAlignment("w", 1)])],
        }
    )
    cancel_event = threading.Event()
    seen: list[str] = []

    def on_sentence(sentence: SentenceAudio) -> None:
        seen.append(sentence.text)
        cancel_event.set()

    result = synthesize(
        _loaded(voice),
        "Hello. World.",
        [(0, 6), (7, 13)],
        rate=1.0,
        volume=1.0,
        cancel_event=cancel_event,
        on_sentence=on_sentence,
    )

    assert [sentence.text for sentence in result.sentences] == ["Hello."]
    assert result.total_samples == 2
    assert seen == ["Hello."]
    assert [call[0] for call in voice.calls] == ["Hello."]


def test_maps_rate_and_volume_to_synthesis_config() -> None:
    voice = FakeVoice({"Hi.": [_chunk([0.1], [FakeAlignment("h", 1)])]})

    synthesize(
        _loaded(voice),
        "Hi.",
        [(0, 3)],
        rate=0.5,
        volume=0.4,
        cancel_event=threading.Event(),
        on_sentence=lambda sentence: None,
    )

    _, syn_config, include_alignments = voice.calls[0]
    assert syn_config.length_scale == 2.0
    assert syn_config.volume == 0.4
    assert include_alignments is True


def test_invalid_offsets_are_rejected_before_synthesis() -> None:
    voice = FakeVoice({})
    cases = [
        [(-1, 3)],
        [(0, 11)],
        [(3, 3)],
        [(5, 2)],
        [(0, 4), (3, 6)],
    ]

    for offsets in cases:
        with pytest.raises(ValueError):
            synthesize(
                _loaded(voice),
                "Hello.",
                offsets,
                rate=1.0,
                volume=1.0,
                cancel_event=threading.Event(),
                on_sentence=lambda sentence: None,
            )

    assert voice.calls == []


def test_synthesis_errors_propagate_after_partial_callback() -> None:
    class FailingVoice(FakeVoice):
        def synthesize(
            self,
            text: str,
            syn_config: Any = None,
            include_alignments: bool = False,
        ) -> Any:
            self.calls.append((text, syn_config, include_alignments))
            if text == "Bad.":
                raise RuntimeError("engine exploded")
            yield _chunk([0.1], [FakeAlignment("h", 1)])

    voice = FailingVoice({})
    seen: list[str] = []

    with pytest.raises(RuntimeError, match="engine exploded"):
        synthesize(
            _loaded(voice),
            "Ok. Bad.",
            [(0, 3), (4, 8)],
            rate=1.0,
            volume=1.0,
            cancel_event=threading.Event(),
            on_sentence=lambda sentence: seen.append(sentence.text),
        )

    assert seen == ["Ok."]
