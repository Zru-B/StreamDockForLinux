"""
Building live Key and Layout objects from edge-case configurations.

This is the config -> device path, and it had no test file at all: the
existing Key and Layout tests use mocks and never invoke the renderer.
Everything here runs against a mock device, so no hardware is needed.
"""

import os
import tempfile
from unittest.mock import MagicMock, Mock

import pytest

from StreamDock.application.configuration_manager import ConfigurationManager
from StreamDock.application.layout_factory import LayoutFactory


@pytest.fixture
def device():
    return MagicMock()


@pytest.fixture
def workdir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def parsed(workdir, streamdock):
    """Validate and parse a subtree the way Application does."""
    return ConfigurationManager.parse_data(
        streamdock, os.path.join(workdir, "config.yml"))


def build(workdir, device, streamdock, action_executor=None):
    """Run the factory over a validated configuration."""
    config = parsed(workdir, streamdock)
    factory = LayoutFactory(config_data=config.raw_config, device=device,
                            action_executor=action_executor)
    return factory.create_layouts()


def key(text="A", **extra):
    return {"text": text, "on_press_actions": [{"KEY_PRESS": "a"}], **extra}


def config(keys=None, layouts=None, **rest):
    return {
        "keys": keys or {"KeyA": key()},
        "layouts": layouts or {"Main": {"Default": True, "keys": [{1: "KeyA"}]}},
        **rest,
    }


class TestLayoutSizes:
    """From one key up to a full deck."""

    def test_single_key_layout(self, workdir, device):
        default, layouts = build(workdir, device, config())

        assert default.name == "Main"
        assert len(default.keys) == 1
        assert len(layouts) == 1

    def test_full_fifteen_key_layout(self, workdir, device):
        keys = {f"K{n}": key(str(n)) for n in range(1, 16)}
        layouts = {"Main": {"Default": True,
                            "keys": [{n: f"K{n}"} for n in range(1, 16)]}}

        default, _ = build(workdir, device, config(keys, layouts))

        assert len(default.keys) == 15
        assert [k.key_number for k in default.keys] == list(range(1, 16))

    def test_positions_may_have_gaps(self, workdir, device):
        keys = {"KeyA": key(), "KeyB": key("B")}
        layouts = {"Main": {"Default": True, "keys": [{1: "KeyA"}, {15: "KeyB"}]}}

        default, _ = build(workdir, device, config(keys, layouts))

        assert [k.key_number for k in default.keys] == [1, 15]


class TestEmptyLayouts:
    """A layout of null slots is documented and must not crash."""

    def test_all_null_slots_builds_an_empty_layout(self, workdir, device):
        layouts = {"Main": {"Default": True, "keys": [{1: None}, {2: None}]}}

        default, _ = build(workdir, device, config(layouts=layouts))

        assert default.keys == []

    def test_an_empty_layout_applies_without_touching_keys(self, workdir, device):
        layouts = {"Main": {"Default": True, "keys": [{1: None}]}}
        default, _ = build(workdir, device, config(layouts=layouts))

        default.apply()

        device.set_key_image.assert_not_called()
        device.refresh.assert_called_once()

    def test_one_empty_layout_does_not_stop_the_others(self, workdir, device):
        """A single bad layout used to abort construction of every layout."""
        layouts = {
            "Empty": {"keys": [{1: None}]},
            "Main": {"Default": True, "keys": [{1: "KeyA"}]},
        }

        _, built = build(workdir, device, config(layouts=layouts))

        assert set(built) == {"Empty", "Main"}
        assert len(built["Main"].keys) == 1

    def test_null_slots_are_skipped_but_real_keys_kept(self, workdir, device):
        layouts = {"Main": {"Default": True,
                            "keys": [{1: None}, {2: "KeyA"}, {3: None}]}}

        default, _ = build(workdir, device, config(layouts=layouts))

        assert len(default.keys) == 1
        assert default.keys[0].key_number == 2


class TestKeysAndLayouts:
    """Which keys end up where."""

    def test_a_key_used_by_no_layout_is_built_but_unplaced(self, workdir, device):
        keys = {"KeyA": key(), "Orphan": key("O")}

        default, _ = build(workdir, device, config(keys))

        assert len(default.keys) == 1
        assert default.keys[0].key_number == 1

    def test_layouts_sharing_a_key_at_the_same_position(self, workdir, device):
        layouts = {
            "Main": {"Default": True, "keys": [{1: "KeyA"}]},
            "Other": {"keys": [{1: "KeyA"}]},
        }

        _, built = build(workdir, device, config(layouts=layouts))

        assert built["Main"].keys[0].key_number == 1
        assert built["Other"].keys[0].key_number == 1

    def test_the_default_layout_is_the_one_marked_default(self, workdir, device):
        layouts = {
            "First": {"keys": [{1: "KeyA"}]},
            "Second": {"Default": True, "keys": [{2: "KeyA"}]},
        }

        default, _ = build(workdir, device, config(layouts=layouts))

        assert default.name == "Second"

    def test_clear_all_is_carried_onto_the_layout(self, workdir, device):
        layouts = {"Main": {"Default": True, "clear_all": True,
                            "keys": [{1: "KeyA"}]}}

        default, _ = build(workdir, device, config(layouts=layouts))
        default.apply()

        assert default.clear_all is True
        device.clear_all_icons.assert_called_once()


class TestKeyRendering:
    """The renderer is reached for the first time by these tests."""

    @pytest.mark.parametrize("text", [
        "A",
        "日本語",
        "🚀🎹",
        "x" * 200,
        "averyveryverylongunbrokenwordwithnospaces",
        "multi word text that wraps",
    ])
    def test_text_keys_render_without_raising(self, workdir, device, text):
        default, _ = build(workdir, device, config({"KeyA": key(text)}))

        default.apply()

        device.set_key_image.assert_called_once()
        rendered = device.set_key_image.call_args[0][1]
        assert rendered and os.path.exists(rendered)

    @pytest.mark.parametrize("font_size", [1, 8, 20, 72, 200])
    def test_font_sizes_across_the_allowed_range(self, workdir, device, font_size):
        default, _ = build(workdir, device,
                           config({"KeyA": key(font_size=font_size)}))

        default.apply()

        device.set_key_image.assert_called_once()

    @pytest.mark.parametrize("colors", [
        {"text_color": "white", "background_color": "black"},
        {"text_color": "#FF0000", "background_color": "#00FF00"},
        {"text_color": "red", "background_color": "navy"},
    ])
    def test_colour_forms(self, workdir, device, colors):
        default, _ = build(workdir, device, config({"KeyA": key(**colors)}))

        default.apply()

        device.set_key_image.assert_called_once()

    def test_bold_false(self, workdir, device):
        default, _ = build(workdir, device, config({"KeyA": key(bold=False)}))

        default.apply()

        device.set_key_image.assert_called_once()

    def test_an_icon_key_passes_the_icon_path_through(self, workdir, device):
        icon = os.path.join(workdir, "icon.png")
        with open(icon, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
        keys = {"KeyA": {"icon": "icon.png",
                         "on_press_actions": [{"KEY_PRESS": "a"}]}}

        default, _ = build(workdir, device, config(keys))
        default.apply()

        assert device.set_key_image.call_args[0][1] == icon


class TestActions:
    """Action wiring, including the shapes that are silently dropped."""

    def test_callbacks_are_registered_for_each_key(self, workdir, device):
        default, _ = build(workdir, device, config(), action_executor=Mock())

        default.apply()

        device.set_per_key_callback.assert_called_once()

    def test_all_three_action_lists_are_wired(self, workdir, device):
        keys = {"KeyA": {"text": "A",
                         "on_press_actions": [{"KEY_PRESS": "a"}],
                         "on_release_actions": [{"KEY_PRESS": "b"}],
                         "on_double_press_actions": [{"KEY_PRESS": "c"}]}}

        default, _ = build(workdir, device, config(keys), action_executor=Mock())
        default.apply()

        kwargs = device.set_per_key_callback.call_args.kwargs
        assert kwargs['on_press'] is not None
        assert kwargs['on_release'] is not None
        assert kwargs['on_double_press'] is not None

    def test_a_lowercase_action_name_is_dropped(self, workdir, device):
        """Known gap: it passes validation, then the factory discards it."""
        keys = {"KeyA": {"text": "A", "on_press_actions": [{"key_press": "a"}]}}

        default, _ = build(workdir, device, config(keys), action_executor=Mock())

        assert default.keys[0].on_press_actions == []

    def test_a_bare_string_action_is_dropped(self, workdir, device):
        """Also validated and also discarded."""
        keys = {"KeyA": {"text": "A", "on_press_actions": ["DEVICE_BRIGHTNESS_UP"]}}

        default, _ = build(workdir, device, config(keys), action_executor=Mock())

        assert default.keys[0].on_press_actions == []

    def test_change_layout_shorthand_is_normalised(self, workdir, device):
        layouts = {
            "Main": {"Default": True, "keys": [{1: "KeyA"}]},
            "Other": {"keys": [{1: "KeyA"}]},
        }
        keys = {"KeyA": {"text": "A",
                         "on_press_actions": [{"CHANGE_LAYOUT": "Other"}]}}

        default, _ = build(workdir, device, config(keys, layouts),
                           action_executor=Mock())

        _, parameter = default.keys[0].on_press_actions[0]
        assert parameter == {"layout": "Other"}


class TestThroughApplication:
    """The same configurations, driven through the real Application."""

    @pytest.fixture(autouse=True)
    def mock_window_manager(self):
        from unittest.mock import patch
        with patch('StreamDock.application.application.LinuxWindowManager') as mock:
            yield mock

    def initialize(self, workdir, streamdock, device):
        from unittest.mock import patch
        import yaml

        from StreamDock.application import Application

        path = os.path.join(workdir, "config.yml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump({"streamdock": streamdock}, f, sort_keys=False)

        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[
            Mock(vendor_id=0x6603, product_id=0x1006, serial_number='S',
                 path='/dev/hidraw0', manufacturer='', product='Dock')])

        app = Application(path)
        with patch('StreamDock.application.application.USBHardware',
                   return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device):
            app.initialize()
        return app

    @pytest.mark.parametrize("brightness", [0, 100, 1, 99])
    def test_brightness_extremes_reach_the_device(self, workdir, device, brightness):
        app = self.initialize(
            workdir, config(**{"settings": {"brightness": brightness}}), device)

        device.init.assert_called_once_with(brightness)
        assert app.get_config().brightness == brightness

    def test_a_layout_of_null_slots_initializes(self, workdir, device):
        """This used to raise ValueError out of the factory."""
        layouts = {"Main": {"Default": True, "keys": [{1: None}]}}

        app = self.initialize(workdir, config(layouts=layouts), device)

        assert app.is_initialized()
        assert app.get_current_layout_name() == "Main"

    def test_a_full_deck_initializes(self, workdir, device):
        keys = {f"K{n}": key(str(n)) for n in range(1, 16)}
        layouts = {"Main": {"Default": True,
                            "keys": [{n: f"K{n}"} for n in range(1, 16)]}}

        app = self.initialize(workdir, config(keys, layouts), device)

        assert app.is_initialized()
        assert device.set_key_image.call_count == 15

    def test_unicode_keys_initialize(self, workdir, device):
        keys = {"Ключ": key("日本 🚀")}
        layouts = {"Основной": {"Default": True, "keys": [{1: "Ключ"}]}}

        app = self.initialize(workdir, config(keys, layouts), device)

        assert app.get_current_layout_name() == "Основной"
