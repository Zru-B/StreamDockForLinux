"""
The Device Settings panel: the brightness slider and the lock switch, plus the
Advanced Settings dialog with its gesture timings.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog

from StreamDock.application.config_document import (
    DEFAULT_DOUBLE_PRESS_INTERVAL,
    DEFAULT_LONG_PRESS_DURATION,
    MIN_BRIGHTNESS,
)
from StreamDock.ui.dialogs import AdvancedSettingsDialog
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.widgets import ToggleSwitch


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def switch(qtbot):
    s = ToggleSwitch("Turn it off")
    qtbot.addWidget(s)
    return s


class TestBrightnessSlider:
    """The device ignores anything below MIN_BRIGHTNESS, so the slider stops there."""

    def test_the_slider_does_not_go_below_the_device_minimum(self, window):
        assert window.brightness_slider.minimum() == MIN_BRIGHTNESS
        assert window.brightness_slider.maximum() == 100

    def test_a_dimmer_value_is_pulled_up_to_the_minimum(self, window):
        window.brightness_slider.setValue(1)

        assert window.brightness_slider.value() == MIN_BRIGHTNESS

    def test_moving_the_slider_updates_the_readout_and_the_config(self, window):
        window.brightness_slider.setValue(73)

        assert window.brightness_value.text() == "73%"
        assert window.config.settings.brightness == 73
        assert window.modified


class TestLockSwitch:
    """The switch stands in for the old Lock Monitor checkbox."""

    def test_it_starts_on(self, window):
        assert window.lock_monitor_toggle.isChecked()

    def test_turning_it_off_reaches_the_config(self, window):
        window.lock_monitor_toggle.setChecked(False)

        assert window.config.settings.lock_monitor is False
        assert window.modified


class TestToggleSwitch:
    """The switch itself behaves like the checkbox it replaces."""

    def test_a_click_toggles_it(self, switch, qtbot):
        with qtbot.waitSignal(switch.toggled) as blocked:
            switch.click()

        assert blocked.args == [True]
        assert switch.isChecked()

    def test_the_knob_settles_at_the_on_end_after_a_click(self, switch, qtbot):
        switch.click()

        qtbot.waitUntil(lambda: switch.knob_position == 1.0)

    def test_the_knob_follows_a_state_set_while_signals_are_blocked(self, switch, qtbot):
        """load_config sets the state with signals blocked; the knob must still move."""
        switch.blockSignals(True)
        switch.setChecked(True)
        switch.blockSignals(False)

        qtbot.waitUntil(lambda: switch.knob_position == 1.0)

    def test_it_shows_its_label(self, switch):
        assert switch.text() == "Turn it off"
        assert switch.sizeHint().width() > ToggleSwitch.TRACK_WIDTH


class TestAdvancedSettings:
    """Both gesture timings travel config -> dialog -> config."""

    def open_dialog(self, qtbot, window):
        dialog = AdvancedSettingsDialog(window.config)
        qtbot.addWidget(dialog)
        return dialog

    def test_it_shows_the_configured_timings(self, qtbot, window):
        window.config.settings.double_press_interval = 0.45
        window.config.settings.long_press_duration = 1.2

        dialog = self.open_dialog(qtbot, window)

        assert dialog.get_settings() == {'double_press_interval': 0.45,
                                         'long_press_duration': 1.2}

    def test_the_long_press_spin_box_matches_the_validator_range(self, qtbot, window):
        dialog = self.open_dialog(qtbot, window)

        assert dialog.long_press_spin.minimum() == 0.1
        assert dialog.long_press_spin.maximum() == 5.0

    def test_accepting_writes_both_timings_to_the_config(self, window):
        with patch('StreamDock.ui.main_window.AdvancedSettingsDialog') as dialog_cls:
            dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_cls.return_value.get_settings.return_value = {
                'double_press_interval': 0.5, 'long_press_duration': 0.8}

            window.show_advanced_settings()

        assert window.config.settings.double_press_interval == 0.5
        assert window.config.settings.long_press_duration == 0.8
        assert window.modified

    def test_it_defaults_to_the_shared_constants(self, qtbot, window):
        dialog = self.open_dialog(qtbot, window)

        assert dialog.get_settings() == {
            'double_press_interval': DEFAULT_DOUBLE_PRESS_INTERVAL,
            'long_press_duration': DEFAULT_LONG_PRESS_DURATION}
