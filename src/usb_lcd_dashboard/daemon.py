from __future__ import annotations

import json
import logging
import signal
import socket
import time

from .config import Config, default_path, load_config
from .display import Display
from .layout import agent_slots, compose
from .model import StateStore, utc_now
from .normalize import normalize_event
from .transport import bind_socket, poll_timeout, receive_event
from .teams import TeamsIntegration

LOG = logging.getLogger(__name__)


class DashboardDaemon:
    def __init__(self, config: Config, simulate: bool = False, config_path=None):
        self.config = config
        self.simulate = simulate
        self.config_path = config_path or default_path()
        self.display = Display(config, simulate=simulate)
        self.store = StateStore()
        self.teams = TeamsIntegration()
        self._apply_config(config)
        self.running = True
        self.next_connect = 0.0
        self.config_signature = self._config_signature()
        self.next_config_check = 0.0
        # The last composed frame, for the settings editor's preview.
        self.last_frame = None
        self.admin = None
        self.tray = None

    def _apply_config(self, config: Config) -> None:
        """Adopt a config, whether at startup or after an edit."""
        self.config = config
        self.store.active_ttl = config.active_ttl_seconds
        self.store.approval_ttl = config.approval_ttl_seconds
        self.store.tool_ttl = config.tool_ttl_seconds
        self.store.switch_dwell = config.switch_dwell_seconds
        # The tiles are the cap on how many sessions can be on screen at once.
        self.slot_count = agent_slots(config.tiles)
        self.teams.set_enabled(any(tile.widget == "messages" for tile in config.tiles))
        # getattr, because this runs once before the tray exists.
        if getattr(self, "tray", None) is not None:
            # The tooltip names the device and the menu offers the editor, both
            # of which an edit can change.
            self.tray.update_config(config)

    def _config_signature(self) -> bytes | None:
        """The config's contents, as the thing to notice changes in.

        Not the mtime: a save can land inside the same filesystem timestamp tick
        as the write before it, and the edit would then be silently ignored until
        something else touched the file — which from the editor looks like Save
        doing nothing. The file is well under a kilobyte and this runs at 1Hz.
        """
        try:
            return self.config_path.read_bytes()
        except OSError:
            return None

    def _reload_config(self) -> None:
        """Pick up an edited config.toml without a restart.

        The settings editor writes the file and the daemon notices, which keeps
        the two from sharing mutable state across threads — the file is the only
        channel, and write_config replaces it atomically so a half-written one is
        never seen. A config that will not load is logged and ignored, so a bad
        edit never takes the panel down.
        """
        if time.monotonic() < self.next_config_check:
            return
        self.next_config_check = time.monotonic() + 1.0
        signature = self._config_signature()
        if signature is None or signature == self.config_signature:
            return
        self.config_signature = signature
        try:
            fresh = load_config(self.config_path)
        except Exception as exc:
            LOG.warning("Ignoring an invalid config (keeping the last good one): %s", exc)
            return
        display_changed = (
            fresh.size != self.config.size
            or fresh.display_kind != self.config.display_kind
            or fresh.device != self.config.device
            or fresh.orientation != self.config.orientation
            or fresh.brightness != self.config.brightness
        )
        self._apply_config(fresh)
        LOG.info(
            "Config reloaded: %s tiles, %s agent slots", len(fresh.tiles), self.slot_count
        )
        if display_changed:
            # A new size or transport means the open panel is the wrong one.
            LOG.info("Display settings changed; reconnecting")
            self.display.close()
            self.display = Display(fresh, simulate=self.simulate)
            self.next_connect = 0.0

    def _start_admin(self) -> None:
        if not self.config.admin_enabled:
            return
        try:
            from .admin import AdminState, start

            self.admin = start(
                AdminState(
                    config_path=self.config_path,
                    get_config=lambda: self.config,
                    get_preview=lambda: self.last_frame,
                    get_teams=self.teams.status,
                    connect_teams=self.teams.connect,
                    disconnect_teams=self.teams.disconnect,
                ),
                self.config.admin_port,
            )
        except Exception as exc:
            # The editor is a convenience; the panel is the job.
            LOG.warning("Settings editor unavailable: %s", exc)

    def _start_tray(self) -> None:
        if not self.config.tray_enabled:
            return
        try:
            from .tray import start

            self.tray = start(self.config, self.stop)
        except Exception as exc:
            # Same bargain as the editor: the panel is the job, and a daemon
            # with no icon is still a working daemon.
            LOG.warning("Tray icon unavailable: %s", exc)

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
        self.teams.start(enabled=any(tile.widget == "messages" for tile in self.config.tiles))
        self._start_admin()
        self._start_tray()
        try:
            while self.running:
                self._connect()
                if self.tray is not None:
                    self.tray.set_connected(self.display.connected)
                self._reload_config()
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
                sessions = self.store.assign(self.slot_count, now)
                try:
                    frame = compose(
                        self.config.tiles,
                        self.config.size,
                        sessions=sessions,
                        now=now,
                        background=self.config.background,
                        connected=self.display.connected,
                        idle_title=self.config.idle_title,
                        messages=self.teams.snapshot(),
                    )
                except Exception:
                    # compose already isolates a single widget's fault to its own
                    # tile; this is the backstop for a fault in composition
                    # itself, which would otherwise strand the panel on its last
                    # frame with nothing to say why.
                    LOG.exception("Frame render failed; skipping this frame")
                    frame = None
                if frame is not None:
                    # Kept whether or not a panel is attached, so the editor's
                    # preview works while waiting for the hardware.
                    self.last_frame = frame
                if frame is not None and self.display.connected:
                    try:
                        self.display.paint(frame)
                    except Exception as exc:
                        LOG.warning("LCD write failed: %s", exc)
                        self.display.close()
                        self.next_connect = time.monotonic() + 2
                # The receive above already blocked for up to the poll timeout,
                # so only the remainder of the frame is left to wait out. Both
                # come from the live config, so an edited refresh_hz takes
                # effect on the next iteration without a restart.
                timeout = poll_timeout(self.config)
                server.settimeout(timeout)
                time.sleep(max(0.0, self.config.frame_interval - timeout))
        finally:
            server.close()
            if self.config.ipc_mode == "unix":
                self.config.socket_path.unlink(missing_ok=True)
            if self.admin is not None:
                self.admin.shutdown()
                self.admin.server_close()
            if self.tray is not None:
                self.tray.stop()
            self.display.close()
            self.teams.stop()

