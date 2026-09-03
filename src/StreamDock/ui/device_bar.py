"""
Device selection and connection controls.

Sits above the key grid in the main window. Not a QToolBar: the stylesheet
has no QToolBar rules, so one would render unstyled against the dark theme.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from StreamDock.application.device_discovery import device_key, device_label
from StreamDock.infrastructure.hardware_interface import DeviceInfo
from StreamDock.ui.device_service import (
    STATE_CONNECTED,
    STATE_CONNECTING,
    STATE_DISCONNECTED,
    STATE_ERROR,
)
from StreamDock.ui.styles import get_colors

logger = logging.getLogger(__name__)

COLORS = get_colors()

STATE_TEXT = {
    STATE_DISCONNECTED: "Disconnected",
    STATE_CONNECTING: "Connecting...",
    STATE_CONNECTED: "Connected",
    STATE_ERROR: "Error",
}


class DeviceBar(QWidget):
    """Device picker, connection status, and the Apply button."""

    refresh_requested = pyqtSignal()
    connect_requested = pyqtSignal(str)      # device_key, '' for the first
    disconnect_requested = pyqtSignal()
    apply_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._busy = False
        self._setup_ui()
        self.set_state(STATE_DISCONNECTED)

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Device:"))

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(240)
        self.device_combo.setToolTip("Stream Dock devices currently attached")
        layout.addWidget(self.device_combo)

        self.refresh_button = QPushButton("⟳")
        self.refresh_button.setFixedWidth(36)
        self.refresh_button.setToolTip("Look for attached devices again")
        self.refresh_button.clicked.connect(self.refresh_requested)
        layout.addWidget(self.refresh_button)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("connectionDot")
        layout.addWidget(self.status_dot)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_button)

        self.apply_button = QPushButton("Apply to Device")
        self.apply_button.setToolTip("Send the current configuration to the device")
        self.apply_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['primary']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {COLORS['primary_hover']}; }}
            QPushButton:disabled {{
                background-color: {COLORS['bg_tertiary']};
                color: {COLORS['text_secondary']};
            }}
        """)
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.apply_button)

    # ── device list ───────────────────────────────────────────────────────

    def set_devices(self, devices: List[DeviceInfo]) -> None:
        """
        Repopulate the picker.

        Keeps the current selection when that device is still attached, so a
        refresh does not silently switch which device Connect would open.

        Args:
            devices: Discovered devices
        """
        previous = self.selected_device_id()

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(device_label(device), device_key(device))

        if devices:
            index = self.device_combo.findData(previous) if previous else -1
            self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self.device_combo.blockSignals(False)

        self.device_combo.setEnabled(bool(devices))
        if not devices:
            self.device_combo.addItem("No device found")
        self._update_buttons()

    def selected_device_id(self) -> Optional[str]:
        """The device_key of the selected entry, or None."""
        return self.device_combo.currentData()

    # ── state ─────────────────────────────────────────────────────────────

    def set_state(self, state: str, detail: str = "") -> None:
        """
        Reflect the connection state.

        Args:
            state: One of the DeviceService STATE_* values
            detail: Device label or error text
        """
        self._connected = state == STATE_CONNECTED

        self.status_dot.setProperty("state", state)
        # Qt does not restyle on a property change by itself.
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

        text = STATE_TEXT.get(state, state)
        self.status_label.setText(f"{text} — {detail}" if detail else text)
        self.status_label.setToolTip(detail)

        self.connect_button.setText("Disconnect" if self._connected else "Connect")
        self._update_buttons()

    def set_busy(self, busy: bool) -> None:
        """Disable the controls while a device operation is in flight."""
        self._busy = busy
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_device = self.device_combo.currentData() is not None
        self.connect_button.setEnabled(not self._busy and (self._connected or has_device))
        self.apply_button.setEnabled(not self._busy and self._connected)
        self.refresh_button.setEnabled(not self._busy)
        self.device_combo.setEnabled(not self._busy and not self._connected and has_device)

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit(self.selected_device_id() or "")
