"""
Another process holding the device: the window edits but must not connect,
and takes the device over once that process goes.
"""

from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QTimer

from StreamDock.ui.app import StreamDockGui
from StreamDock.ui.device_service import STATE_CONNECTED
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.tray import TrayIcon


@pytest.fixture
def window(qtbot):
    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture
def tray():
    icon = TrayIcon()
    yield icon
    icon.deleteLater()


def test_connect_is_refused_while_locked(window, tmp_path):
    window.config._path = str(tmp_path / "config.yml")
    window.device_locked = True
    emitted = []
    window.connect_requested.connect(lambda *a: emitted.append(a))

    window.on_connect_requested("")

    assert emitted == []


def test_the_tray_starts_offering_connect_and_keeps_its_menu(tray):
    """setContextMenu does not own the menu; a local one was garbage collected."""
    assert tray.contextMenu() is tray._menu
    assert tray.connect_action.isVisible()
    assert not tray.disconnect_action.isVisible()


def test_the_tray_offers_neither_while_locked(tray):
    tray.set_locked(True)
    tray.set_state(STATE_CONNECTED)

    assert not tray.connect_action.isVisible()
    assert not tray.disconnect_action.isVisible()


def test_the_lock_is_retried_and_the_device_taken_over(window, tray):
    gui = StreamDockGui()
    gui._window, gui._tray = window, tray
    gui._lock = Mock()
    gui._lock.acquire = Mock(side_effect=[False, True])
    gui._set_device_locked(True)
    gui._lock_timer = QTimer()
    watched = []
    window.watch_devices_requested.connect(lambda: watched.append(True))

    gui._retry_lock()
    assert window.device_locked and not window.device_bar.isEnabled()

    gui._retry_lock()

    assert not window.device_locked
    assert window.device_bar.isEnabled()
    assert tray.connect_action.isVisible()
    assert watched == [True]
