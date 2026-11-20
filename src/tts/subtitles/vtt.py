"""Render subtitle cues as WebVTT text."""

from __future__ import annotations

from tts.types import Cue


def render_vtt(cues: list[Cue]) -> str:
    """Render cues as a WebVTT document with blank-line-separated blocks."""
    blocks = [
        f"{_format_timestamp(cue.start_ms)} --> {_format_timestamp(cue.end_ms)}\n{cue.text}"
        for cue in cues
    ]
    if not blocks:
        return "WEBVTT\n\n"
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"


def _format_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, int(milliseconds)), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
