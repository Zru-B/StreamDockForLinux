"""
Tests for Application.reload() and device selection.

reload() backs the GUI's "Apply to Device" button. The contract that matters:
it must not disconnect the device, it must clear stale state, and an invalid
configuration must leave the running one alone.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from StreamDock.application import Application
from StreamDock.application.configuration_manager import ConfigValidationError


CONFIG_TEMPLATE = """
streamdock:
  settings:
    brightness: {brightness}
  keys:
    {key_name}:
      text: "A"
      on_press_actions:
        - KEY_PRESS: "{key_press}"
  layouts:
    {layout_name}:
      Default: true
      keys:
        - 1: "{key_name}"
"""


class TestApplicationReload:
    """Application.reload()."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture(autouse=True)
    def mock_window_manager(self):
        with patch('StreamDock.application.application.LinuxWindowManager') as mock:
            yield mock

    @pytest.fixture
    def device_info(self):
        return Mock(vendor_id=0x6603, product_id=0x1006, serial_number='SERIAL',
                    path='/dev/hidraw0', manufacturer='Test', product='StreamDock')

    def write_config(self, temp_dir, *, brightness=50, key_name="KeyA",
                     layout_name="Main", key_press="a", name="config.yml"):
        path = os.path.join(temp_dir, name)
        with open(path, 'w') as f:
            f.write(CONFIG_TEMPLATE.format(brightness=brightness, key_name=key_name,
                                           layout_name=layout_name, key_press=key_press))
        return path

    def build_app(self, config_path, device, device_info, **kwargs):
        """Initialize an Application against a mocked device."""
        app = Application(config_path, **kwargs)

        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[device_info])

        with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device):
            app.initialize()

        return app

    @pytest.fixture
    def device(self):
        device = Mock()
        device.open = Mock(return_value=True)
        return device

    # ── the core contract ────────────────────────────────────────────────

    def test_reload_keeps_the_device_connected(self, temp_dir, device, device_info):
        """A full stop/start would blank the deck on every Apply."""
        app = self.build_app(self.write_config(temp_dir), device, device_info)
        device.close.reset_mock()

        assert app.reload() is True

        device.close.assert_not_called()

    def test_reload_clears_stale_callbacks(self, temp_dir, device, device_info):
        """set_per_key_callback only overwrites keys the new layout defines."""
        app = self.build_app(self.write_config(temp_dir), device, device_info)
        device.clear_all_callbacks.reset_mock()

        app.reload()

        device.clear_all_callbacks.assert_called_once()

    def test_reload_clears_stale_images(self, temp_dir, device, device_info):
        app = self.build_app(self.write_config(temp_dir), device, device_info)
        device.clear_all_icons.reset_mock()

        app.reload()

        device.clear_all_icons.assert_called_once()

    def test_reload_applies_the_new_brightness(self, temp_dir, device, device_info):
        app = self.build_app(self.write_config(temp_dir, brightness=20),
                             device, device_info)

        app.reload(self.write_config(temp_dir, brightness=90, name="other.yml"))

        device.set_brightness.assert_called_with(90)
        assert app.get_config().brightness == 90

    def test_reload_switches_to_the_new_config_file(self, temp_dir, device, device_info):
        app = self.build_app(self.write_config(temp_dir), device, device_info)
        other = self.write_config(temp_dir, layout_name="Other", name="other.yml")

        assert app.reload(other) is True

        assert app.get_config_path() == other
        assert app.get_config().default_layout_name == "Other"

    def test_reload_accepts_an_unsaved_document(self, temp_dir, device, device_info):
        """Apply must work on edits that were never written to disk."""
        from StreamDock.application.config_document import ConfigDocument

        config_path = self.write_config(temp_dir)
        app = self.build_app(config_path, device, device_info)

        document = ConfigDocument.load(config_path)
        document.settings.brightness = 42

        assert app.reload(raw_document=document.to_dict()['streamdock']) is True
        assert app.get_config().brightness == 42

    # ── failure leaves the running config alone ──────────────────────────

    def test_invalid_config_is_refused(self, temp_dir, device, device_info):
        app = self.build_app(self.write_config(temp_dir, brightness=20),
                             device, device_info)

        bad = os.path.join(temp_dir, "bad.yml")
        with open(bad, 'w') as f:
            f.write("streamdock:\n  settings:\n    brightness: 500\n")

        assert app.reload(bad) is False

    def test_refused_reload_keeps_the_previous_config(self, temp_dir, device, device_info):
        config_path = self.write_config(temp_dir, brightness=20)
        app = self.build_app(config_path, device, device_info)

        bad = os.path.join(temp_dir, "bad.yml")
        with open(bad, 'w') as f:
            f.write("streamdock:\n  settings:\n    brightness: 500\n")
        app.reload(bad)

        assert app.get_config().brightness == 20
        assert app.get_config_path() == config_path

    def test_refused_reload_does_not_touch_the_device(self, temp_dir, device, device_info):
        app = self.build_app(self.write_config(temp_dir), device, device_info)
        device.clear_all_icons.reset_mock()
        device.close.reset_mock()

        app.reload(raw_document={'settings': {'brightness': 500}})

        device.clear_all_icons.assert_not_called()
        device.close.assert_not_called()

    def test_reload_before_initialize_is_refused(self, temp_dir):
        assert Application(self.write_config(temp_dir)).reload() is False


class TestDeviceSelection:
    """Application honours a chosen device."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture(autouse=True)
    def mock_window_manager(self):
        with patch('StreamDock.application.application.LinuxWindowManager') as mock:
            yield mock

    def make_info(self, path):
        return Mock(vendor_id=0x6603, product_id=0x1006, serial_number='',
                    path=path, manufacturer='', product='StreamDock')

    def initialize_with(self, config_path, discovered, device_info=None):
        device = Mock()
        device.open = Mock(return_value=True)
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=discovered)

        app = Application(config_path, device_info=device_info)
        with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device) as ctor:
            app.initialize()

        return app, ctor

    @pytest.fixture
    def config_path(self, temp_dir):
        path = os.path.join(temp_dir, "config.yml")
        with open(path, 'w') as f:
            f.write(CONFIG_TEMPLATE.format(brightness=50, key_name="KeyA",
                                           layout_name="Main", key_press="a"))
        return path

    def test_defaults_to_the_first_discovered_device(self, config_path):
        first, second = self.make_info('/dev/hidraw0'), self.make_info('/dev/hidraw1')

        app, ctor = self.initialize_with(config_path, [first, second])

        assert ctor.call_args[0][1]['path'] == '/dev/hidraw0'
        assert app.get_device_info() is first

    def test_opens_the_requested_device(self, config_path):
        first, second = self.make_info('/dev/hidraw0'), self.make_info('/dev/hidraw1')

        app, ctor = self.initialize_with(config_path, [first, second], device_info=second)

        assert ctor.call_args[0][1]['path'] == '/dev/hidraw1'
        assert app.get_device_info() is second

    def test_falls_back_when_the_requested_device_is_gone(self, config_path):
        present = self.make_info('/dev/hidraw0')
        missing = self.make_info('/dev/hidraw9')

        app, _ = self.initialize_with(config_path, [present], device_info=missing)

        assert app.get_device_info() is present

    def test_no_devices_leaves_the_application_deviceless(self, config_path):
        app, ctor = self.initialize_with(config_path, [])

        ctor.assert_not_called()
        assert app.get_device() is None


class TestStopHardening:
    """A failed start must not leak the HID handle."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture(autouse=True)
    def mock_window_manager(self):
        with patch('StreamDock.application.application.LinuxWindowManager') as mock:
            yield mock

    @pytest.fixture
    def config_path(self, temp_dir):
        path = os.path.join(temp_dir, "config.yml")
        with open(path, 'w') as f:
            f.write(CONFIG_TEMPLATE.format(brightness=50, key_name="KeyA",
                                           layout_name="Main", key_press="a"))
        return path

    def build(self, config_path):
        device = Mock()
        device.open = Mock(return_value=True)
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[
            Mock(vendor_id=0x6603, product_id=0x1006, serial_number='S',
                 path='/dev/hidraw0', manufacturer='', product='')])

        app = Application(config_path)
        with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device):
            app.initialize()
        return app, device

    def test_stop_without_force_is_a_noop_when_never_started(self, config_path):
        app, device = self.build(config_path)
        device.close.reset_mock()

        app.stop()

        device.close.assert_not_called()

    def test_stop_with_force_releases_an_initialized_but_unstarted_device(self, config_path):
        app, device = self.build(config_path)
        device.close.reset_mock()

        app.stop(force=True)

        device.close.assert_called()
        assert app.get_device() is None

    def test_stop_can_keep_the_device(self, config_path):
        app, device = self.build(config_path)
        device.close.reset_mock()

        app.stop(force=True, release_devices=False)

        device.close.assert_not_called()


class TestLayoutChangedHook:
    """The GUI learns about layout changes through a plain callable."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture(autouse=True)
    def mock_window_manager(self):
        with patch('StreamDock.application.application.LinuxWindowManager') as mock:
            yield mock

    def test_hook_fires_with_the_default_layout(self, temp_dir):
        path = os.path.join(temp_dir, "config.yml")
        with open(path, 'w') as f:
            f.write(CONFIG_TEMPLATE.format(brightness=50, key_name="KeyA",
                                           layout_name="Main", key_press="a"))

        seen = []
        device = Mock()
        device.open = Mock(return_value=True)
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[
            Mock(vendor_id=0x6603, product_id=0x1006, serial_number='S',
                 path='/dev/hidraw0', manufacturer='', product='')])

        app = Application(path, on_layout_changed=seen.append)
        with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device):
            app.initialize()

        assert seen == ["Main"]
        assert app.get_current_layout_name() == "Main"

    def test_a_raising_hook_does_not_break_initialization(self, temp_dir):
        path = os.path.join(temp_dir, "config.yml")
        with open(path, 'w') as f:
            f.write(CONFIG_TEMPLATE.format(brightness=50, key_name="KeyA",
                                           layout_name="Main", key_press="a"))

        def boom(_name):
            raise RuntimeError("hook exploded")

        device = Mock()
        device.open = Mock(return_value=True)
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[
            Mock(vendor_id=0x6603, product_id=0x1006, serial_number='S',
                 path='/dev/hidraw0', manufacturer='', product='')])

        app = Application(path, on_layout_changed=boom)
        with patch('StreamDock.application.application.USBHardware', return_value=hardware), \
             patch('StreamDock.application.application.LinuxSystemInterface'), \
             patch('StreamDock.devices.stream_dock_293_v3.StreamDock293V3',
                   return_value=device):
            app.initialize()

        assert app.is_initialized()
