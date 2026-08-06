from __future__ import annotations

import json
import logging
import signal
import socket
import time

from .config import Config
from .display import Display
from .model import StateStore, utc_now
from .normalize import normalize_event
from .render import render_dashboard, render_idle
from .transport import bind_socket, receive_event

LOG = logging.getLogger(__name__)


class DashboardDaemon:
    def __init__(self, config: Config, simulate: bool = False):
        self.config = config
        self.display = Display(config, simulate=simulate)
        self.store = StateStore(
            active_ttl=config.active_ttl_seconds,
            approval_ttl=config.approval_ttl_seconds,
        )
        self.running = True
        self.next_connect = 0.0

    def stop(self, *_args) -> None:
        self.running = False

    def _connect(self) -> None:
        if self.display.connected or time.monotonic() < self.next_connect:
            return
        try:
            self.display.connect()
            LOG.info("LCD connected at %s", self.display.device)
        except Exception as exc:
            LOG.warning("LCD unavailable: %s", exc)
            self.display.close()
            self.next_connect = time.monotonic() + 3

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)
        server = bind_socket(self.config)
        try:
            while self.running:
                self._connect()
                try:
                    data = receive_event(server, self.config)
                    envelope = json.loads(data)
                    if envelope.get("control") == "shutdown":
                        LOG.info("Shutdown requested")
                        self.running = False
                        continue
                    if envelope.get("schema_version") == 1:
                        update = normalize_event(
                            str(envelope["provider"]),
                            envelope.get("payload") or {},
                        )
                        self.store.apply(update)
                        LOG.info(
                            "Event received: provider=%s event=%s session=%s",
                            update.provider,
                            update.extra.get("event"),
                            update.session_id,
                        )
                except socket.timeout:
                    pass
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    LOG.warning("Ignored invalid event: %s", exc)

                now = utc_now()
                state = self.store.active(now)
                try:
                    frame = (
                        render_dashboard(state, now)
                        if state
                        else render_idle(
                            self.config.idle_title, now, self.display.connected
                        )
                    )
                except Exception:
                    # A render fault must not take the daemon down: it would
                    # strand the panel on its last frame with nothing to say why.
                    LOG.exception("Frame render failed; skipping this frame")
                    frame = None
                if frame is not None and self.display.connected:
                    try:
                        self.display.paint(frame)
                    except Exception as exc:
                        LOG.warning("LCD write failed: %s", exc)
                        self.display.close()
                        self.next_connect = time.monotonic() + 2
                time.sleep(max(0.0, self.config.frame_interval - 0.2))
        finally:
            server.close()
            if self.config.ipc_mode == "unix":
                self.config.socket_path.unlink(missing_ok=True)
            self.display.close()

