"""
Unit tests for DeviceBar.
"""

from unittest.mock import Mock

import pytest

from StreamDock.ui.device_bar import DeviceBar
from StreamDock.ui.device_service import (
    STATE_CONNECTED,
    STATE_DISCONNECTED,
    STATE_ERROR,
)


def make_device(path, serial=''):
    return Mock(vendor_id=0x6603, product_id=0x1006, serial_number=serial,
                path=path, manufacturer='Test', product='StreamDock')


@pytest.fixture
def bar(qtbot):
    widget = DeviceBar()
    qtbot.addWidget(widget)
    return widget


class TestDeviceList:
    """set_devices()."""

    def test_first_device_is_selected_by_default(self, bar):
        bar.set_devices([make_device('/dev/hidraw0'), make_device('/dev/hidraw1')])

        assert bar.selected_device_id() == '6603:1006@/dev/hidraw0'

    def test_selection_survives_a_refresh(self, bar):
        first, second = make_device('/dev/hidraw0'), make_device('/dev/hidraw1')
        bar.set_devices([first, second])
        bar.device_combo.setCurrentIndex(1)

        bar.set_devices([first, second])

        assert bar.selected_device_id() == '6603:1006@/dev/hidraw1'

    def test_falls_back_to_the_first_when_the_selection_disappears(self, bar):
        first, second = make_device('/dev/hidraw0'), make_device('/dev/hidraw1')
        bar.set_devices([first, second])
        bar.device_combo.setCurrentIndex(1)

        bar.set_devices([first])

        assert bar.selected_device_id() == '6603:1006@/dev/hidraw0'

    def test_empty_list_disables_connect(self, bar):
        bar.set_devices([])

        assert bar.selected_device_id() is None
        assert not bar.connect_button.isEnabled()

    def test_devices_are_labelled_readably(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])

        assert 'StreamDock' in bar.device_combo.currentText()


class TestState:
    """set_state()."""

    def test_connecting_alone_does_not_enable_apply(self, bar):
        """Connecting applies the configuration, so there is nothing to send."""
        bar.set_devices([make_device('/dev/hidraw0')])

        bar.set_state(STATE_CONNECTED, 'StreamDock')

        assert not bar.apply_button.isEnabled()
        assert bar.connect_button.text() == 'Disconnect'

    def test_apply_enables_once_the_config_diverges(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])
        bar.set_state(STATE_CONNECTED, 'StreamDock')

        bar.set_needs_apply(True)

        assert bar.apply_button.isEnabled()

    def test_apply_stays_disabled_while_disconnected(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])

        bar.set_needs_apply(True)

        assert not bar.apply_button.isEnabled()

    def test_disconnected_disables_apply(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])

        bar.set_state(STATE_DISCONNECTED)

        assert not bar.apply_button.isEnabled()
        assert bar.connect_button.text() == 'Connect'

    def test_state_drives_the_indicator_colour(self, bar):
        bar.set_state(STATE_ERROR, 'boom')

        assert bar.status_dot.property('state') == STATE_ERROR

    def test_the_picker_is_locked_while_connected(self, bar):
        """Switching device mid-session would silently do nothing."""
        bar.set_devices([make_device('/dev/hidraw0')])

        bar.set_state(STATE_CONNECTED, 'StreamDock')

        assert not bar.device_combo.isEnabled()


class TestBusy:
    """set_busy()."""

    def test_busy_disables_the_controls(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])

        bar.set_busy(True)

        assert not bar.connect_button.isEnabled()
        assert not bar.apply_button.isEnabled()
        assert not bar.refresh_button.isEnabled()

    def test_clearing_busy_restores_them(self, bar):
        bar.set_devices([make_device('/dev/hidraw0')])
        bar.set_busy(True)

        bar.set_busy(False)

        assert bar.connect_button.isEnabled()


class TestSignals:
    """Button presses reach the application."""

    def test_connect_emits_the_selected_device(self, bar, qtbot):
        bar.set_devices([make_device('/dev/hidraw0')])

        with qtbot.waitSignal(bar.connect_requested) as blocker:
            bar.connect_button.click()

        assert blocker.args == ['6603:1006@/dev/hidraw0']

    def test_connect_button_disconnects_when_connected(self, bar, qtbot):
        bar.set_devices([make_device('/dev/hidraw0')])
        bar.set_state(STATE_CONNECTED, 'StreamDock')

        with qtbot.waitSignal(bar.disconnect_requested):
            bar.connect_button.click()

    def test_apply_emits(self, bar, qtbot):
        bar.set_devices([make_device('/dev/hidraw0')])
        bar.set_state(STATE_CONNECTED, 'StreamDock')
        bar.set_needs_apply(True)

        with qtbot.waitSignal(bar.apply_requested):
            bar.apply_button.click()

    def test_refresh_emits(self, bar, qtbot):
        with qtbot.waitSignal(bar.refresh_requested):
            bar.refresh_button.click()
