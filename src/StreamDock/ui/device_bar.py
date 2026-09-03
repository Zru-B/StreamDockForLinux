"""
Device selection and connection controls.

Sits above the key grid in the main window. Not a QToolBar: the stylesheet
has no QToolBar rules, so one would render unstyled against the dark theme.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
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
from StreamDock.ui.resources import load_app_icon
from StreamDock.ui.styles import get_colors

logger = logging.getLogger(__name__)

COLORS = get_colors()

# One height and one minimum width for every control, so the row lines up.
CONTROL_HEIGHT = 28  # matches the min/max-height in the bar's stylesheet
BUTTON_WIDTH = 92  # fits 'Disconnect'; every text button shares it

# U+21BB renders in the default UI fonts; U+27F3 falls back to a tofu box.
REFRESH_GLYPH = "\u21bb"

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
        # Apply stays disabled while the device already matches the open
        # configuration; there is nothing to send.
        self._needs_apply = False
        self._setup_ui()
        self.set_state(STATE_DISCONNECTED)

    def _setup_ui(self) -> None:
        self.setObjectName("deviceBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setPixmap(load_app_icon().pixmap(QSize(18, 18)))
        layout.addWidget(icon_label)

        self.device_combo = QComboBox()
        self.device_combo.setObjectName("deviceCombo")
        self.device_combo.setFixedHeight(CONTROL_HEIGHT)
        self.device_combo.setMinimumWidth(200)
        self.device_combo.setMaximumWidth(280)
        self.device_combo.setIconSize(QSize(14, 14))
        # Long device names elide rather than stretching the row.
        self.device_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setToolTip("Stream Dock devices currently attached")
        layout.addWidget(self.device_combo)

        self.refresh_button = self._make_button(REFRESH_GLYPH, "Look for attached devices again")
        self.refresh_button.setFixedWidth(CONTROL_HEIGHT)  # square
        self.refresh_button.clicked.connect(self.refresh_requested)
        layout.addWidget(self.refresh_button)

        layout.addSpacing(4)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("connectionDot")
        layout.addWidget(self.status_dot)

        self.status_label = QLabel()
        self.status_label.setObjectName("connectionStatus")
        self.status_label.setMinimumWidth(96)
        layout.addWidget(self.status_label)

        layout.addStretch()

        self.connect_button = self._make_button("Connect", "Open or release the device")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        layout.addWidget(self.connect_button)

        self.apply_button = self._make_button("Apply", primary=True)
        self.apply_button.clicked.connect(self.apply_requested)
        layout.addWidget(self.apply_button)

    def _make_button(self, text: str, tooltip: str = "",
                     primary: bool = False) -> QPushButton:
        """
        Build one control-bar button.

        All of them share a height and a minimum width so the row reads as a
        single strip rather than a jumble of sizes.

        Args:
            text: Button label
            tooltip: Hover text
            primary: Use the accent colour

        Returns:
            The button
        """
        button = QPushButton(text)
        button.setFixedHeight(CONTROL_HEIGHT)
        # Fixed, not minimum: Connect/Disconnect must not resize as its label
        # changes, or the row jumps every time you connect.
        button.setFixedWidth(BUTTON_WIDTH)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("barButton", "primary" if primary else "normal")
        if tooltip:
            button.setToolTip(tooltip)
        return button

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

        icon = load_app_icon()
        names = [device.product or device.manufacturer or "Stream Dock"
                 for device in devices]

        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device, name in zip(devices, names):
            # Only spell out the serial or USB path when the names collide;
            # one device should just read "Stream Dock".
            if names.count(name) > 1:
                detail = device.serial_number or device.path
                text = f"{name} · {detail}" if detail else name
            else:
                text = name
            self.device_combo.addItem(icon, text, device_key(device))
            self.device_combo.setItemData(
                self.device_combo.count() - 1, device_label(device),
                Qt.ItemDataRole.ToolTipRole)

        if devices:
            index = self.device_combo.findData(previous) if previous else -1
            self.device_combo.setCurrentIndex(index if index >= 0 else 0)
        self.device_combo.blockSignals(False)

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

        # The combo already names the device, so the status stays short and
        # the full detail lives in the tooltip.
        text = STATE_TEXT.get(state, state)
        self.status_label.setText(text)
        self.status_label.setToolTip(f"{text} — {detail}" if detail else text)

        self.connect_button.setText("Disconnect" if self._connected else "Connect")
        self._update_buttons()

    def set_needs_apply(self, needs_apply: bool) -> None:
        """
        Enable Apply only when the device is out of date.

        Args:
            needs_apply: True when the open configuration differs from what
                the device is running
        """
        self._needs_apply = needs_apply
        self._update_buttons()

    def set_busy(self, busy: bool) -> None:
        """Disable the controls while a device operation is in flight."""
        self._busy = busy
        self._update_buttons()

    def _update_buttons(self) -> None:
        has_device = self.device_combo.currentData() is not None
        self.connect_button.setEnabled(not self._busy and (self._connected or has_device))
        can_apply = self._connected and self._needs_apply
        self.apply_button.setEnabled(not self._busy and can_apply)
        self.apply_button.setToolTip(
            "Send the current configuration to the device" if can_apply
            else "The device already matches this configuration")
        self.refresh_button.setEnabled(not self._busy)
        self.device_combo.setEnabled(not self._busy and not self._connected and has_device)

    def _on_connect_clicked(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit(self.selected_device_id() or "")
