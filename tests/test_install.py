from types import SimpleNamespace

from usb_lcd_dashboard import install as install_mod
from usb_lcd_dashboard.install import (
    EVENTS_BY_PROVIDER, MCP_NAME, _codex_mcp_section, _merge_hooks,
    _replace_codex_mcp,
)
from usb_lcd_dashboard.normalize import PHASES


def merged(provider="claude", existing=None):
    settings = {"hooks": existing} if existing else {}
    _merge_hooks(settings, provider, "usb-lcd-dashboard")
    return settings["hooks"]


def test_every_installed_event_maps_to_a_phase():
    """An event we register but do not normalise would arrive and mean nothing."""
    for provider, events in EVENTS_BY_PROVIDER.items():
        for event in events:
            assert event in PHASES, f"{provider} installs {event} with no phase"


def test_the_notification_hook_is_installed():
    """NOTICE is what the crab widget alarms on besides APPROVAL.

    The phase was mapped in normalize.PHASES long before the hook was registered,
    so it existed but could never fire. This is the guard on that staying fixed.
    """
    assert "Notification" in EVENTS_BY_PROVIDER["claude"]
    assert "Notification" in EVENTS_BY_PROVIDER["codex"]
    assert PHASES["Notification"] == "NOTICE"
    hooks = merged()
    assert "Notification" in hooks
    command = hooks["Notification"][0]["hooks"][0]["command"]
    assert command == "usb-lcd-dashboard emit --provider claude"


def test_the_approval_hook_is_still_installed():
    assert "PermissionRequest" in merged()


def test_merging_preserves_someone_elses_hook():
    """The installer merges rather than replaces, which is what makes it safe to
    re-run to pick up a newly added event."""
    theirs = {
        "hooks": [{"type": "command", "command": "notify-send hello"}]
    }
    hooks = merged(existing={"Notification": [theirs]})
    commands = [
        entry["command"]
        for group in hooks["Notification"]
        for entry in group["hooks"]
    ]
    assert "notify-send hello" in commands
    assert "usb-lcd-dashboard emit --provider claude" in commands


def test_merging_twice_does_not_duplicate_our_hook():
    settings = {}
    _merge_hooks(settings, "claude", "usb-lcd-dashboard")
    _merge_hooks(settings, "claude", "usb-lcd-dashboard")
    ours = [
        entry
        for group in settings["hooks"]["Notification"]
        for entry in group["hooks"]
        if "usb-lcd-dashboard" in entry["command"]
    ]
    assert len(ours) == 1


def test_codex_mcp_merge_preserves_other_configuration_and_is_idempotent():
    original = 'model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "other"\n'
    section = _codex_mcp_section("C:/Program Files/USB LCD/python.exe", ["-m", "usb_lcd_dashboard", "mcp"])
    once, previous = _replace_codex_mcp(original, section)
    twice, displaced = _replace_codex_mcp(once, section)
    assert previous is None
    assert displaced is not None
    assert once == twice
    assert once.count(MCP_NAME) == 1
    assert '[mcp_servers.other]' in once and 'model = "gpt-5"' in once


def test_codex_mcp_uninstall_can_restore_a_displaced_entry():
    prior = f'[mcp_servers.{MCP_NAME}]\ncommand = "mine"'
    installed, displaced = _replace_codex_mcp(prior + "\n", _codex_mcp_section("ours", ["mcp"]))
    restored, _ = _replace_codex_mcp(installed, displaced)
    assert 'command = "mine"' in restored
    assert 'command = "ours"' not in restored


def test_install_and_uninstall_manage_both_user_mcp_configs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    state_home = tmp_path / "state"
    home.mkdir()
    monkeypatch.setattr(install_mod.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(install_mod, "config_home", lambda: state_home)
    install_mod.install("usb-lcd-dashboard")
    claude = install_mod._read_json(home / ".claude.json")
    codex_text = (home / ".codex/config.toml").read_text()
    assert claude["mcpServers"][MCP_NAME]["args"] == ["mcp"]
    assert codex_text.count(MCP_NAME) == 1

    install_mod.install("usb-lcd-dashboard")
    assert (home / ".codex/config.toml").read_text().count(MCP_NAME) == 1
    install_mod.uninstall()
    assert MCP_NAME not in (home / ".codex/config.toml").read_text()
    assert MCP_NAME not in install_mod._read_json(home / ".claude.json").get("mcpServers", {})


# ------------------------------------------------------- the systemd user unit

def test_the_unit_is_enabled_and_started(monkeypatch):
    """Writing the unit and stopping there is a half-installed state: the panel
    stays dark until the user finds the systemctl commands in the README."""
    calls = []
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: "/bin/systemctl")
    monkeypatch.setattr(
        install_mod.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0),
    )
    assert install_mod._systemd_enable() is True
    assert calls[0][:3] == ["/bin/systemctl", "--user", "daemon-reload"]
    assert calls[1][2:] == ["enable", "--now", "usb-lcd-dashboard.service"]


def test_the_unit_is_disabled_before_its_file_is_removed(monkeypatch):
    """Deleting the unit first leaves a dangling default.target.wants symlink
    and leaves the daemon running with the panel still held open."""
    calls = []
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: "/bin/systemctl")
    monkeypatch.setattr(
        install_mod.subprocess,
        "run",
        lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(returncode=0),
    )
    install_mod._systemd_disable()
    assert calls[0][2:] == ["disable", "--now", "usb-lcd-dashboard.service"]


def test_a_missing_systemctl_is_not_fatal(monkeypatch):
    """No user manager exists in a container, a chroot or a package build. An
    installer that failed there would be worse than one that needs a manual
    start."""
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    assert install_mod._systemd_enable() is False
    install_mod._systemd_disable()  # must not raise


def test_a_failing_systemctl_is_not_fatal(monkeypatch):
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: "/bin/systemctl")

    def boom(cmd, **kwargs):
        raise OSError("no session bus")

    monkeypatch.setattr(install_mod.subprocess, "run", boom)
    assert install_mod._systemd_enable() is False
