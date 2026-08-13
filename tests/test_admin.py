import json
import urllib.error
import urllib.request
from dataclasses import replace

import pytest
from PIL import Image

from usb_lcd_dashboard import admin
from usb_lcd_dashboard.admin import (
    AdminState,
    config_from_json,
    config_to_json,
    _host_is_loopback,
)
from usb_lcd_dashboard.config import Config, load_config
from usb_lcd_dashboard.layout import Tile


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


@pytest.fixture
def state(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(WIDE, encoding="utf-8")
    holder = {"config": load_config(path), "frame": None}
    return AdminState(
        config_path=path,
        get_config=lambda: holder["config"],
        get_preview=lambda: holder["frame"],
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
    payload["tiles"][0]["options"]["title"] = "HOME"
    result = config_from_json(holder["config"], payload)
    assert result.brightness == 41
    assert result.idle_title == "HOME"
    assert result.tiles[0].options["title"] == "HOME"


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
    assert set(widgets) == {"agent", "clock", "crab", "legacy"}
    assert widgets["agent"]["wants_session"] is True
    assert widgets["crab"]["wants_session"] is True
    assert any(o["name"] == "hour12" for o in widgets["clock"]["options"])


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
