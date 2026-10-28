"""
System tray presence.

Closing the window hides the application here rather than quitting, so the
device keeps switching layouts while the editor is out of the way.
"""

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from StreamDock.ui.device_service import STATE_CONNECTED, STATE_DISCONNECTED
from StreamDock.ui.resources import load_app_icon
from StreamDock.ui.theme import themed_icon

logger = logging.getLogger(__name__)


class TrayIcon(QSystemTrayIcon):
    """Tray icon and its menu."""

    show_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    connect_requested = pyqtSignal()
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(load_app_icon(), parent)
        self.setToolTip("StreamDock")
        # Another process holds the device: nothing to connect or disconnect.
        self._locked = False
        self._connected = False
        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        # Kept: setContextMenu does not take ownership, so a local menu is
        # collected and the tray loses its menu.
        self._menu = menu = QMenu()

        self.show_action = QAction(load_app_icon(), "Show StreamDock", self)
        self.show_action.triggered.connect(self.show_requested)
        menu.addAction(self.show_action)

        menu.addSeparator()

        self.connect_action = QAction(themed_icon('network-connect'), "Connect", self)
        self.connect_action.triggered.connect(self.connect_requested)
        menu.addAction(self.connect_action)

        self.disconnect_action = QAction(themed_icon('network-disconnect'), "Disconnect", self)
        self.disconnect_action.triggered.connect(self.disconnect_requested)
        menu.addAction(self.disconnect_action)

        menu.addSeparator()

        self.quit_action = QAction(themed_icon('application-exit'), "Quit", self)
        self.quit_action.triggered.connect(self.quit_requested)
        menu.addAction(self.quit_action)

        self.setContextMenu(menu)
        self.set_state(STATE_DISCONNECTED)

    def set_state(self, state: str, detail: str = "") -> None:
        """
        Reflect the connection state in the tooltip and menu.

        Args:
            state: One of the DeviceService STATE_* values
            detail: Device label or error text
        """
        self._connected = state == STATE_CONNECTED
        self._update_actions()
        self.setToolTip(f"StreamDock — {detail}" if detail else f"StreamDock — {state}")

    def set_locked(self, locked: bool) -> None:
        """Hide Connect and Disconnect while another process controls the device."""
        self._locked = locked
        self._update_actions()

    def _update_actions(self) -> None:
        self.connect_action.setVisible(not self._locked and not self._connected)
        self.disconnect_action.setVisible(not self._locked and self._connected)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_requested.emit()
