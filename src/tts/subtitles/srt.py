"""Render subtitle cues as SubRip (SRT) text."""

from __future__ import annotations

from tts.types import Cue


def render_srt(cues: list[Cue]) -> str:
    """Render cues as SRT blocks separated by blank lines."""
    if not cues:
        return ""
    blocks = [
        f"{cue.index}\n"
        f"{_format_timestamp(cue.start_ms)} --> {_format_timestamp(cue.end_ms)}\n"
        f"{cue.text}"
        for cue in cues
    ]
    return "\n\n".join(blocks) + "\n"


def _format_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, int(milliseconds)), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
