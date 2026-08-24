from dataclasses import replace

from usb_lcd_dashboard.config import Config, load_config
from usb_lcd_dashboard.layout import Tile
from usb_lcd_dashboard.profiles import PanelIdentity, ProfileStore, profile_key_for_config


def test_existing_configs_map_to_stable_hardware_keys():
    assert profile_key_for_config(Config()) == "legacy-480x320"
    assert profile_key_for_config(replace(Config(), width=1920, height=462)) == "turzx-0092"


def test_first_activation_preserves_an_existing_matching_layout(tmp_path):
    path = tmp_path / "config.toml"
    wide = replace(
        Config(),
        display_kind="auto",
        width=1920,
        height=462,
        tiles=(Tile("clock", 0, 0, 1920, 462),),
    )
    store = ProfileStore(path)
    selected = store.activate(
        PanelIdentity("turzx-0092", "turing_usb", (1920, 462)), wide
    )

    assert selected.tiles == wide.tiles
    assert load_config(store.path_for("turzx-0092")).tiles == wide.tiles


def test_switching_panels_restores_each_saved_profile(tmp_path):
    path = tmp_path / "config.toml"
    store = ProfileStore(path)
    legacy_panel = PanelIdentity("legacy-480x320", "turing_rev_a", (480, 320), "COM10")
    wide_panel = PanelIdentity("turzx-0092", "turing_usb", (1920, 462))

    legacy = replace(Config(), display_kind="auto", idle_title="WORK")
    store.activate(legacy_panel, legacy)
    edited_legacy = replace(legacy, idle_title="SMALL SAVED")
    wide = store.activate(wide_panel, edited_legacy)
    edited_wide = replace(wide, idle_title="LARGE SAVED")
    restored = store.activate(legacy_panel, edited_wide)

    assert restored.size == (480, 320)
    assert restored.idle_title == "SMALL SAVED"
    assert load_config(store.path_for("turzx-0092")).idle_title == "LARGE SAVED"


def test_a_new_panel_gets_a_valid_full_canvas_layout(tmp_path):
    store = ProfileStore(tmp_path / "config.toml")
    selected = store.activate(
        PanelIdentity("turzx-0092", "turing_usb", (1920, 462)), Config()
    )
    assert selected.size == (1920, 462)
    assert selected.tiles == (Tile("legacy", 0, 0, 1920, 462),)
