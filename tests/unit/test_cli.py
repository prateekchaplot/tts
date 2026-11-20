"""Tests for the local server and voice-install CLI commands."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tts import __main__ as cli
from tts.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8321,
        data_dir=tmp_path,
        max_input_chars=50_000,
        history_limit=20,
        log_level="INFO",
        default_voice_id="en_US-lessac-medium",
    )


def test_main_starts_loopback_server_and_opens_browser(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    monkeypatch.setattr(cli.Settings, "load", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "configure_logging", lambda settings: None)

    def run(server: cli._BrowserServer) -> None:
        calls.update(
            {
                "host": server.config.host,
                "port": server.config.port,
                "url": server._browser_url,
                "open_browser": server._open_browser,
            }
        )

    monkeypatch.setattr(cli._BrowserServer, "run", run)
    monkeypatch.setattr("sys.argv", ["tts", "--port", "9000"])

    cli.main()

    assert calls["url"] == "http://127.0.0.1:9000"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9000
    assert calls["open_browser"] is True


def test_browser_opens_after_server_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def start_server(server: cli.uvicorn.Server, sockets: object = None) -> None:
        server.started = True

    monkeypatch.setattr(cli.uvicorn.Server, "startup", start_server)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls.append(url))
    server = cli._BrowserServer(cli.uvicorn.Config("app"), "http://127.0.0.1:8321", True)

    asyncio.run(server.startup())

    assert calls == ["http://127.0.0.1:8321"]


def test_main_refuses_non_loopback_binding_without_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.Settings, "load", lambda: _settings(tmp_path))
    monkeypatch.setattr("sys.argv", ["tts", "--host", "0.0.0.0", "--no-open"])

    with pytest.raises(SystemExit) as error:
        cli.main()

    assert error.value.code == 2


def test_add_voice_initializes_store_and_prints_voice_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli.Settings, "load", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "ensure_data_dirs", lambda settings: tmp_path / "voices")
    monkeypatch.setattr(cli, "install_voice", lambda name: calls.append(name) or name)
    monkeypatch.setattr("sys.argv", ["tts", "add-voice", "de_DE-thorsten-medium"])

    cli.main()

    assert calls == ["de_DE-thorsten-medium"]
    assert capsys.readouterr().out == "de_DE-thorsten-medium\n"
