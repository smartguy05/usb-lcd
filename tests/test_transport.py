import base64
import json
import socket

import pytest

from usb_lcd_dashboard.cli import main
from usb_lcd_dashboard.config import Config
from usb_lcd_dashboard.transport import (
    bind_socket,
    poll_timeout,
    receive_event,
    send_event,
)


def test_missing_daemon_is_nonblocking(tmp_path, monkeypatch):
    # Point at an endpoint nothing is listening on, for whichever IPC mode this
    # platform defaults to; on Windows that is TCP, where a live dashboard
    # daemon on the default port would otherwise accept the event.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    config = Config(ipc_port=dead_port)
    monkeypatch.setattr(type(config), "socket_path", property(lambda self: tmp_path / "missing.sock"))
    assert send_event(config, "codex", {}) is False


def test_tcp_transport_round_trip():
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()

    config = Config(ipc_mode="tcp", ipc_port=port)
    server = bind_socket(config)
    try:
        assert send_event(config, "codex", {"session_id": "windows"})
        envelope = json.loads(receive_event(server, config))
    finally:
        server.close()

    assert envelope == {
        "schema_version": 1,
        "provider": "codex",
        "payload": {"session_id": "windows"},
    }


def test_missing_tcp_daemon_is_nonblocking():
    config = Config(ipc_mode="tcp", ipc_port=45999)
    assert send_event(config, "codex", {}) is False


def test_statusline_proxy_preserves_output(monkeypatch, capfd):
    payload = json.dumps({"session_id": "test"}).encode()
    encoded = base64.urlsafe_b64encode(b"cat").decode()

    class FakeStdin:
        class Buffer:
            @staticmethod
            def read():
                return payload
        buffer = Buffer()

    monkeypatch.setattr("sys.stdin", FakeStdin())
    assert main(["statusline-proxy", "--downstream-b64", encoded]) == 0
    assert capfd.readouterr().out == payload.decode()


def test_the_poll_timeout_follows_the_frame_rate():
    """The receive blocks for this long before the loop goes round again, so a
    fixed value here is a hard ceiling on the frame rate however high refresh_hz
    is set. A slow panel keeps the old 0.2s responsiveness to an incoming event.
    """
    assert poll_timeout(Config(refresh_hz=2.0)) == 0.2
    assert poll_timeout(Config(refresh_hz=0.5)) == 0.2
    assert poll_timeout(Config(refresh_hz=8.0)) == pytest.approx(0.125)
    # And the daemon then has a non-negative remainder left to sleep.
    for hz in (0.5, 2.0, 8.0, 10.0):
        config = Config(refresh_hz=hz)
        assert config.frame_interval - poll_timeout(config) >= 0.0

