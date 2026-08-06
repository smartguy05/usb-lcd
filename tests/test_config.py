import tomllib
from dataclasses import replace
from pathlib import Path

import pytest

from usb_lcd_dashboard.config import (
    ADMIN_HOST,
    Config,
    default_config_toml,
    dump_config_toml,
    load_config,
    write_config,
)
from usb_lcd_dashboard.layout import Tile


ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = {
    ROOT / "config.example.toml": ("/dev/turing-lcd", "unix"),
    ROOT / "packaging/windows/config.example.toml": ("AUTO", "tcp"),
}


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("path", sorted(EXAMPLES, key=str), ids=lambda p: p.name)
def test_example_configs_have_not_drifted_from_the_defaults(path):
    """The example files are generated from Config(), so they cannot disagree.

    They used to be hand-maintained copies of the same table alongside a literal
    in install() — four places to remember when adding a key.
    """
    device, ipc_mode = EXAMPLES[path]
    assert path.read_text(encoding="utf-8") == default_config_toml(device, ipc_mode)


@pytest.mark.parametrize("path", sorted(EXAMPLES, key=str), ids=lambda p: p.name)
def test_example_configs_load_to_the_defaults(tmp_path, path):
    device, ipc_mode = EXAMPLES[path]
    loaded = load_config(write(tmp_path, path.read_text(encoding="utf-8")))
    defaults = Config()
    for field in Config.__dataclass_fields__:
        if field == "device":
            assert loaded.device == device
        elif field == "ipc_mode":
            assert loaded.ipc_mode == ipc_mode
        elif field == "tiles":
            # A config with no [[tile]] gets the legacy full-screen layout.
            assert loaded.tiles == (Tile("legacy", 0, 0, 480, 320),)
        else:
            assert getattr(loaded, field) == getattr(defaults, field), field


def test_default_config_toml_is_parseable():
    assert tomllib.loads(default_config_toml())["dashboard"]["idle_title"] == "AI WORKBENCH"


# ------------------------------------------------------------------ the layout

WIDE = """
[display]
kind = "simulated"
width = 1920
height = 462

[display.background]
color = "#081018"
fit = "cover"

[[tile]]
widget = "legacy"
x = 12
y = 12
w = 404
h = 438
[tile.options]
title = "HOME"
hour12 = true

[[tile]]
widget = "legacy"
x = 428
y = 12
w = 486
h = 438
"""


def test_a_tile_layout_parses_with_its_rects_and_options(tmp_path):
    cfg = load_config(write(tmp_path, WIDE))
    assert cfg.display_kind == "simulated"
    assert cfg.size == (1920, 462)
    assert len(cfg.tiles) == 2
    assert cfg.tiles[0] == Tile(
        "legacy", 12, 12, 404, 438, {"title": "HOME", "hour12": True}
    )
    assert cfg.tiles[1].rect == (428, 12, 914, 450)
    assert cfg.background is not None
    assert cfg.background.color == "#081018"
    assert cfg.background.fit == "cover"


def test_no_background_table_means_no_background(tmp_path):
    assert load_config(write(tmp_path, "[display]\n")).background is None


def test_a_background_image_that_is_absent_warns_but_loads(tmp_path, caplog):
    text = '[display.background]\nimage = "%s"\n' % (tmp_path / "nope.png").as_posix()
    with caplog.at_level("WARNING"):
        cfg = load_config(write(tmp_path, text))
    assert cfg.background is not None and cfg.background.image is not None
    assert any("does not exist" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    "text,match",
    [
        ('[display]\nkind = "plasma"\n', "display.kind must be one of"),
        ("[display]\nwidth = 0\n", "between 1 and 4096"),
        ("[display]\nheight = 9000\n", "between 1 and 4096"),
        ('[display.background]\nfit = "squish"\n', "background.fit must be one of"),
        ('[[tile]]\nwidget = "legacy"\nx = 0\ny = 0\nw = 10\n', "missing"),
        ('[[tile]]\nwidget = "nope"\nx = 0\ny = 0\nw = 10\nh = 10\n', "not a known widget"),
        (
            '[[tile]]\nwidget = "legacy"\nx = 0\ny = 0\nw = 100\nh = 100\n'
            '[[tile]]\nwidget = "legacy"\nx = 50\ny = 50\nw = 100\nh = 100\n',
            "overlaps",
        ),
        (
            '[display]\nwidth = 480\nheight = 320\n'
            '[[tile]]\nwidget = "legacy"\nx = 400\ny = 0\nw = 200\nh = 100\n',
            "does not fit",
        ),
    ],
)
def test_a_broken_layout_is_rejected_at_load_time(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        load_config(write(tmp_path, text))


# -------------------------------------------------------------- round-tripping

def test_dump_round_trips_through_the_loader(tmp_path):
    """The editor writes config.toml, so what we emit must be what we read."""
    original = load_config(write(tmp_path, WIDE))
    again = load_config(write(tmp_path, dump_config_toml(original)))
    assert again == original


def test_dump_round_trips_the_default_config(tmp_path):
    original = load_config(tmp_path / "absent.toml")
    assert load_config(write(tmp_path, dump_config_toml(original))) == original


def test_dump_preserves_tile_options_of_every_type(tmp_path):
    text = (
        '[display]\nwidth = 800\nheight = 400\n'
        '[[tile]]\nwidget = "clock"\nx = 0\ny = 0\nw = 800\nh = 400\n'
        '[tile.options]\ntitle = "HOME"\nhour12 = true\nseconds = false\n'
        'opacity = 0.75\nbackground = "#101c28"\n'
    )
    original = load_config(write(tmp_path, text))
    again = load_config(write(tmp_path, dump_config_toml(original)))
    assert again.tiles[0].options == {
        "title": "HOME",
        "hour12": True,
        "seconds": False,
        "opacity": 0.75,
        "background": "#101c28",
    }
    assert again == original


def test_dump_survives_a_windows_path_in_the_background_image(tmp_path):
    wallpaper = tmp_path / "wall.png"
    wallpaper.write_bytes(b"")
    text = f'[display.background]\nimage = "{wallpaper.as_posix()}"\nfit = "contain"\n'
    original = load_config(write(tmp_path, text))
    dumped = dump_config_toml(original)
    again = load_config(write(tmp_path, dumped))
    assert again.background.image == original.background.image
    assert again.background.fit == "contain"
    assert "\\" not in dumped, "paths should be emitted with forward slashes"


def test_write_config_replaces_the_file_atomically(tmp_path):
    target = tmp_path / "config.toml"
    target.write_text('[display]\nwidth = 480\nheight = 320\n', encoding="utf-8")
    cfg = load_config(target)
    written = write_config(replace(cfg, brightness=41), target)
    assert written == target
    assert load_config(target).brightness == 41
    assert not (tmp_path / "config.toml.tmp").exists(), "temp file left behind"


def test_write_config_creates_the_parent_directory(tmp_path):
    target = tmp_path / "nested" / "deeper" / "config.toml"
    write_config(Config(), target)
    assert target.exists()


# ------------------------------------------------------------------ the editor

def test_the_admin_editor_is_enabled_on_a_loopback_port_by_default():
    cfg = Config()
    assert cfg.admin_enabled is True
    assert cfg.admin_port == 45723
    assert ADMIN_HOST == "127.0.0.1"


def test_the_admin_block_is_parsed(tmp_path):
    cfg = load_config(write(tmp_path, "[admin]\nenabled = false\nport = 45999\n"))
    assert cfg.admin_enabled is False
    assert cfg.admin_port == 45999


@pytest.mark.parametrize(
    "text,match",
    [
        ("[admin]\nport = 80\n", "admin.port must be"),
        ("[admin]\nport = 45722\n", "must differ"),
    ],
)
def test_a_bad_admin_port_is_rejected(tmp_path, text, match):
    with pytest.raises(ValueError, match=match):
        load_config(write(tmp_path, text))


def test_a_missing_config_file_still_gets_the_legacy_layout(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg.tiles == (Tile("legacy", 0, 0, 480, 320),)
    assert cfg.size == (480, 320)
