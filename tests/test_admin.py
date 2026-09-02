import json
import io
import urllib.error
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from usb_lcd_dashboard import admin
from usb_lcd_dashboard.admin_page import PAGE
from usb_lcd_dashboard.admin import (
    AdminState,
    config_from_json,
    config_to_json,
    _host_is_loopback,
    rotate_layout_payload,
)
from usb_lcd_dashboard.config import Config, load_config
from usb_lcd_dashboard.layout import Tile
from usb_lcd_dashboard.todos import TodoStore


WIDE = """
[display]
kind = "simulated"
width = 1920
height = 462

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


def test_switching_to_the_legacy_panel_restores_its_fixed_profile():
    """The old panel must not inherit a wide panel's canvas and tile layout."""
    assert '["turing_rev_a", "turing_usb", "auto", "simulated", "window"], changeDisplayKind' in PAGE
    assert 'cfg.display.width = portrait ? 320 : 480;' in PAGE
    assert 'cfg.display.height = portrait ? 480 : 320;' in PAGE
    assert 'widget: "legacy", x: 0, y: 0' in PAGE


def test_enabling_auto_preserves_the_current_panel_for_profile_seeding():
    auto = PAGE.index('if (kind === "auto")')
    legacy = PAGE.index('if (kind !== "turing_rev_a")')
    assert auto < legacy
    assert 'drawPanels();\n    return;' in PAGE[auto:legacy]


def test_the_editor_is_split_into_a_stage_a_panel_and_three_tabs():
    """The stage stays put; everything else is a tab or collapses away."""
    assert 'id="stage"' in PAGE and 'id="settingsPanel"' in PAGE
    for mount in ("bgForm", "screensaverForm", "displayForm"):
        assert 'id="%s"' % mount in PAGE
    assert 'id="tabBtnLive"' in PAGE and 'id="tabBtnWidget"' in PAGE
    assert 'id="tabLive"' in PAGE and 'id="tabWidget"' in PAGE
    # The active background is a tab of its own, with its own form mount.
    assert 'id="tabBtnActiveBg"' in PAGE and 'id="tabActiveBg"' in PAGE
    assert 'id="activeBgForm"' in PAGE
    # The live frame is the only thing in its tab; the stage is not inside one.
    assert PAGE.index('id="stage"') < PAGE.index('id="tabLive"')


def test_source_backed_sections_live_in_the_widget_tab():
    """Discord, notifications and todos configure a widget, so they follow it."""
    for section in ("secDash", "secDiscord", "secWindows", "secTodos", "secReadonly"):
        assert 'id="%s"' % section in PAGE
    # Present but hidden at parse time: module-level listeners and the unguarded
    # $("todoCreate") in drawTodoCreate both need these ids to exist.
    for section in ("secDash", "secDiscord", "secWindows", "secTodos"):
        start = PAGE.index('id="%s"' % section)
        assert "hidden" in PAGE[start:PAGE.index(">", start)]
    for mount in ("todoCreate", "todoHistory", "todoList", "discordConnection",
                  "windowsNotifications", "roInfo"):
        assert 'id="%s"' % mount in PAGE
    # Driven by the registry flags rather than a hardcoded list of widget names.
    assert "wants_session" in PAGE and "wants_messages" in PAGE
    assert "wants_notifications" in PAGE and "wants_todos" in PAGE


def test_the_preview_poll_stops_while_its_tab_is_hidden():
    """A PNG fetched every two seconds for a tab nobody is looking at."""
    assert "if (document.hidden || !liveTabShowing()) return;" in PAGE


def test_switching_to_the_turzx_panel_restores_its_wide_profile():
    """The USB transport cannot retain the legacy 480x320 canvas."""
    assert 'if (kind === "turing_usb")' in PAGE
    assert 'cfg.display.width = 1920;' in PAGE
    assert 'cfg.display.height = 462;' in PAGE
    assert '{widget:"clock", x:12, y:12, w:404, h:438' in PAGE
    assert '{widget:"crab", x:1424, y:12, w:484, h:438' in PAGE


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(WIDE, encoding="utf-8")
    holder = {"config": load_config(path), "frame": None}
    return AdminState(
        config_path=path,
        get_config=lambda: holder["config"],
        get_preview=lambda: holder["frame"],
        todo_store=TodoStore(tmp_path / "todos.sqlite3"),
    ), holder


@pytest.fixture
def server(state):
    st, holder = state
    srv = admin.start(st, 0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base, st, holder
    srv.shutdown()
    srv.server_close()


def get(base, route):
    with urllib.request.urlopen(base + route, timeout=5) as response:
        return response.status, response.read(), response.headers


def post(base, route, payload):
    request = urllib.request.Request(
        base + route,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def post_bytes(base, route, payload):
    request = urllib.request.Request(
        base + route,
        data=payload,
        headers={"Content-Type": "application/octet-stream"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# --------------------------------------------------------------- serialisation

def test_config_to_json_carries_the_layout_and_marks_ipc_readonly():
    cfg = load_config.__wrapped__ if False else Config()
    payload = config_to_json(replace(cfg, tiles=(Tile("clock", 1, 2, 3, 4, {"a": 1}),)))
    assert payload["display"]["width"] == 480
    assert payload["tiles"] == [
        {"widget": "clock", "x": 1, "y": 2, "w": 3, "h": 4, "options": {"a": 1}}
    ]
    assert payload["readonly"]["ipc_port"] == 45722
    assert payload["background"] is None
    assert payload["screensaver"] == {"enabled": True, "idle_seconds": 600}


def test_json_round_trips_a_config(state):
    st, holder = state
    original = holder["config"]
    again = config_from_json(original, config_to_json(original))
    assert again == original


def test_config_from_json_applies_edits(state):
    st, holder = state
    payload = config_to_json(holder["config"])
    payload["display"]["brightness"] = 41
    payload["dashboard"]["idle_title"] = "HOME"
    payload["screensaver"]["idle_seconds"] = 1200
    payload["tiles"][0]["options"]["title"] = "HOME"
    result = config_from_json(holder["config"], payload)
    assert result.brightness == 41
    assert result.idle_title == "HOME"
    assert result.screensaver_idle_seconds == 1200
    assert result.tiles[0].options["title"] == "HOME"


def test_config_to_json_omits_the_active_background_when_off():
    assert config_to_json(Config())["active_background"] is None


def test_config_from_json_applies_the_active_background(state):
    st, holder = state
    payload = config_to_json(holder["config"])
    payload["active_background"] = {
        "enabled": True, "scale": 0.3, "speed_min": 25,
        "speed_max": 180, "opacity": 0.7,
    }
    result = config_from_json(holder["config"], payload)
    assert result.active_background is not None
    assert result.active_background.enabled is True
    assert result.active_background.scale == 0.3
    assert result.active_background.speed_max == 180
    # And clearing it (checkbox off → null) turns the layer back off.
    payload["active_background"] = None
    assert config_from_json(result, payload).active_background is None


def test_layout_rotation_payload_rotates_every_tile():
    result = rotate_layout_payload({
        "source": "landscape", "target": "portrait",
        "width": 480, "height": 320,
        "tiles": [{"widget": "clock", "x": 10, "y": 20, "w": 30, "h": 40}],
    })
    assert (result["width"], result["height"]) == (320, 480)
    assert result["tiles"][0] == {
        "widget": "clock", "x": 260, "y": 10, "w": 40, "h": 30
    }


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"tiles": "nope"}, "tiles must be a list"),
        ({"tiles": ["nope"]}, r"tile\[0\] must be an object"),
        ({"tiles": [{"widget": "clock", "x": 0, "y": 0, "w": 1}]}, "missing"),
        ({"tiles": [{"widget": "clock", "x": 0, "y": 0, "w": 1, "h": 1,
                     "options": 5}]}, "options must be an object"),
        ({"tiles": []}, "at least one tile"),
        (
            {
                "tiles": [{"widget": "clock", "x": 0, "y": 0, "w": 10, "h": 10}],
                "display": {"width": "wide"},
            },
            "width must be a number",
        ),
    ],
)
def test_config_from_json_rejects_bad_shapes(state, payload, match):
    st, holder = state
    with pytest.raises(ValueError, match=match):
        config_from_json(holder["config"], payload)


# ------------------------------------------------------------------ the routes

def test_the_page_is_served(server):
    base, _, _ = server
    status, body, headers = get(base, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert b"USB LCD settings" in body
    assert b"Human todos" in body


def test_layout_rotation_route(server):
    base, _, _ = server
    status, body = post(base, "/api/layout/rotate", {
        "source": "landscape", "target": "landscape_flipped",
        "width": 100, "height": 50,
        "tiles": [{"widget": "clock", "x": 5, "y": 6, "w": 20, "h": 10}],
    })
    assert status == 200
    assert body["tiles"][0]["x"] == 75
    assert body["tiles"][0]["y"] == 34


def test_background_upload_stores_a_managed_png(server):
    base, state, _ = server
    buffer = io.BytesIO()
    Image.new("RGB", (80, 40), "#123456").save(buffer, format="JPEG")
    status, body = post_bytes(base, "/api/background-image", buffer.getvalue())
    assert status == 201
    stored = state.background_dir / Path(body["image"]).name
    assert stored.parent == state.background_dir
    with Image.open(stored) as image:
        assert image.format == "PNG"
        assert image.size == (80, 40)


def test_background_upload_rejects_non_images(server):
    base, _, _ = server
    status, body = post_bytes(base, "/api/background-image", b"not an image")
    assert status == 400
    assert "readable image" in body["error"]


def test_the_config_endpoint_returns_the_layout(server):
    base, _, _ = server
    status, body, _ = get(base, "/api/config")
    payload = json.loads(body)
    assert status == 200
    assert payload["display"]["width"] == 1920
    assert [t["widget"] for t in payload["tiles"]] == ["clock", "agent"]


def test_the_widgets_endpoint_describes_the_registry(server):
    base, _, _ = server
    _, body, _ = get(base, "/api/widgets")
    widgets = {w["name"]: w for w in json.loads(body)["widgets"]}
    assert set(widgets) == {"agent", "claude_limits", "clock", "crab", "legacy", "messages", "notifications", "todos"}
    assert widgets["agent"]["wants_session"] is True
    assert widgets["crab"]["wants_session"] is True
    assert any(o["name"] == "hour12" for o in widgets["clock"]["options"])
    assert widgets["messages"]["wants_messages"] is True
    assert widgets["todos"]["wants_todos"] is True
    assert widgets["claude_limits"]["wants_claude_limits"] is True


def test_todo_routes_cover_crud_history_reopen_and_delete(server):
    base, _, _ = server
    status, created = post(base, "/api/todos", {"title": "Call dentist", "priority": "high", "due_date": "2026-08-20"})
    assert status == 201
    item_id = created["todo"]["id"]
    status, body, _ = get(base, "/api/todos")
    assert status == 200 and json.loads(body)["todos"][0]["title"] == "Call dentist"

    request = urllib.request.Request(base + "/api/todos/" + item_id,
        data=json.dumps({"details": "Ask about Tuesday"}).encode(),
        headers={"Content-Type": "application/json"}, method="PATCH")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.loads(response.read())["todo"]["details"] == "Ask about Tuesday"
    assert post(base, f"/api/todos/{item_id}/complete", {})[0] == 200
    assert json.loads(get(base, "/api/todos")[1])["todos"] == []
    assert len(json.loads(get(base, "/api/todos?include_completed=1")[1])["todos"]) == 1
    assert post(base, f"/api/todos/{item_id}/reopen", {})[0] == 200

    request = urllib.request.Request(base + "/api/todos/" + item_id,
        data=json.dumps({"confirm": True}).encode(), headers={"Content-Type": "application/json"}, method="DELETE")
    with urllib.request.urlopen(request, timeout=5) as response:
        assert json.loads(response.read())["deleted"] is True


def test_todo_delete_requires_confirmation(server):
    base, _, _ = server
    item_id = post(base, "/api/todos", {"title": "Keep me"})[1]["todo"]["id"]
    request = urllib.request.Request(base + "/api/todos/" + item_id,
        data=b"{}", headers={"Content-Type": "application/json"}, method="DELETE")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 400


def test_the_discord_status_endpoint_contains_no_token(server):
    base, _, _ = server
    status, body, _ = get(base, "/api/integrations/discord")
    assert status == 200
    payload = json.loads(body)
    assert payload["status"] == "unconfigured"
    assert "token" not in body.decode().lower()


def test_discord_actions_are_forwarded(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(WIDE, encoding="utf-8")
    actions = []
    integration = {"configured": True, "status": "connected", "channels": []}
    state = AdminState(
        path,
        lambda: load_config(path),
        lambda: None,
        get_discord=lambda: integration,
        save_discord_token=lambda token: actions.append(("token", token)) or integration,
        disconnect_discord=lambda: actions.append(("disconnect", None)) or integration,
        refresh_discord_channels=lambda: actions.append(("channels", None)),
        clear_discord=lambda: actions.append(("clear", None)) or integration,
    )
    srv = admin.start(state, 0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert post(base, "/api/integrations/discord/token", {"token": "secret"})[0] == 200
        assert post(base, "/api/integrations/discord/channels", {})[0] == 200
        assert post(base, "/api/integrations/discord/clear", {})[0] == 200
        assert post(base, "/api/integrations/discord/disconnect", {})[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
    assert actions == [("token", "secret"), ("channels", None), ("clear", None), ("disconnect", None)]


def test_windows_notification_status_and_access_are_forwarded(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(WIDE, encoding="utf-8")
    actions = []
    integration = {"status": "permission_required", "apps": [], "matching": 0, "error": ""}
    state = AdminState(
        path,
        lambda: load_config(path),
        lambda: None,
        get_windows_notifications=lambda: integration,
        request_windows_notification_access=lambda: actions.append("access") or integration,
    )
    srv = admin.start(state, 0)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert json.loads(get(base, "/api/integrations/windows-notifications")[1])["status"] == "permission_required"
        assert post(base, "/api/integrations/windows-notifications/access", {})[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()
    assert actions == ["access"]


def test_a_cross_site_form_cannot_trigger_a_discord_action(server):
    base, _, _ = server
    request = urllib.request.Request(
        base + "/api/integrations/discord/clear",
        data=b"",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 415


def test_the_preview_says_so_when_no_frame_exists_yet(server):
    base, _, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(base, "/api/preview.png")
    assert exc.value.code == 503


def test_the_preview_serves_the_daemons_frame(server):
    base, _, holder = server
    holder["frame"] = Image.new("RGB", (1920, 462), "#081018")
    status, body, headers = get(base, "/api/preview.png")
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


def test_an_unknown_route_is_a_404(server):
    base, _, _ = server
    with pytest.raises(urllib.error.HTTPError) as exc:
        get(base, "/api/nope")
    assert exc.value.code == 404


# ------------------------------------------------------------------- saving

def test_saving_writes_the_config_file(server):
    base, st, holder = server
    payload = config_to_json(holder["config"])
    payload["tiles"][0]["w"] = 300
    payload["display"]["brightness"] = 33
    status, body = post(base, "/api/config", payload)
    assert status == 200 and body["saved"] is True
    reloaded = load_config(st.config_path)
    assert reloaded.tiles[0].w == 300
    assert reloaded.brightness == 33
    # And the response echoes what was actually stored.
    assert body["config"]["tiles"][0]["w"] == 300


def test_saving_an_overlapping_layout_is_refused_with_the_reason(server):
    base, st, holder = server
    before = st.config_path.read_text(encoding="utf-8")
    payload = config_to_json(holder["config"])
    payload["tiles"][1]["x"] = 100          # now on top of tile 0
    status, body = post(base, "/api/config", payload)
    assert status == 400
    assert "overlaps" in body["error"]
    assert st.config_path.read_text(encoding="utf-8") == before, "file was touched"


@pytest.mark.parametrize(
    "mutate,fragment",
    [
        (lambda p: p["display"].__setitem__("brightness", 99), "brightness"),
        (lambda p: p["display"].__setitem__("kind", "plasma"), "display.kind"),
        (lambda p: p["display"].__setitem__("width", 0), "between 1 and 4096"),
        (lambda p: p["tiles"][0].__setitem__("widget", "weather"), "not a known widget"),
        (lambda p: p["tiles"][0].__setitem__("w", 5000), "does not fit"),
        (lambda p: p["tiles"].clear(), "at least one tile"),
    ],
)
def test_every_loader_rule_is_enforced_on_save(server, mutate, fragment):
    """The editor validates by round-tripping through the real loader, so it
    cannot accept a config the daemon would then refuse to start on."""
    base, st, holder = server
    payload = config_to_json(holder["config"])
    mutate(payload)
    status, body = post(base, "/api/config", payload)
    assert status == 400
    assert fragment in body["error"]


def test_invalid_json_is_reported(server):
    base, _, _ = server
    request = urllib.request.Request(
        base + "/api/config", data=b"{not json",
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 400
    assert "invalid JSON" in json.loads(exc.value.read())["error"]


def test_an_implausibly_large_body_is_refused(server):
    base, _, _ = server
    request = urllib.request.Request(
        base + "/api/config", data=b"x" * (admin.MAX_BODY_BYTES + 10),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 413


# -------------------------------------------------------------------- guarding

@pytest.mark.parametrize(
    "header,expected",
    [
        ("127.0.0.1:45723", True),
        ("localhost:45723", True),
        ("127.0.0.1", True),
        ("LOCALHOST", True),
        ("[::1]:45723", True),
        ("evil.example.com", False),
        ("evil.example.com:45723", False),
        ("192.168.1.10:45723", False),
        (None, False),
        ("", False),
    ],
)
def test_only_loopback_hosts_are_accepted(header, expected):
    assert _host_is_loopback(header) is expected


def test_a_foreign_host_header_is_refused(server):
    """Blunts DNS rebinding: a page on the web resolving its own name to
    127.0.0.1 would otherwise reach this server through the browser."""
    base, _, _ = server
    request = urllib.request.Request(base + "/api/config")
    request.add_header("Host", "evil.example.com")
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(request, timeout=5)
    assert exc.value.code == 403


def test_the_server_binds_loopback_only(server):
    base, _, _ = server
    assert base.startswith("http://127.0.0.1:")
