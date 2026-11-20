"""Command-line entry points for running tts and installing Piper voices."""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import webbrowser
from dataclasses import replace

import uvicorn

from tts import __version__
from tts.app import create_app
from tts.config import Settings, configure_logging
from tts.voices.store import ensure_data_dirs, install_voice


class _BrowserServer(uvicorn.Server):
    """Open the browser only after uvicorn has bound and started serving."""

    def __init__(self, config: uvicorn.Config, browser_url: str, open_browser: bool) -> None:
        super().__init__(config)
        self._browser_url = browser_url
        self._open_browser = open_browser

    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets=sockets)
        if self.started and self._open_browser:
            webbrowser.open(self._browser_url)


def _is_loopback_host(host: str) -> bool:
    """Accept localhost names and literal loopback IP addresses."""
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _browser_host(host: str) -> str:
    """Use a browser-reachable host when uvicorn binds to every interface."""
    if host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return host


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tts")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--host", help="bind address (default: TTS_HOST or 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port (default: TTS_PORT or 8321)")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    parser.add_argument(
        "--i-know-this-is-lan",
        action="store_true",
        help="allow binding to a non-loopback address",
    )
    commands = parser.add_subparsers(dest="command")
    add_voice_parser = commands.add_parser("add-voice", help="download a Piper voice")
    add_voice_parser.add_argument("name", help="Piper voice name to install")
    return parser


def _serve(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    settings = Settings.load()
    host = args.host or settings.host
    port = args.port if args.port is not None else settings.port
    if not _is_loopback_host(host) and not args.i_know_this_is_lan:
        parser.error(
            "refusing a non-loopback bind; pass --i-know-this-is-lan to expose tts on your LAN"
        )

    settings = replace(settings, host=host, port=port)
    configure_logging(settings)
    browser_host = _browser_host(host)
    if ":" in browser_host:
        browser_host = f"[{browser_host}]"
    url = f"http://{browser_host}:{port}"
    config = uvicorn.Config(create_app(settings), host=host, port=port, log_config=None)
    _BrowserServer(config, url, open_browser=not args.no_open).run()


def _install(name: str) -> None:
    settings = Settings.load()
    ensure_data_dirs(settings)
    try:
        voice_id = install_voice(name)
    except Exception as error:
        print(f"Could not install voice {name!r}: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(voice_id)


def main() -> None:
    """Start the local web application or run the ``add-voice`` subcommand."""
    parser = _parser()
    args = parser.parse_args()
    if args.command == "add-voice":
        _install(args.name)
        return
    _serve(args, parser)


def add_voice() -> None:
    """Entry point retained for the standalone ``tts.add-voice`` script."""
    parser = argparse.ArgumentParser(prog="tts.add-voice")
    parser.add_argument("name", help="Piper voice name to install")
    _install(parser.parse_args().name)


if __name__ == "__main__":
    main()
