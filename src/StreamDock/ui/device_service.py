"""
Device control from the GUI, off the GUI thread.

Applying a layout is fifteen multi-packet JPEG transfers over HID and takes
on the order of a second. Doing that on the Qt main thread would freeze the
window on every connect, apply and layout switch, so an Application lives on
a worker thread and the GUI talks to it through queued signals.

Threading rules
---------------

===========================  ==========  ============  ============
thread                       Qt widgets  emit signals  touch device
===========================  ==========  ============  ============
GUI (main)                   yes         yes           no
device-service               no          yes           yes
HID reader / key workers     no          via hooks     yes
window-poll / LockMonitor    no          via hooks     yes
===========================  ==========  ============  ============

Application spawns those last threads itself and always will, so the worker
is the command thread, not the only device thread. Emitting a signal from a
non-Qt thread is safe and arrives queued; calling a widget method from one is
not. That is why Application takes a plain callable for layout changes rather
than importing Qt.
"""

import copy
import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from StreamDock.application.application import Application
from StreamDock.application.configuration_manager import ConfigurationManager
from StreamDock.application.device_discovery import (
    device_key,
    device_label,
    discover_devices,
)
from StreamDock.application.device_watcher import DeviceWatcher
from StreamDock.infrastructure import USBHardware
from StreamDock.infrastructure.hardware_interface import DeviceInfo

logger = logging.getLogger(__name__)

# connection_state_changed values
STATE_DISCONNECTED = "disconnected"
STATE_CONNECTING = "connecting"
STATE_CONNECTED = "connected"
STATE_ERROR = "error"


class DeviceService(QObject):
    """
    Owns the device runtime on a worker thread.

    Every slot runs on the worker; every signal is delivered back to whichever
    thread connected to it. Nothing here may touch a widget.
    """

    devices_discovered = pyqtSignal(list)          # List[DeviceInfo]
    connection_state_changed = pyqtSignal(str, str)  # state, detail
    config_applied = pyqtSignal(str)               # config path, '' when unsaved
    layout_changed = pyqtSignal(str)               # layout name
    error_occurred = pyqtSignal(str, str)          # title, message
    busy_changed = pyqtSignal(bool)
    device_attached = pyqtSignal(str)              # label of a device just plugged in
    device_detached = pyqtSignal(str)              # label of the device that vanished

    # Emitted from the watcher thread so the reaction runs as a queued slot on
    # the worker, never on whichever thread udev happened to notify.
    _devices_changed = pyqtSignal(list)

    def __init__(self, application_factory=Application,
                 hardware_factory=USBHardware, parent: Optional[QObject] = None):
        """
        Args:
            application_factory: Builds the runtime. Injected so tests run
                without hardware and without patching import paths.
            hardware_factory: Builds the hardware abstraction used for
                enumeration when nothing is connected yet.
            parent: Qt parent
        """
        super().__init__(parent)
        self._application_factory = application_factory
        self._hardware_factory = hardware_factory
        self._app: Optional[Application] = None
        self._devices: List[DeviceInfo] = []
        self._watcher: Optional[DeviceWatcher] = None
        # Remembered so hotplug can reconnect the same device with the same
        # configuration without asking the window again.
        self._config_path: str = ""
        self._requested_device_id: str = ""
        # An explicit Disconnect must not be undone by the next udev event.
        self._user_disconnected: bool = False

        self._devices_changed.connect(self._on_devices_changed)

    # ── queries ───────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        """True while a device runtime is running."""
        return self._app is not None

    def current_device(self) -> Optional[DeviceInfo]:
        """The connected device, or None."""
        return self._app.get_device_info() if self._app else None

    # ── slots ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def refresh_devices(self) -> None:
        """Re-enumerate and publish the device list."""
        try:
            if self._watcher is not None:
                self._watcher.refresh()
                self._devices = self._watcher.devices()
            else:
                hardware = (self._app.get_hardware() if self._app
                            else self._hardware_factory())
                self._devices = discover_devices(hardware)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error enumerating devices: %s", e)
            self._devices = []
            self.error_occurred.emit("Device discovery failed", str(e))

        self.devices_discovered.emit(list(self._devices))

    @pyqtSlot(str, str)
    def connect_device(self, device_id: str, config_path: str) -> None:
        """
        Open a device and start the runtime against a configuration.

        Args:
            device_id: Key from device_key(), or '' for the first discovered
            config_path: Configuration to apply
        """
        if self._app is not None:
            self.disconnect_device()

        if not config_path:
            self.error_occurred.emit(
                "No configuration",
                "Load or create a configuration before connecting.")
            self.connection_state_changed.emit(STATE_DISCONNECTED, "No configuration")
            return

        self._config_path = config_path
        self._requested_device_id = device_id
        self._user_disconnected = False

        device_info = self._resolve(device_id)
        if device_info is None:
            self.connection_state_changed.emit(STATE_DISCONNECTED, "No device found")
            return

        self.busy_changed.emit(True)
        self.connection_state_changed.emit(STATE_CONNECTING, device_label(device_info))

        app = None
        try:
            app = self._application_factory(
                config_path,
                device_info=device_info,
                on_layout_changed=self.layout_changed.emit,
            )
            if not app.start():
                raise RuntimeError("The device runtime failed to start")

            # start() succeeds even when the device could not be opened, which
            # would otherwise show as "Connected" with dead hardware.
            if app.get_device() is None:
                raise RuntimeError(
                    "The device could not be opened. Another process may be "
                    "using it, or you may lack permission to access it.")

            self._app = app
            self.connection_state_changed.emit(STATE_CONNECTED, device_label(device_info))
            self.config_applied.emit(config_path)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error connecting to device: %s", e)
            if app is not None:
                # initialize() opens the HID handle before start() can fail, so
                # force the teardown or the handle leaks and the next attempt
                # finds the device busy.
                try:
                    app.stop(force=True)
                except Exception:  # pylint: disable=broad-exception-caught
                    logger.exception("Error releasing the device after a failed connect")
            self._app = None
            self.error_occurred.emit("Could not connect", str(e))
            self.connection_state_changed.emit(STATE_ERROR, str(e))

        finally:
            self.busy_changed.emit(False)

    @pyqtSlot()
    def disconnect_device(self) -> None:
        """Stop the runtime and release the device, at the user's request."""
        self._user_disconnected = True
        self._release(detail="")

    def _release(self, detail: str = "") -> None:
        """
        Stop the runtime and release the device.

        Args:
            detail: Text for the disconnected state, e.g. why it happened
        """
        if self._app is None:
            self.connection_state_changed.emit(STATE_DISCONNECTED, detail)
            return

        self.busy_changed.emit(True)
        try:
            self._app.stop(force=True)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error disconnecting: %s", e)
            self.error_occurred.emit("Error while disconnecting", str(e))
        finally:
            self._app = None
            self.busy_changed.emit(False)
            self.connection_state_changed.emit(STATE_DISCONNECTED, detail)

    @pyqtSlot(dict, str)
    def apply_config(self, raw_document: Dict[str, Any], config_path: str) -> None:
        """
        Push a configuration to the connected device.

        Args:
            raw_document: The 'streamdock' subtree, possibly unsaved
            config_path: Path it belongs to; relative icon paths resolve
                against its directory
        """
        if self._app is None:
            self.error_occurred.emit(
                "Not connected", "Connect to a device before applying a configuration.")
            return

        # Validate before touching the hardware: a half-finished config must
        # never reach the device.
        issues = ConfigurationManager.collect_issues(
            raw_document, config_path or self._app.get_config_path())
        if issues:
            self.error_occurred.emit("Configuration is invalid", issues[0])
            return

        self.busy_changed.emit(True)
        try:
            applied = self._app.reload(
                config_path or None, raw_document=copy.deepcopy(raw_document))
            if applied:
                self.config_applied.emit(config_path)
            else:
                self.error_occurred.emit(
                    "Could not apply configuration",
                    "The device kept its previous configuration.")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error applying configuration: %s", e)
            self.error_occurred.emit("Could not apply configuration", str(e))
        finally:
            self.busy_changed.emit(False)

    @pyqtSlot(int)
    def set_brightness(self, percent: int) -> None:
        """
        Change screen brightness on the connected device.

        Args:
            percent: Brightness 0-100
        """
        if self._app is None:
            return

        device = self._app.get_device()
        orchestrator = self._app.get_orchestrator()
        if device is None or orchestrator is None:
            return

        try:
            # Through the orchestrator's lock: a bare device call could
            # interleave its packets with a layout render.
            orchestrator.run_exclusive(lambda: device.set_brightness(percent))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error setting brightness: %s", e)
            self.error_occurred.emit("Could not set brightness", str(e))

    @pyqtSlot()
    def start_watching(self) -> None:
        """Begin reacting to devices being plugged in and unplugged."""
        if self._watcher is not None:
            return

        # Hop to the worker thread via a signal: udev notifies on its own
        # thread, and the reaction opens and closes devices.
        self._watcher = DeviceWatcher(self._devices_changed.emit)
        self._watcher.start()
        self._devices = self._watcher.devices()
        self.devices_discovered.emit(list(self._devices))

    @pyqtSlot(list)
    def _on_devices_changed(self, devices: List[DeviceInfo]) -> None:
        """
        React to the attached device set changing.

        Args:
            devices: The devices now attached
        """
        previous = {device_key(d) for d in self._devices}
        current = {device_key(d): d for d in devices}
        self._devices = list(devices)
        self.devices_discovered.emit(list(devices))

        connected = self.current_device()
        if connected is not None and device_key(connected) not in current:
            logger.info("Connected device was unplugged: %s", device_label(connected))
            self.device_detached.emit(device_label(connected))
            # Not a user disconnect: reconnect when it comes back.
            self._release(detail=f"{device_label(connected)} was unplugged")
            self._reconnect_if_possible(current)
            return

        for key, device in current.items():
            if key not in previous:
                logger.info("Device attached: %s", device_label(device))
                self.device_attached.emit(device_label(device))

        if self._app is None:
            self._reconnect_if_possible(current)

    def _reconnect_if_possible(self, current: dict) -> None:
        """
        Connect to a newly available device when that is what the user wants.

        Args:
            current: device_key -> DeviceInfo for everything attached
        """
        if self._app is not None or self._user_disconnected or not self._config_path:
            return
        if not current:
            return

        # A device the user picked explicitly is the only one worth
        # reconnecting to; silently moving to a different dock would be
        # surprising. With no explicit choice, any device will do.
        if self._requested_device_id:
            if self._requested_device_id not in current:
                return
            target = self._requested_device_id
        else:
            target = ""

        logger.info("Device available again; reconnecting")
        self.connect_device(target, self._config_path)

    @pyqtSlot()
    def shutdown(self) -> None:
        """Release everything ahead of the worker thread stopping."""
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self.disconnect_device()

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve(self, device_id: str) -> Optional[DeviceInfo]:
        """
        Find the device to open, re-enumerating if the cache is stale.

        Args:
            device_id: Key from device_key(), or '' for the first discovered

        Returns:
            The device, or None when nothing matches
        """
        if not self._devices:
            self.refresh_devices()

        if not self._devices:
            self.error_occurred.emit(
                "No device found",
                "No Stream Dock is attached. Plug one in and press refresh.")
            return None

        if not device_id:
            return self._devices[0]

        for device in self._devices:
            if device_key(device) == device_id:
                return device

        self.error_occurred.emit(
            "Device not found",
            f"{device_id} is no longer attached; using the first available device.")
        return self._devices[0]
