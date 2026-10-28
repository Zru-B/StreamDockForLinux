"""
The Device Settings panel: the brightness slider and the lock switch, plus the
Advanced Settings dialog with its gesture timings.
"""

import logging
import os
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox

from StreamDock.application.config_document import (
    DEFAULT_DOUBLE_PRESS_INTERVAL,
    DEFAULT_LONG_PRESS_DURATION,
    MIN_BRIGHTNESS,
)
from StreamDock.logging_control import set_debug
from StreamDock.ui.dialogs import AdvancedSettingsDialog
from StreamDock.ui.settings_store import get_debug_logging, set_debug_logging
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

    def test_moving_the_slider_updates_the_readout_and_the_config(self, window, qtbot):
        window.brightness_slider.setValue(73)

        assert window.brightness_value.text() == "73%"
        qtbot.waitUntil(lambda: window.config.settings.brightness == 73)
        assert window.modified

    def test_each_tick_is_not_an_edit_of_its_own(self, window):
        """Every valueChanged used to dirty the document and rebuild the sidebar."""
        window.brightness_slider.setValue(60)
        window.brightness_slider.setValue(61)

        assert window.brightness_value.text() == "61%"
        assert not window.modified

    def test_releasing_the_slider_commits_at_once(self, window):
        window.brightness_slider.setValue(64)

        window.brightness_slider.sliderReleased.emit()

        assert window.config.settings.brightness == 64
        assert window.modified


class TestLockSwitch:
    """The switch stands in for the old Lock Monitor checkbox."""

    def test_it_starts_on(self, window):
        assert window.lock_monitor_toggle.isChecked()

    def test_turning_it_off_reaches_the_config(self, window):
        window.lock_monitor_toggle.setChecked(False)

        assert window.config.settings.lock_monitor is False
        assert window.modified

    def test_toggling_it_leaves_a_fractional_brightness_alone(self, window, tmp_path):
        """The slider holds ints; toggling lock used to write 42 over the file's 42.5."""
        path = tmp_path / "config.yml"
        path.write_text("streamdock:\n  settings:\n    brightness: 42.5\n"
                        "  keys: {}\n  layouts: {}\n")
        window.load_config(str(path))

        window.lock_monitor_toggle.setChecked(False)

        assert window.config.settings.brightness == 42.5


class TestNewConfiguration:
    """File > New shows the new document's settings, not the old file's."""

    def test_the_controls_follow_the_new_document(self, window, tmp_path):
        path = tmp_path / "config.yml"
        path.write_text("streamdock:\n  settings:\n    brightness: 80\n    lock_monitor: false\n"
                        "  keys: {}\n  layouts: {}\n")
        window.load_config(str(path))

        with patch("StreamDock.ui.main_window.QMessageBox.question",
                   return_value=QMessageBox.StandardButton.Yes):
            window.new_config()

        assert window.brightness_slider.value() == window.config.settings.brightness
        assert window.lock_monitor_toggle.isChecked() is True
        assert window.device_bar._needs_apply


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

    def test_accepting_unchanged_timings_is_not_an_edit(self, window):
        settings = window.config.settings
        with patch('StreamDock.ui.main_window.AdvancedSettingsDialog') as dialog_cls:
            dialog_cls.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_cls.return_value.get_settings.return_value = {
                'double_press_interval': settings.double_press_interval,
                'long_press_duration': settings.long_press_duration}

            window.show_advanced_settings()

        assert not window.modified

    def test_a_three_decimal_timing_survives_the_dialog(self, qtbot, window):
        window.config.settings.double_press_interval = 0.125

        dialog = self.open_dialog(qtbot, window)

        assert dialog.get_settings()['double_press_interval'] == 0.125

    def test_it_defaults_to_the_shared_constants(self, qtbot, window):
        dialog = self.open_dialog(qtbot, window)

        assert dialog.get_settings() == {
            'double_press_interval': DEFAULT_DOUBLE_PRESS_INTERVAL,
            'long_press_duration': DEFAULT_LONG_PRESS_DURATION}


class TestDebugLoggingSwitch:
    """The checkbox flips every logger at once, and the choice is remembered."""

    @pytest.fixture(autouse=True)
    def restore_logging(self):
        root = logging.getLogger()
        level = root.level
        yield
        set_debug(False)
        root.setLevel(level)
        set_debug_logging(False)

    def test_toggling_it_changes_every_logger(self, qtbot, window):
        stubborn = logging.getLogger('streamdock.test.stubborn')
        stubborn.setLevel(logging.WARNING)
        dialog = AdvancedSettingsDialog(window.config)
        qtbot.addWidget(dialog)

        dialog.debug_check.setChecked(True)
        assert stubborn.isEnabledFor(logging.DEBUG)
        assert logging.getLogger('anything.else').isEnabledFor(logging.DEBUG)
        assert not logging.getLogger('PIL.PngImagePlugin').isEnabledFor(logging.DEBUG)

        dialog.debug_check.setChecked(False)
        assert not stubborn.isEnabledFor(logging.DEBUG)

    def test_the_choice_is_remembered(self, qtbot, window):
        dialog = AdvancedSettingsDialog(window.config)
        qtbot.addWidget(dialog)

        dialog.debug_check.setChecked(True)

        assert get_debug_logging()
        assert os.environ['STREAMDOCK_DEBUG'] == '1'

    def test_it_starts_checked_when_debug_is_already_on(self, qtbot, window):
        set_debug(True)
        dialog = AdvancedSettingsDialog(window.config)
        qtbot.addWidget(dialog)

        assert dialog.debug_check.isChecked()
