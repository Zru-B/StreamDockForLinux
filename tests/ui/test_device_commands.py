"""
The window's side of a device command: controls busy while it is in flight,
and failures nobody asked for reported without a modal dialog.
"""

from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt

from StreamDock.ui.chrome import Toast
from StreamDock.ui.device_service import STATE_CONNECTING, STATE_ERROR
from StreamDock.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot, tmp_path):
    w = MainWindow()
    qtbot.addWidget(w)
    w.config._path = str(tmp_path / "config.yml")
    return w


def test_connect_marks_the_bar_busy_at_once(window):
    """The worker's busy signal arrives late; a second click could queue a second connect."""
    window.on_connect_requested("")

    assert window.device_bar._busy


def test_busy_clears_once_the_command_settles(window):
    window.on_connect_requested("")
    window.on_connection_state_changed(STATE_CONNECTING, "dock")
    assert window.device_bar._busy

    window.on_connection_state_changed(STATE_ERROR, "boom")

    assert not window.device_bar._busy


def test_a_background_failure_opens_no_dialog(window):
    with patch('StreamDock.ui.main_window.plain_message_box') as box:
        window.on_background_error("Could not connect", "busy")

    box.assert_not_called()
    assert "busy" in window.current_status()


def test_a_toast_shows_markup_literally(qtbot):
    from PyQt6.QtWidgets import QWidget
    parent = QWidget()
    qtbot.addWidget(parent)

    toast = Toast(parent)

    assert toast._label.textFormat() == Qt.TextFormat.PlainText
