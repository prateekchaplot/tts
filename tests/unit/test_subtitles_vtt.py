"""Unit tests for the WebVTT renderer."""

from __future__ import annotations

from pathlib import Path

from tts.subtitles.vtt import render_vtt
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


def test_render_vtt_matches_golden_fixture_byte_for_byte() -> None:
    assert render_vtt(CUES).encode("utf-8") == (FIXTURES / "basic.vtt").read_bytes()


def test_render_vtt_empty_cue_list_is_a_valid_empty_document() -> None:
    assert render_vtt([]) == "WEBVTT\n\n"


def test_render_vtt_uses_hour_scale_timestamps() -> None:
    cue = Cue(index=1, start_ms=3_723_004, end_ms=3_726_507, text="Later on.")

    assert render_vtt([cue]) == ("WEBVTT\n\n01:02:03.004 --> 01:02:06.507\nLater on.\n")


def test_render_vtt_clamps_negative_timestamps_to_zero() -> None:
    cue = Cue(index=1, start_ms=-500, end_ms=0, text="Start.")

    assert render_vtt([cue]).startswith("WEBVTT\n\n00:00:00.000 --> 00:00:00.000\n")
