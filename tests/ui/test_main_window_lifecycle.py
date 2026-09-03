"""
Window lifecycle: close-to-tray, quitting, and validation gating.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QMessageBox

from StreamDock.application.config_document import ConfigDocument
from StreamDock.ui.main_window import MainWindow


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


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


class TestCloseToTray:
    """Closing must not stop the device when a tray is available."""

    def test_close_hides_when_a_tray_exists(self, window, qtbot):
        window.tray_available = True
        window.show()

        with qtbot.waitSignal(window.hidden_to_tray):
            window.close()

        assert not window.isVisible()

    def test_close_does_not_prompt_about_unsaved_changes(self, window):
        """Nagging on every minimise would be intolerable."""
        window.tray_available = True
        window.modified = True
        window.ask_about_unsaved_changes = Mock()

        window.close()

        window.ask_about_unsaved_changes.assert_not_called()

    def test_close_really_closes_without_a_tray(self, window):
        window.tray_available = False
        window.show()

        event = QCloseEvent()
        window.closeEvent(event)

        assert event.isAccepted()


class TestQuit:
    """Explicit quit tears everything down."""

    def test_quit_emits_after_closing(self, window, qtbot):
        window.tray_available = True

        with qtbot.waitSignal(window.quit_requested):
            window.request_quit()

    def test_quit_prompts_about_unsaved_changes(self, window):
        window.tray_available = True
        window.modified = True
        window.ask_about_unsaved_changes = Mock(
            return_value=QMessageBox.StandardButton.Discard)

        window.request_quit()

        window.ask_about_unsaved_changes.assert_called_once()

    def test_cancelling_the_prompt_aborts_the_quit(self, window):
        window.tray_available = True
        window.modified = True
        window.show()
        window.ask_about_unsaved_changes = Mock(
            return_value=QMessageBox.StandardButton.Cancel)

        window.request_quit()

        assert window.isVisible()
        assert window._quitting is False


class TestValidationGate:
    """Nothing invalid reaches the device."""

    def test_apply_is_blocked_by_an_invalid_config(self, window, qtbot):
        window.config = ConfigDocument.from_dict({'settings': {'brightness': 500}})
        emitted = []
        window.apply_config_requested.connect(lambda d, p: emitted.append(d))

        with patch.object(MainWindow, 'validate_current_config', return_value=False):
            window.on_apply_requested()

        assert emitted == []

    def test_apply_sends_a_copy_of_the_document(self, window, config_path, qtbot):
        window.load_config(config_path)
        emitted = []
        window.apply_config_requested.connect(lambda d, p: emitted.append((d, p)))

        window.on_apply_requested()

        document, path = emitted[0]
        assert path == config_path
        assert document == window.config.to_dict()['streamdock']
        assert document is not window.config.to_dict()['streamdock']

    def test_valid_config_reports_no_issues(self, window, config_path):
        window.load_config(config_path)

        assert window.validate_current_config() is True

    def test_connect_requires_a_saved_configuration(self, window):
        """The runtime resolves relative icon paths against the config file."""
        window.config = ConfigDocument.new_empty()
        emitted = []
        window.connect_requested.connect(lambda d, p: emitted.append(p))

        with patch('StreamDock.ui.main_window.QMessageBox.warning'):
            window.on_connect_requested("")

        assert emitted == []

    def test_connect_passes_the_config_path(self, window, config_path):
        window.load_config(config_path)
        emitted = []
        window.connect_requested.connect(lambda d, p: emitted.append((d, p)))

        window.on_connect_requested("some-device")

        assert emitted == [("some-device", config_path)]


class TestDeviceFeedback:
    """Worker signals land in the UI."""

    def test_device_list_reaches_the_bar(self, window):
        device = Mock(vendor_id=0x6603, product_id=0x1006, serial_number='',
                      path='/dev/hidraw0', manufacturer='', product='Dock')

        window.on_devices_discovered([device])

        assert window.device_bar.selected_device_id() == '6603:1006@/dev/hidraw0'

    def test_connection_state_reaches_the_bar(self, window):
        window.on_connection_state_changed("connected", "Dock")

        assert window.device_bar.status_dot.property('state') == "connected"

    def test_layout_change_is_reported(self, window):
        window.on_layout_changed("Firefox")

        assert "Firefox" in window.statusBar().currentMessage()


class TestApplyGate:
    """Apply is offered only when the device is actually out of date."""

    def test_a_freshly_loaded_config_needs_applying(self, window, config_path):
        """Nothing has been sent to the device yet."""
        window.load_config(config_path)

        assert window._needs_apply is True

    def test_applying_clears_the_gate(self, window, config_path):
        window.load_config(config_path)

        window.on_config_applied(config_path)

        assert window._needs_apply is False
        assert not window.device_bar.apply_button.isEnabled()

    def test_editing_reopens_the_gate(self, window, config_path):
        window.load_config(config_path)
        window.on_config_applied(config_path)

        window.mark_modified()

        assert window._needs_apply is True

    def test_reloading_the_same_file_does_not_reopen_the_gate(self, window,
                                                              config_path):
        """Re-opening what the device is already running changes nothing."""
        window.load_config(config_path)
        window.on_config_applied(config_path)

        window.load_config(config_path)

        assert window._needs_apply is False

    def test_loading_a_different_file_reopens_the_gate(self, window, config_path,
                                                       tmp_path):
        window.load_config(config_path)
        window.on_config_applied(config_path)

        other = tmp_path / "other.yml"
        other.write_text(CONFIG)
        window.load_config(str(other))

        assert window._needs_apply is True

    def test_unplugging_reopens_the_gate(self, window, config_path):
        window.load_config(config_path)
        window.on_config_applied(config_path)

        window.on_device_detached("StreamDock")
        window.load_config(config_path)

        assert window._needs_apply is True

    def test_saving_does_not_close_the_gate(self, window, config_path):
        """Writing the file does not put it on the device."""
        window.load_config(config_path)
        window.on_config_applied(config_path)
        window.mark_modified()

        window.save_config_to_file(config_path)

        assert window._needs_apply is True

    def test_editing_a_key_marks_the_config_dirty(self, window, config_path):
        """edit_key used to mutate the config without marking it."""
        window.load_config(config_path)
        window.on_config_applied(config_path)
        key_def = window.config.keys['KeyA']

        with patch('StreamDock.ui.main_window.KeyEditorDialog') as dialog_cls:
            dialog = dialog_cls.return_value
            dialog.exec.return_value = dialog.DialogCode.Accepted
            dialog.get_key_definition.return_value = key_def
            window.edit_key('KeyA')

        assert window.modified is True
        assert window._needs_apply is True

    def test_changing_the_default_layout_marks_the_config_dirty(self, window,
                                                                config_path):
        """set_default_layout used to mutate the config without marking it."""
        window.load_config(config_path)
        window.on_config_applied(config_path)

        window.set_default_layout('Main')

        assert window.modified is True
        assert window._needs_apply is True
