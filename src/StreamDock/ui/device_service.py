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

# Consecutive failed connects after which hotplug stops retrying on its own;
# the next Connect the user presses arms it again.
MAX_AUTO_RECONNECT_FAILURES = 2


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
    # A failure nobody asked for - a hotplug reconnect - worth a status line,
    # not a modal dialog popping up over whatever the user is doing.
    background_error = pyqtSignal(str, str)        # title, message
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
        # The dock last connected to; hotplug only ever reconnects to it.
        self._connected_device_id: str = ""
        # An explicit Disconnect must not be undone by the next udev event.
        self._user_disconnected: bool = False
        self._failed_connects: int = 0
        self._discovery_failed: bool = False
        self._shutting_down: bool = False

        self._devices_changed.connect(self._on_devices_changed)

    # ── queries ───────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        """True while a device runtime is running."""
        return self._app is not None

    def current_device(self) -> Optional[DeviceInfo]:
        """The connected device, or None."""
        return self._app.get_device_info() if self._app else None

    def recent_windows(self) -> list:
        """
        Recently focused windows, newest first; empty while no device runs.

        Called from the GUI thread: it only copies a list the monitor guards.
        """
        app = self._app
        monitor = app.get_event_monitor() if app is not None else None
        return monitor.recent_windows if monitor is not None else []

    # ── slots ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def refresh_devices(self) -> None:
        """Re-enumerate and publish the device list."""
        self._discovery_failed = False
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
            self._discovery_failed = True
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
        # Pressing Connect is the user taking charge again, failures and all.
        self._failed_connects = 0
        self._connect(device_id, config_path, background=False)

    def _connect(self, device_id: str, config_path: str, background: bool) -> None:
        if self._shutting_down:
            return
        report = self.background_error.emit if background else self.error_occurred.emit

        if self._app is not None:
            self.disconnect_device()

        if not config_path:
            report(
                "No configuration",
                "Load or create a configuration before connecting.")
            self.connection_state_changed.emit(STATE_DISCONNECTED, "No configuration")
            return

        self._config_path = config_path
        self._requested_device_id = device_id
        self._user_disconnected = False

        device_info = self._resolve(device_id, report)
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
            self._failed_connects = 0
            self._connected_device_id = device_key(device_info)
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
            self._failed_connects += 1
            report("Could not connect", str(e))
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
            # The window already hands over a private copy.
            applied = self._app.reload(config_path or None, raw_document=raw_document)
            if applied:
                # Hotplug reconnects with this path; left at the file first
                # connected, a replug would load that one and report it applied.
                if config_path:
                    self._config_path = config_path
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

        # Announced first: one udev batch can carry a new dock and the loss of
        # the connected one, and the detach below returns early.
        for key, device in current.items():
            if key not in previous:
                logger.info("Device attached: %s", device_label(device))
                self.device_attached.emit(device_label(device))

        connected = self.current_device()
        if connected is not None and device_key(connected) not in current:
            logger.info("Connected device was unplugged: %s", device_label(connected))
            self.device_detached.emit(device_label(connected))
            # Not a user disconnect: reconnect when it comes back.
            self._release(detail=f"{device_label(connected)} was unplugged")
            self._reconnect_if_possible(current)
            return

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
        if self._shutting_down or not current:
            return
        if self._failed_connects >= MAX_AUTO_RECONNECT_FAILURES:
            logger.info("Not reconnecting after %d failed attempts", self._failed_connects)
            return

        # The dock the user picked, or failing that the one that was in use,
        # is the only one worth reconnecting to; silently moving to a
        # different dock would be surprising. Never connected, any will do.
        target = self._requested_device_id or self._connected_device_id
        if target and target not in current:
            return

        logger.info("Device available again; reconnecting")
        self._connect(target, self._config_path, background=True)

    @pyqtSlot()
    def shutdown(self) -> None:
        """Release everything ahead of the worker thread stopping."""
        self._shutting_down = True
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self.disconnect_device()

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve(self, device_id: str, report) -> Optional[DeviceInfo]:
        """
        Find the device to open, re-enumerating if the cache is stale.

        An explicit device that is not attached is an error, never a reason
        to open whichever dock happens to be first.

        Args:
            device_id: Key from device_key(), or '' for the first discovered
            report: Where a failure goes, as (title, message)

        Returns:
            The device, or None when nothing matches
        """
        if not self._devices:
            self.refresh_devices()

        if not self._devices:
            # A failed enumeration has already said so.
            if not self._discovery_failed:
                report("No device found",
                       "No Stream Dock is attached. Plug one in and press refresh.")
            return None

        if not device_id:
            return self._devices[0]

        match = self._find(device_id)
        if match is None:
            self.refresh_devices()
            match = self._find(device_id)
        if match is None and not self._discovery_failed:
            report("Device not found", f"{device_id} is not attached.")
        return match

    def _find(self, device_id: str) -> Optional[DeviceInfo]:
        return next((device for device in self._devices
                     if device_key(device) == device_id), None)
