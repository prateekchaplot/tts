"""Unit tests for the SRT renderer."""

from __future__ import annotations

from pathlib import Path

from tts.subtitles.srt import render_srt
from tts.types import Cue

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "subtitles"

CUES = [
    Cue(index=1, start_ms=0, end_ms=3200, text="Hello world, this is a test."),
    Cue(
        index=2,
        start_ms=3200,
        end_ms=6100,
        text="Second sentence with a longer line of text that still fits.",
    ),
    Cue(index=3, start_ms=6100, end_ms=9504, text="A third cue ends the file."),
]


def test_render_srt_matches_golden_fixture_byte_for_byte() -> None:
    assert render_srt(CUES).encode("utf-8") == (FIXTURES / "basic.srt").read_bytes()


def test_render_srt_empty_cue_list_renders_nothing() -> None:
    assert render_srt([]) == ""


def test_render_srt_uses_hour_scale_timestamps() -> None:
    cue = Cue(index=1, start_ms=3_723_004, end_ms=3_726_507, text="Later on.")

    assert render_srt([cue]) == ("1\n01:02:03,004 --> 01:02:06,507\nLater on.\n")


def test_render_srt_clamps_negative_timestamps_to_zero() -> None:
    cue = Cue(index=1, start_ms=-500, end_ms=0, text="Start.")

    assert render_srt([cue]).startswith("1\n00:00:00,000 --> 00:00:00,000\n")
