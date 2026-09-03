"""
GUI application assembly.

Builds the QApplication, puts a DeviceService on its own thread, and connects
it to the main window. Every GUI-to-worker connection is queued by Qt because
the receiver lives on another thread, so nothing here blocks the UI.
"""

import logging
import sys
from typing import Optional

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from StreamDock.application.config_document import ConfigDocument
from StreamDock.application.instance_lock import InstanceLock
from StreamDock.ui.device_service import DeviceService
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.resources import load_app_icon
from StreamDock.ui.settings_store import get_default_config_path
from StreamDock.ui.single_instance import SingleInstanceGuard
from StreamDock.ui.styles import get_stylesheet
from StreamDock.ui.tray import TrayIcon

logger = logging.getLogger(__name__)


class StreamDockGui:
    """Owns the GUI process: window, tray, and the device worker thread."""

    def __init__(self, config_path: Optional[str] = None,
                 device_id: str = "", start_minimized: bool = False):
        """
        Args:
            config_path: Configuration to open. Falls back to the remembered
                default, then to an empty document.
            device_id: Device to connect to, from device_key(). Empty means
                the first discovered.
            start_minimized: Start hidden in the tray.
        """
        self._config_path = config_path or get_default_config_path()
        self._device_id = device_id
        self._start_minimized = start_minimized

        self._qapp: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None
        self._tray: Optional[TrayIcon] = None
        self._thread: Optional[QThread] = None
        self._service: Optional[DeviceService] = None
        self._guard: Optional[SingleInstanceGuard] = None
        self._lock = InstanceLock()

    def run(self) -> int:
        """
        Start the GUI and run until it quits.

        Returns:
            Process exit code
        """
        self._qapp = QApplication(sys.argv)
        self._qapp.setApplicationName("StreamDock")
        self._qapp.setOrganizationName("StreamDock")
        self._qapp.setDesktopFileName("streamdock")
        self._qapp.setWindowIcon(load_app_icon())
        self._qapp.setStyleSheet(get_stylesheet())

        self._guard = SingleInstanceGuard()
        if not self._guard.try_acquire():
            logger.info("Another StreamDock window is open; raising it")
            self._guard.signal_existing()
            return 0

        self._build_window()
        self._build_tray()
        self._build_service()
        self._connect_signals()

        if not self._lock.acquire():
            self._warn_device_in_use()
        else:
            self._window.refresh_devices_requested.emit()
            if self._config_path:
                self._window.connect_requested.emit(self._device_id, self._config_path)

        if self._start_minimized and self._window.tray_available:
            logger.info("Starting minimised to the tray")
        else:
            self._window.show()

        try:
            return self._qapp.exec()
        finally:
            self._shutdown()

    # ── assembly ──────────────────────────────────────────────────────────

    def _build_window(self) -> None:
        self._window = MainWindow()

        if self._config_path:
            try:
                self._window.load_config(self._config_path)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Could not open %s: %s", self._config_path, e)
                QMessageBox.warning(
                    self._window, "Could not open configuration",
                    f"{self._config_path}\n\n{e}")
                self._config_path = None

        if not self._config_path:
            self._window.config = ConfigDocument.new_empty()
            self._window.statusBar().showMessage(
                "No configuration loaded — use File > Open, or create one", 10000)

    def _build_tray(self) -> None:
        # Without a tray, hiding the window on close would make the
        # application unreachable and unquittable.
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("No system tray available; closing the window will quit")
            self._window.tray_available = False
            self._qapp.setQuitOnLastWindowClosed(True)
            return

        self._qapp.setQuitOnLastWindowClosed(False)
        self._window.tray_available = True
        self._tray = TrayIcon()
        self._tray.show()

    def _build_service(self) -> None:
        self._thread = QThread()
        self._thread.setObjectName("device-service")
        self._service = DeviceService()
        self._service.moveToThread(self._thread)
        self._thread.finished.connect(self._service.deleteLater)
        self._thread.start()

    def _connect_signals(self) -> None:
        window, service = self._window, self._service

        # GUI -> worker. Queued automatically: the receiver is on the thread.
        window.refresh_devices_requested.connect(service.refresh_devices)
        window.connect_requested.connect(service.connect_device)
        window.disconnect_requested.connect(service.disconnect_device)
        window.apply_config_requested.connect(service.apply_config)

        # worker -> GUI
        service.devices_discovered.connect(window.on_devices_discovered)
        service.connection_state_changed.connect(window.on_connection_state_changed)
        service.config_applied.connect(window.on_config_applied)
        service.layout_changed.connect(window.on_layout_changed)
        service.error_occurred.connect(window.on_device_error)
        service.busy_changed.connect(window.device_bar.set_busy)

        # device bar -> window
        window.device_bar.refresh_requested.connect(window.refresh_devices_requested)
        window.device_bar.connect_requested.connect(window.on_connect_requested)
        window.device_bar.disconnect_requested.connect(window.disconnect_requested)
        window.device_bar.apply_requested.connect(window.on_apply_requested)

        window.quit_requested.connect(self._qapp.quit)
        self._guard.activate_requested.connect(self._raise_window)

        if self._tray is not None:
            self._tray.show_requested.connect(self._raise_window)
            self._tray.quit_requested.connect(window.request_quit)
            self._tray.apply_requested.connect(window.on_apply_requested)
            self._tray.connect_requested.connect(
                lambda: window.on_connect_requested(
                    window.device_bar.selected_device_id() or ""))
            self._tray.disconnect_requested.connect(window.disconnect_requested)
            service.connection_state_changed.connect(self._tray.set_state)
            window.hidden_to_tray.connect(self._notify_hidden)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def _raise_window(self) -> None:
        self._window.show()
        self._window.setWindowState(
            self._window.windowState() & ~self._window.windowState().WindowMinimized)
        self._window.raise_()
        self._window.activateWindow()

    def _notify_hidden(self) -> None:
        if self._tray is not None:
            self._tray.showMessage(
                "StreamDock", "Still running in the tray.",
                QSystemTrayIcon.MessageIcon.Information, 4000)

    def _warn_device_in_use(self) -> None:
        pid = self._lock.owner_pid()
        detail = f" (pid {pid})" if pid else ""
        QMessageBox.warning(
            self._window, "Device in use",
            f"Another StreamDock process{detail} already controls the device.\n\n"
            "You can edit and save configurations, but connecting is disabled "
            "until that process exits.")
        self._window.device_bar.setEnabled(False)

    def _shutdown(self) -> None:
        """Release the device and stop the worker thread."""
        if self._service is not None:
            # Direct call: the thread's event loop may already be gone, and
            # the device must be released either way.
            try:
                self._service.shutdown()
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error during device shutdown: %s", e)

        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(5000):
                logger.warning("Device service thread did not stop; terminating")
                self._thread.terminate()
                self._thread.wait(1000)

        if self._guard is not None:
            self._guard.close()

        self._lock.release()


def main(config_path: Optional[str] = None, device_id: str = "",
         start_minimized: bool = False) -> int:
    """
    Run the GUI.

    Args:
        config_path: Configuration to open
        device_id: Device to connect to, from device_key()
        start_minimized: Start hidden in the tray

    Returns:
        Process exit code
    """
    return StreamDockGui(config_path, device_id, start_minimized).run()
