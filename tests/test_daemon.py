from dataclasses import replace

from PIL import Image

from usb_lcd_dashboard.config import Config, dump_config_toml, load_config
from usb_lcd_dashboard.daemon import DashboardDaemon
from usb_lcd_dashboard.layout import Tile


WIDE = """
[display]
kind = "simulated"
width = 1920
height = 462

[admin]
enabled = false

[[tile]]
widget = "clock"
x = 12
y = 12
w = 404
h = 438

[[tile]]
widget = "agent"
x = 428
y = 12
w = 486
h = 438
"""


def daemon_for(tmp_path, text=WIDE):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return DashboardDaemon(load_config(path), simulate=True, config_path=path), path


def rewrite(path, cfg):
    """Write a config. The watcher compares contents, so no mtime nudging."""
    path.write_text(dump_config_toml(cfg), encoding="utf-8")


def force_check(daemon):
    daemon.next_config_check = 0.0


def test_the_slot_count_comes_from_the_agent_tiles(tmp_path):
    daemon, _ = daemon_for(tmp_path)
    assert daemon.slot_count == 1
    assert len(daemon.config.tiles) == 2


def test_the_store_takes_its_timings_from_the_config(tmp_path):
    daemon, path = daemon_for(tmp_path, WIDE + "\n[dashboard]\nswitch_dwell_seconds = 9.5\n")
    assert daemon.store.switch_dwell == 9.5


def test_an_edited_layout_is_picked_up_without_a_restart(tmp_path):
    daemon, path = daemon_for(tmp_path)
    tiles = daemon.config.tiles + (Tile("agent", 926, 12, 486, 438),)
    rewrite(path, replace(daemon.config, tiles=tiles))
    force_check(daemon)
    daemon._reload_config()
    assert len(daemon.config.tiles) == 3
    assert daemon.slot_count == 2, "a new agent tile should raise the session cap"


def test_a_save_in_the_same_timestamp_tick_is_still_noticed(tmp_path):
    """The regression this pins: an edit landing inside the same filesystem
    timestamp tick as the previous write was silently ignored, which from the
    settings editor looked like Save doing nothing."""
    import os

    daemon, path = daemon_for(tmp_path)
    stamp = path.stat().st_mtime
    rewrite(path, replace(daemon.config, idle_title="SAME TICK"))
    # Force the mtime back to exactly what it was when the daemon last loaded.
    os.utime(path, (stamp, stamp))
    force_check(daemon)
    daemon._reload_config()
    assert daemon.config.idle_title == "SAME TICK"


def test_edited_timings_reach_the_store(tmp_path):
    daemon, path = daemon_for(tmp_path)
    rewrite(path, replace(daemon.config, switch_dwell_seconds=12.0, tool_ttl_seconds=42))
    force_check(daemon)
    daemon._reload_config()
    assert daemon.store.switch_dwell == 12.0
    assert daemon.store.tool_ttl == 42


def test_an_invalid_config_is_ignored_and_the_last_good_one_kept(tmp_path, caplog):
    daemon, path = daemon_for(tmp_path)
    before = daemon.config
    path.write_text('[display]\nkind = "plasma"\n', encoding="utf-8")
    force_check(daemon)
    with caplog.at_level("WARNING"):
        daemon._reload_config()
    assert daemon.config is before, "a bad edit must not take the panel down"
    assert any("Ignoring an invalid config" in r.message for r in caplog.records)


def test_an_unchanged_file_is_not_reloaded(tmp_path):
    daemon, path = daemon_for(tmp_path)
    before = daemon.config
    force_check(daemon)
    daemon._reload_config()
    assert daemon.config is before


def test_the_reload_is_throttled(tmp_path):
    """Stat-per-frame at 2Hz is cheap, but there is no reason to do it twice."""
    daemon, path = daemon_for(tmp_path)
    rewrite(path, replace(daemon.config, brightness=11))
    daemon.next_config_check = float("inf")
    daemon._reload_config()
    assert daemon.config.brightness == 25, "the check should have been skipped"


def test_a_resized_display_forces_a_reconnect(tmp_path):
    daemon, path = daemon_for(tmp_path)
    first = daemon.display
    daemon.next_connect = 999.0
    rewrite(path, replace(daemon.config, width=800, height=480,
                          tiles=(Tile("agent", 0, 0, 800, 480),)))
    force_check(daemon)
    daemon._reload_config()
    assert daemon.display is not first, "the open panel is the wrong size now"
    assert daemon.next_connect == 0.0
    assert daemon.config.size == (800, 480)


def test_a_layout_only_change_keeps_the_panel_open(tmp_path):
    daemon, path = daemon_for(tmp_path)
    first = daemon.display
    rewrite(path, replace(daemon.config, idle_title="HOME"))
    force_check(daemon)
    daemon._reload_config()
    assert daemon.display is first
    assert daemon.config.idle_title == "HOME"


def test_a_missing_config_file_does_not_trigger_a_reload(tmp_path):
    daemon, path = daemon_for(tmp_path)
    before = daemon.config
    path.unlink()
    force_check(daemon)
    daemon._reload_config()
    assert daemon.config is before


# --------------------------------------------------------------- the editor

def test_the_editor_is_not_started_when_disabled(tmp_path):
    daemon, _ = daemon_for(tmp_path)
    assert daemon.config.admin_enabled is False
    daemon._start_admin()
    assert daemon.admin is None


def test_the_editor_starts_when_enabled(tmp_path):
    daemon, _ = daemon_for(tmp_path, WIDE.replace("enabled = false", "enabled = true"))
    daemon.config = replace(daemon.config, admin_port=0)
    daemon._start_admin()
    try:
        assert daemon.admin is not None
        assert daemon.admin.server_address[0] == "127.0.0.1"
    finally:
        daemon.admin.shutdown()
        daemon.admin.server_close()


def test_a_port_already_in_use_does_not_stop_the_daemon(tmp_path, caplog):
    """The editor is a convenience; the panel is the job."""
    import socket

    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    taken = holder.getsockname()[1]
    try:
        daemon, _ = daemon_for(tmp_path, WIDE.replace("enabled = false", "enabled = true"))
        daemon.config = replace(daemon.config, admin_port=taken)
        with caplog.at_level("WARNING"):
            daemon._start_admin()
        assert daemon.admin is None
        assert any("Settings editor unavailable" in r.message for r in caplog.records)
    finally:
        holder.close()


# ----------------------------------------------------------------- the tray

class FakeTray:
    """Stands in for the Win32 icon, which needs a shell to talk to."""

    def __init__(self):
        self.states = []
        self.configs = []
        self.stopped = False

    def set_connected(self, connected):
        self.states.append(connected)

    def update_config(self, config):
        self.configs.append(config)

    def stop(self):
        self.stopped = True


def test_the_tray_is_not_started_when_disabled(tmp_path):
    daemon, _ = daemon_for(tmp_path, WIDE + "\n[tray]\nenabled = false\n")
    daemon._start_tray()
    assert daemon.tray is None


def test_a_failing_tray_does_not_stop_the_daemon(tmp_path, monkeypatch, caplog):
    import usb_lcd_dashboard.tray as tray_module

    daemon, _ = daemon_for(tmp_path)
    monkeypatch.setattr(
        tray_module, "start", lambda *a, **k: (_ for _ in ()).throw(OSError("no shell"))
    )
    with caplog.at_level("WARNING"):
        daemon._start_tray()
    assert daemon.tray is None
    assert any("Tray icon unavailable" in r.message for r in caplog.records)


def test_quitting_from_the_tray_stops_the_daemon(tmp_path):
    """The menu's Quit is wired to the same stop() that SIGTERM is."""
    daemon, _ = daemon_for(tmp_path)
    assert daemon.running is True
    daemon.stop()
    assert daemon.running is False


def test_an_edited_config_reaches_the_tray(tmp_path):
    daemon, path = daemon_for(tmp_path)
    daemon.tray = FakeTray()
    rewrite(path, replace(daemon.config, device="COM9"))
    force_check(daemon)
    daemon._reload_config()
    assert daemon.tray.configs[-1].device == "COM9"


def test_the_preview_frame_starts_empty(tmp_path):
    daemon, _ = daemon_for(tmp_path)
    assert daemon.last_frame is None


def test_the_editor_reads_the_daemons_live_config_and_frame(tmp_path):
    from usb_lcd_dashboard.admin import AdminState, config_to_json

    daemon, path = daemon_for(tmp_path)
    state = AdminState(path, lambda: daemon.config, lambda: daemon.last_frame)
    daemon.last_frame = Image.new("RGB", (1920, 462), "#081018")
    assert config_to_json(state.get_config())["display"]["width"] == 1920
    assert state.get_preview().size == (1920, 462)
    # And an edit made through the editor is what the daemon then reloads.
    state.save(
        {
            "display": {"kind": "simulated", "width": 1920, "height": 462},
            "dashboard": {"idle_title": "SAVED BY THE EDITOR"},
            "tiles": config_to_json(daemon.config)["tiles"],
        }
    )
    force_check(daemon)
    daemon._reload_config()
    assert daemon.config.idle_title == "SAVED BY THE EDITOR"
