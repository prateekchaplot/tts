"""Command-line entry points for tts."""

from __future__ import annotations

import argparse

from tts import __version__


def main() -> None:
    """Print the installed application version."""
    parser = argparse.ArgumentParser(prog="tts")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args()
    print(f"tts {__version__}")


def add_voice() -> None:
    """Provide the voice-install command entry point."""
    parser = argparse.ArgumentParser(prog="tts.add-voice")
    parser.add_argument("name", help="Piper voice name to install")
    parser.parse_args()
    parser.error("voice installation is not available until the voice store is initialized")
