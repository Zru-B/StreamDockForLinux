"""
Device selection and connection controls.

On Plasma the row is hosted in the window's toolbar, the way Dolphin keeps
its location bar there, so its buttons dress as tool buttons: flat, with an
outline on hover and the desktop's icons. On GNOME it sits on a card above
the key grid. Not a QToolBar of its own: the stylesheet decides how it looks
in either home.
"""

import logging
from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
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
from StreamDock.ui.theme import Flavor, current_theme, theme_manager, themed_icon

logger = logging.getLogger(__name__)

# Every text button in the row shares a width, so Connect turning into
# Disconnect does not shove Apply sideways. This is the floor; the label
# and its icon can ask for more.
BUTTON_WIDTH = 96

# U+21BB renders in the default UI fonts; U+27F3 falls back to a tofu box.
REFRESH_GLYPH = "↻"

CONNECT_TEXT = "Connect"
DISCONNECT_TEXT = "Disconnect"
APPLY_TEXT = "Apply"

STATE_TEXT = {
    STATE_DISCONNECTED: "Disconnected",
    STATE_CONNECTING: "Connecting...",
    STATE_CONNECTED: "Connected",
    STATE_ERROR: "Error",
}

# The desktop icon for each button, tried in order.
ICONS: Dict[str, Tuple[str, ...]] = {
    'refresh': ('view-refresh', 'view-refresh-symbolic'),
    'connect': ('network-connect', 'network-wired-symbolic'),
    'disconnect': ('network-disconnect', 'network-offline-symbolic'),
    'apply': ('dialog-ok-apply', 'object-select-symbolic'),
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
        self._sized: List[QWidget] = []
        self._text_buttons: List[QPushButton] = []
        # Apply stays disabled while the device already matches the open
        # configuration; there is nothing to send.
        self._needs_apply = False
        self._setup_ui()
        self.set_state(STATE_DISCONNECTED)
        theme_manager().changed.connect(self._apply_metrics)

    def _setup_ui(self) -> None:
        self.setObjectName("deviceBar")
        # A plain QWidget ignores a stylesheet background without this.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # In a toolbar the row takes whatever width is left, so its stretch
        # pushes Connect and Apply to the far end.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._layout = QHBoxLayout(self)

        self.device_combo = QComboBox()
        self.device_combo.setObjectName("deviceCombo")
        self._sized.append(self.device_combo)
        self.device_combo.setMinimumWidth(200)
        self.device_combo.setMaximumWidth(280)
        self.device_combo.setIconSize(QSize(16, 16))
        # Long device names elide rather than stretching the row.
        self.device_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setToolTip("Stream Dock devices currently attached")
        self._layout.addWidget(self.device_combo)

        self.refresh_button = self._make_button("", "Look for attached devices again")
        self.refresh_button.clicked.connect(self.refresh_requested)
        self._layout.addWidget(self.refresh_button)

        self._layout.addSpacing(4)

        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("connectionDot")
        self._layout.addWidget(self.status_dot)

        self.status_label = QLabel()
        self.status_label.setObjectName("connectionStatus")
        self.status_label.setMinimumWidth(96)
        self._layout.addWidget(self.status_label)

        self._layout.addStretch()

        self.connect_button = self._make_button(CONNECT_TEXT, "Open or release the device")
        self.connect_button.clicked.connect(self._on_connect_clicked)
        self._layout.addWidget(self.connect_button)

        self.apply_button = self._make_button(APPLY_TEXT, primary=True)
        self.apply_button.clicked.connect(self.apply_requested)
        self._layout.addWidget(self.apply_button)

        self._apply_metrics()

    def _make_button(self, text: str, tooltip: str = "",
                     primary: bool = False) -> QPushButton:
        """
        Build one control-bar button.

        All of them share a height and a minimum width so the row reads as a
        single strip rather than a jumble of sizes.

        Args:
            text: Button label, '' for an icon-only button
            tooltip: Hover text
            primary: The action that leads - Apply

        Returns:
            The button
        """
        button = QPushButton(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sized.append(button)
        if text:
            self._text_buttons.append(button)
        button.setProperty("barButton", "primary" if primary else "normal")
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _apply_metrics(self) -> None:
        """Put every control in the row on the current design's geometry."""
        theme = current_theme()
        metrics = theme.metrics
        breeze = theme.flavor is Flavor.KDE

        # Inside a toolbar the strip is already padded; on a card it is not.
        if breeze:
            self._layout.setContentsMargins(2, 0, 2, 0)
            height = metrics.control_height - 4
        else:
            self._layout.setContentsMargins(metrics.card_padding, metrics.spacing_tight,
                                            metrics.card_padding, metrics.spacing_tight)
            height = metrics.control_height
        self._layout.setSpacing(metrics.spacing)

        for widget in self._sized:
            widget.setFixedHeight(height)

        self._decorate(breeze, metrics.icon_size_small)

        # Fixed, not minimum: Connect/Disconnect must not resize as its label
        # changes, or the row jumps every time you connect.
        width = self._text_button_width(breeze, metrics.icon_size_small)
        for button in self._text_buttons:
            button.setFixedWidth(width)
        # The refresh button carries a single glyph, so it stays square.
        self.refresh_button.setFixedWidth(height)

    def _decorate(self, breeze: bool, icon_size: int) -> None:
        """
        Give the buttons the desktop's icons, or a glyph where there is none.

        Args:
            breeze: Whether the Plasma design is on, which puts icons on
                text buttons as well
            icon_size: Icon size in pixels
        """
        size = QSize(icon_size, icon_size)

        refresh = themed_icon(*ICONS['refresh'])
        self.refresh_button.setIcon(refresh)
        self.refresh_button.setIconSize(size)
        self.refresh_button.setText("" if not refresh.isNull() else REFRESH_GLYPH)

        for button, key in ((self.apply_button, 'apply'),
                            (self.connect_button, 'disconnect' if self._connected else 'connect')):
            button.setIcon(themed_icon(*ICONS[key]) if breeze else QIcon())
            button.setIconSize(size)

    def _text_button_width(self, breeze: bool, icon_size: int) -> int:
        """
        The width the widest label needs, icon included.

        Args:
            breeze: Whether text buttons carry an icon
            icon_size: Icon size in pixels

        Returns:
            A width in pixels, never under BUTTON_WIDTH
        """
        metrics = self.connect_button.fontMetrics()
        text = max(metrics.horizontalAdvance(label)
                   for label in (CONNECT_TEXT, DISCONNECT_TEXT, APPLY_TEXT))
        icon = icon_size + 6 if breeze and not self.connect_button.icon().isNull() else 0
        return max(BUTTON_WIDTH, text + icon + 24)

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

        self.connect_button.setText(DISCONNECT_TEXT if self._connected else CONNECT_TEXT)
        if not self.connect_button.icon().isNull():
            self.connect_button.setIcon(
                themed_icon(*ICONS['disconnect' if self._connected else 'connect']))
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
