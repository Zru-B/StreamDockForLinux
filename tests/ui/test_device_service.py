"""
Unit tests for DeviceService.

The Application is injected, so none of this needs hardware or a real HID
handle.
"""

import os
import tempfile
from unittest.mock import Mock

import pytest

from StreamDock.ui.device_service import (
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    STATE_ERROR,
    DeviceService,
)


CONFIG = """
streamdock:
  settings:
    brightness: 40
  keys:
    KeyA:
      text: "A"
      on_press_actions:
        - KEY_PRESS: "a"
  layouts:
    Main:
      Default: true
      keys:
        - 1: "KeyA"
"""


@pytest.fixture
def config_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.yml")
        with open(path, 'w') as f:
            f.write(CONFIG)
        yield path


def make_device(path='/dev/hidraw0', serial=''):
    return Mock(vendor_id=0x6603, product_id=0x1006, serial_number=serial,
                path=path, manufacturer='Test', product='StreamDock')


@pytest.fixture
def hardware():
    hw = Mock()
    hw.enumerate_devices = Mock(return_value=[make_device()])
    return hw


@pytest.fixture
def app():
    """A stand-in Application that starts successfully."""
    application = Mock()
    application.start = Mock(return_value=True)
    application.reload = Mock(return_value=True)
    application.get_config_path = Mock(return_value="")
    application.get_device = Mock(return_value=Mock())
    return application


@pytest.fixture
def service(app, hardware):
    factory = Mock(return_value=app)
    service = DeviceService(application_factory=factory,
                            hardware_factory=lambda: hardware)
    service.factory = factory
    return service


class TestDiscovery:
    """refresh_devices()."""

    def test_publishes_the_device_list(self, service, qtbot):
        with qtbot.waitSignal(service.devices_discovered) as blocker:
            service.refresh_devices()

        assert len(blocker.args[0]) == 1

    def test_enumeration_failure_is_reported_not_raised(self, app, qtbot):
        hardware = Mock()
        hardware.enumerate_devices = Mock(side_effect=OSError("usb exploded"))
        service = DeviceService(application_factory=Mock(return_value=app),
                                hardware_factory=lambda: hardware)

        with qtbot.waitSignal(service.devices_discovered) as blocker:
            service.refresh_devices()

        assert blocker.args[0] == []

    def test_reuses_the_open_hardware_once_connected(self, service, app, config_path,
                                                     hardware):
        service.connect_device("", config_path)
        open_hardware = Mock()
        open_hardware.enumerate_devices = Mock(return_value=[])
        app.get_hardware = Mock(return_value=open_hardware)

        service.refresh_devices()

        open_hardware.enumerate_devices.assert_called()


class TestConnect:
    """connect_device()."""

    def test_reports_connecting_then_connected(self, service, config_path, qtbot):
        states = []
        service.connection_state_changed.connect(lambda s, d: states.append(s))

        service.connect_device("", config_path)

        assert states == [STATE_CONNECTING, STATE_CONNECTED]

    def test_starts_the_runtime(self, service, app, config_path):
        service.connect_device("", config_path)

        app.start.assert_called_once()
        assert service.is_connected()

    def test_defaults_to_the_first_discovered_device(self, service, config_path):
        service.connect_device("", config_path)

        assert service.factory.call_args.kwargs['device_info'].path == '/dev/hidraw0'

    def test_selects_the_requested_device(self, app, config_path):
        first, second = make_device('/dev/hidraw0'), make_device('/dev/hidraw1')
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[first, second])
        factory = Mock(return_value=app)
        service = DeviceService(application_factory=factory,
                                hardware_factory=lambda: hardware)

        service.connect_device("6603:1006@/dev/hidraw1", config_path)

        assert factory.call_args.kwargs['device_info'].path == '/dev/hidraw1'

    def test_refuses_without_a_configuration(self, service, qtbot):
        with qtbot.waitSignal(service.error_occurred):
            service.connect_device("", "")

        assert not service.is_connected()

    def test_reports_when_no_device_is_attached(self, app, config_path, qtbot):
        hardware = Mock()
        hardware.enumerate_devices = Mock(return_value=[])
        service = DeviceService(application_factory=Mock(return_value=app),
                                hardware_factory=lambda: hardware)

        with qtbot.waitSignal(service.error_occurred):
            service.connect_device("", config_path)

        assert not service.is_connected()

    def test_a_failed_start_releases_the_device(self, hardware, config_path):
        """initialize() opens the HID handle before start() can fail."""
        app = Mock()
        app.start = Mock(return_value=False)
        service = DeviceService(application_factory=Mock(return_value=app),
                                hardware_factory=lambda: hardware)

        service.connect_device("", config_path)

        app.stop.assert_called_once_with(force=True)
        assert not service.is_connected()

    def test_a_device_that_will_not_open_is_not_reported_as_connected(
            self, hardware, config_path, qtbot):
        """Application.start() succeeds even when the device stayed shut."""
        app = Mock()
        app.start = Mock(return_value=True)
        app.get_device = Mock(return_value=None)
        service = DeviceService(application_factory=Mock(return_value=app),
                                hardware_factory=lambda: hardware)

        with qtbot.waitSignal(service.error_occurred) as blocker:
            service.connect_device("", config_path)

        assert not service.is_connected()
        assert "could not be opened" in blocker.args[1]
        app.stop.assert_called_once_with(force=True)

    def test_a_failed_start_reports_an_error(self, hardware, config_path, qtbot):
        app = Mock()
        app.start = Mock(return_value=False)
        service = DeviceService(application_factory=Mock(return_value=app),
                                hardware_factory=lambda: hardware)

        with qtbot.waitSignal(service.error_occurred):
            service.connect_device("", config_path)

    def test_a_raising_factory_is_reported(self, hardware, config_path, qtbot):
        service = DeviceService(
            application_factory=Mock(side_effect=RuntimeError("boom")),
            hardware_factory=lambda: hardware)

        with qtbot.waitSignal(service.connection_state_changed) as blocker:
            service.connect_device("", config_path)

        assert blocker.args[0] in (STATE_CONNECTING, STATE_ERROR)
        assert not service.is_connected()

    def test_connecting_again_replaces_the_previous_runtime(self, service, app,
                                                            config_path):
        service.connect_device("", config_path)
        service.connect_device("", config_path)

        app.stop.assert_called_with(force=True)
        assert service.factory.call_count == 2


class TestDisconnect:
    """disconnect_device()."""

    def test_stops_the_runtime(self, service, app, config_path):
        service.connect_device("", config_path)

        service.disconnect_device()

        app.stop.assert_called_with(force=True)
        assert not service.is_connected()

    def test_reports_disconnected(self, service, config_path, qtbot):
        service.connect_device("", config_path)

        with qtbot.waitSignal(service.connection_state_changed) as blocker:
            service.disconnect_device()

        assert blocker.args[0] == STATE_DISCONNECTED

    def test_is_safe_when_not_connected(self, service, qtbot):
        with qtbot.waitSignal(service.connection_state_changed) as blocker:
            service.disconnect_device()

        assert blocker.args[0] == STATE_DISCONNECTED

    def test_shutdown_releases_the_device(self, service, app, config_path):
        service.connect_device("", config_path)

        service.shutdown()

        app.stop.assert_called_with(force=True)


class TestApplyConfig:
    """apply_config()."""

    def valid_document(self):
        import yaml
        return yaml.safe_load(CONFIG)['streamdock']

    def test_applies_a_valid_document(self, service, app, config_path, qtbot):
        service.connect_device("", config_path)

        with qtbot.waitSignal(service.config_applied):
            service.apply_config(self.valid_document(), config_path)

        app.reload.assert_called_once()

    def test_refuses_when_not_connected(self, service, config_path, qtbot):
        with qtbot.waitSignal(service.error_occurred):
            service.apply_config(self.valid_document(), config_path)

    def test_an_invalid_document_never_reaches_the_device(self, service, app,
                                                          config_path, qtbot):
        service.connect_device("", config_path)

        with qtbot.waitSignal(service.error_occurred):
            service.apply_config({'settings': {'brightness': 500}}, config_path)

        app.reload.assert_not_called()

    def test_a_refused_reload_is_reported(self, service, app, config_path, qtbot):
        service.connect_device("", config_path)
        app.reload = Mock(return_value=False)

        with qtbot.waitSignal(service.error_occurred):
            service.apply_config(self.valid_document(), config_path)

    def test_the_document_is_copied_at_the_thread_boundary(self, service, app,
                                                           config_path):
        """The GUI stays editable while an apply is in flight."""
        service.connect_device("", config_path)
        document = self.valid_document()

        service.apply_config(document, config_path)

        passed = app.reload.call_args.kwargs['raw_document']
        assert passed == document and passed is not document


class TestBrightness:
    """set_brightness()."""

    def test_goes_through_the_orchestrator_lock(self, service, app, config_path):
        service.connect_device("", config_path)
        device, orchestrator = Mock(), Mock()
        orchestrator.run_exclusive = Mock(side_effect=lambda fn: fn())
        app.get_device = Mock(return_value=device)
        app.get_orchestrator = Mock(return_value=orchestrator)

        service.set_brightness(35)

        orchestrator.run_exclusive.assert_called_once()
        device.set_brightness.assert_called_once_with(35)

    def test_is_ignored_when_not_connected(self, service):
        service.set_brightness(35)


class TestBusySignal:
    """busy_changed brackets the slow operations."""

    def test_connect_brackets_with_busy(self, service, config_path):
        seen = []
        service.busy_changed.connect(seen.append)

        service.connect_device("", config_path)

        assert seen[0] is True and seen[-1] is False

    def test_busy_is_cleared_even_when_connecting_fails(self, hardware, config_path):
        service = DeviceService(
            application_factory=Mock(side_effect=RuntimeError("boom")),
            hardware_factory=lambda: hardware)
        seen = []
        service.busy_changed.connect(seen.append)

        service.connect_device("", config_path)

        assert seen[-1] is False


class TestHotplug:
    """Reacting to devices appearing and disappearing while running."""

    def connected(self, service, app, config_path, path='/dev/hidraw0'):
        """Connect, then report the current device via the app mock."""
        service.connect_device("", config_path)
        app.get_device_info = Mock(return_value=make_device(path))
        return service

    def test_unplugging_the_connected_device_releases_it(self, service, app,
                                                         config_path):
        self.connected(service, app, config_path)
        app.stop.reset_mock()

        service._on_devices_changed([])

        app.stop.assert_called_with(force=True)
        assert not service.is_connected()

    def test_unplugging_reports_which_device_went(self, service, app, config_path,
                                                  qtbot):
        self.connected(service, app, config_path)

        with qtbot.waitSignal(service.device_detached) as blocker:
            service._on_devices_changed([])

        assert 'StreamDock' in blocker.args[0]

    def test_unplugging_leaves_a_reason_in_the_state(self, service, app,
                                                     config_path):
        self.connected(service, app, config_path)
        states = []
        service.connection_state_changed.connect(lambda s, d: states.append((s, d)))

        service._on_devices_changed([])

        assert states[-1][0] == STATE_DISCONNECTED
        assert 'unplugged' in states[-1][1]

    def test_replugging_reconnects(self, service, app, config_path):
        self.connected(service, app, config_path)
        service._on_devices_changed([])
        assert not service.is_connected()

        service._on_devices_changed([make_device('/dev/hidraw0')])

        assert service.is_connected()

    def test_plugging_in_while_idle_connects(self, service, app, config_path,
                                             hardware):
        """Nothing attached at startup, then the user plugs one in."""
        hardware.enumerate_devices = Mock(return_value=[])
        service.connect_device("", config_path)
        assert not service.is_connected()

        service._on_devices_changed([make_device('/dev/hidraw0')])

        assert service.is_connected()

    def test_an_explicit_disconnect_is_not_undone_by_a_replug(self, service, app,
                                                              config_path):
        """Pressing Disconnect must stick."""
        self.connected(service, app, config_path)
        service.disconnect_device()

        service._on_devices_changed([make_device('/dev/hidraw0')])

        assert not service.is_connected()

    def test_a_new_device_is_announced(self, service, app, config_path, qtbot):
        self.connected(service, app, config_path)

        with qtbot.waitSignal(service.device_attached) as blocker:
            service._on_devices_changed([make_device('/dev/hidraw0'),
                                         make_device('/dev/hidraw1')])

        assert 'StreamDock' in blocker.args[0]

    def test_a_second_device_does_not_disturb_the_connection(self, service, app,
                                                             config_path):
        self.connected(service, app, config_path)

        service._on_devices_changed([make_device('/dev/hidraw0'),
                                     make_device('/dev/hidraw1')])

        assert service.is_connected()

    def test_the_device_list_is_republished_on_every_change(self, service, app,
                                                            config_path, qtbot):
        self.connected(service, app, config_path)

        with qtbot.waitSignal(service.devices_discovered) as blocker:
            service._on_devices_changed([make_device('/dev/hidraw1')])

        assert len(blocker.args[0]) == 1

    def test_reconnect_prefers_the_device_that_was_asked_for(self, app, hardware,
                                                             config_path):
        first, second = make_device('/dev/hidraw0'), make_device('/dev/hidraw1')
        hardware.enumerate_devices = Mock(return_value=[first, second])
        factory = Mock(return_value=app)
        service = DeviceService(application_factory=factory,
                                hardware_factory=lambda: hardware)
        service.connect_device('6603:1006@/dev/hidraw1', config_path)
        app.get_device_info = Mock(return_value=second)

        service._on_devices_changed([first])       # the chosen one goes away
        assert not service.is_connected(), "must not silently move to another dock"

        service._on_devices_changed([first, second])  # and comes back

        assert service.is_connected()
        assert factory.call_args.kwargs['device_info'].path == '/dev/hidraw1'

    def test_shutdown_stops_the_watcher(self, service, app, config_path):
        service.connect_device("", config_path)
        watcher = Mock()
        service._watcher = watcher

        service.shutdown()

        watcher.stop.assert_called_once()
