from __future__ import annotations

import json
import socket
from typing import Any

from .config import Config


MAX_WIRE_BYTES = 65_535


def _wire_data(provider: str, payload: dict[str, Any]) -> bytes:
    envelope = {
        "schema_version": 1,
        "provider": provider,
        "payload": payload,
    }
    return json.dumps(envelope, separators=(",", ":")).encode()


def _send(config: Config, data: bytes) -> bool:
    if len(data) > 60_000:
        return False
    family = socket.AF_INET if config.ipc_mode == "tcp" else socket.AF_UNIX
    kind = socket.SOCK_STREAM if config.ipc_mode == "tcp" else socket.SOCK_DGRAM
    client = socket.socket(family, kind)
    try:
        client.settimeout(0.1)
        target = (
            config.ipc_address
            if config.ipc_mode == "tcp"
            else str(config.socket_path)
        )
        client.connect(target)
        if config.ipc_mode == "tcp":
            client.sendall(data)
        else:
            client.send(data)
        return True
    except OSError:
        return False
    finally:
        client.close()


def send_event(config: Config, provider: str, payload: dict[str, Any]) -> bool:
    return _send(config, _wire_data(provider, payload))


def send_control(config: Config, control: str) -> bool:
    data = json.dumps(
        {"schema_version": 1, "control": control}, separators=(",", ":")
    ).encode()
    return _send(config, data)


def bind_socket(config: Config) -> socket.socket:
    if config.ipc_mode == "tcp":
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(config.ipc_address)
        server.listen(16)
    else:
        path = config.socket_path
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        server.bind(str(path))
        path.chmod(0o600)
    server.settimeout(poll_timeout(config))
    return server


def poll_timeout(config: Config) -> float:
    """How long a receive may block before the loop goes round again.

    This is the real floor on the frame rate: the loop blocks here, then sleeps
    the remainder of the frame, so a fixed 0.2s timeout capped the panel at 5Hz
    however high refresh_hz was set. Tying it to the frame interval lets an
    animated widget actually reach the rate it was configured for, while a slow
    panel keeps the old 0.2s responsiveness to an incoming event.
    """
    return min(0.2, config.frame_interval)


def receive_event(server: socket.socket, config: Config) -> bytes:
    if config.ipc_mode != "tcp":
        return server.recv(MAX_WIRE_BYTES)

    connection, _address = server.accept()
    with connection:
        connection.settimeout(0.1)
        chunks = bytearray()
        while len(chunks) < MAX_WIRE_BYTES:
            try:
                chunk = connection.recv(min(8192, MAX_WIRE_BYTES - len(chunks)))
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.extend(chunk)
        return bytes(chunks)
