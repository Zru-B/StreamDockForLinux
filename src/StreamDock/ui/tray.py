"""
System tray presence.

Closing the window hides the application here rather than quitting, so the
device keeps switching layouts while the editor is out of the way.
"""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from StreamDock.ui.device_service import STATE_CONNECTED
from StreamDock.ui.resources import load_app_icon

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """Tray icon and its menu."""

    show_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    apply_requested = pyqtSignal()
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(load_app_icon(), parent)
        self.setToolTip("StreamDock")
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        menu = QMenu()

        self.show_action = QAction("Show StreamDock", self)
        self.show_action.triggered.connect(self.show_requested)
        menu.addAction(self.show_action)

        menu.addSeparator()

        self.connect_action = QAction("Connect", self)
        self.connect_action.triggered.connect(self.connect_requested)
        menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Disconnect", self)
        self.disconnect_action.triggered.connect(self.disconnect_requested)
        menu.addAction(self.disconnect_action)

        self.apply_action = QAction("Apply Current Config", self)
        self.apply_action.triggered.connect(self.apply_requested)
        menu.addAction(self.apply_action)

        menu.addSeparator()

        self.quit_action = QAction("Quit", self)
        self.quit_action.triggered.connect(self.quit_requested)
        menu.addAction(self.quit_action)

        self.setContextMenu(menu)

    def set_state(self, state: str, detail: str = "") -> None:
        """
        Reflect the connection state in the tooltip and menu.

        Args:
            state: One of the DeviceService STATE_* values
            detail: Device label or error text
        """
        connected = state == STATE_CONNECTED
        self.connect_action.setVisible(not connected)
        self.disconnect_action.setVisible(connected)
        self.apply_action.setEnabled(connected)
        self.setToolTip(f"StreamDock — {detail}" if detail else f"StreamDock — {state}")

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()
