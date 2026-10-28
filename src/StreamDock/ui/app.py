"""
GUI application assembly.

Builds the QApplication, puts a DeviceService on its own thread, and connects
it to the main window. Every GUI-to-worker connection is queued by Qt because
the receiver lives on another thread, so nothing here blocks the UI.
"""

import logging
import os
import sys
import traceback
from typing import Optional

from PyQt6.QtCore import QMetaObject, QThread, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QSystemTrayIcon

from StreamDock.application.config_document import ConfigDocument
from StreamDock.application.instance_lock import InstanceLock
from StreamDock.ui.device_service import DeviceService
from StreamDock.ui.main_window import MainWindow
from StreamDock.ui.resources import load_app_icon
from StreamDock.ui.settings_store import (
    get_default_config_path,
    get_design,
    get_scheme,
)
from StreamDock.ui.single_instance import SingleInstanceGuard
from StreamDock.ui.theme import apply_theme, theme_manager
from StreamDock.ui.theme.detection import is_plasma_session
from StreamDock.ui.tray import TrayIcon

logger = logging.getLogger(__name__)

APP_DISPLAY_NAME = "StreamDock"
# How often to try for the device again while another process holds it.
LOCK_RETRY_MS = 5000

# Set to 0 to keep Qt's own file dialogs on Plasma instead of the desktop's.
PORTAL_DIALOGS_ENV = "STREAMDOCK_PORTAL_DIALOGS"
PLATFORM_THEME_ENV = "QT_QPA_PLATFORMTHEME"
PORTAL_THEME = "xdgdesktopportal"


def prefer_desktop_file_dialogs() -> bool:
    """
    Route file dialogs through the desktop portal on Plasma.

    A PyQt wheel carries no KDE platform plugin, so Qt would open its own
    generic file picker in the middle of a Breeze session. The portal theme
    Qt does ship asks the desktop for the dialog instead, which on Plasma is
    the real KDE one - Places sidebar, previews and all - and falls back to
    Qt's when no portal answers. Everything else about the theme still comes
    from the session.

    Must run before the QApplication exists; Qt reads the variable once.

    Returns:
        True when the portal theme was selected
    """
    if os.environ.get(PORTAL_DIALOGS_ENV, "1") in ("0", "false", "no", "off"):
        return False
    if os.environ.get(PLATFORM_THEME_ENV):
        return False
    if not is_plasma_session():
        return False
    os.environ[PLATFORM_THEME_ENV] = PORTAL_THEME
    logger.debug("Using the desktop portal for file dialogs")
    return True


def install_exception_hook(parent_provider=lambda: None) -> None:
    """
    Report an exception escaping a Qt slot instead of dying on it.

    PyQt6 calls sys.excepthook for such an exception and, with the default
    hook, aborts the process - so one bad value in a config file took the
    window and the device runtime down with it. This hook logs the traceback
    and tells the user once per run, then lets the event loop carry on.

    Args:
        parent_provider: Returns the widget to parent the message to, if any
    """
    shown = {'error': False}

    def hook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
        if shown['error'] or QApplication.instance() is None:
            return
        shown['error'] = True
        # Non-modal: a modal box would start a nested event loop inside
        # whatever slot just failed.
        box = QMessageBox(parent_provider())
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("Unexpected error")
        box.setText("Something went wrong. StreamDock kept running, but the last "
                    "action may not have completed.")
        box.setInformativeText(f"{exc_type.__name__}: {exc_value}")
        box.setDetailedText("".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)))
        for label in box.findChildren(QLabel):
            label.setTextFormat(Qt.TextFormat.PlainText)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)
        box.show()

    sys.excepthook = hook


class StreamDockGui:
    """Owns the GUI process: window, tray, and the device worker thread."""

    def __init__(self, config_path: Optional[str] = None,
                 device_id: str = "", start_minimized: bool = False,
                 design: Optional[str] = None):
        """
        Args:
            config_path: Configuration to open. Falls back to the remembered
                default, then to an empty document.
            device_id: Device to connect to, from device_key(). Empty means
                the first discovered.
            start_minimized: Start hidden in the tray.
            design: Force 'kde' or 'gnome' for this run only. None uses the
                remembered preference, which itself defaults to following the
                running desktop.
        """
        self._config_path = config_path or get_default_config_path()
        self._device_id = device_id
        self._start_minimized = start_minimized
        self._design = design

        self._qapp: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None
        self._tray: Optional[TrayIcon] = None
        self._thread: Optional[QThread] = None
        self._service: Optional[DeviceService] = None
        self._guard: Optional[SingleInstanceGuard] = None
        self._lock = InstanceLock()
        self._lock_timer: Optional[QTimer] = None

    def run(self) -> int:
        """
        Start the GUI and run until it quits.

        Returns:
            Process exit code
        """
        prefer_desktop_file_dialogs()
        self._qapp = QApplication(sys.argv)
        self._qapp.setApplicationName("StreamDock")
        # Appended to every window title by the platform: "config.yml — StreamDock".
        self._qapp.setApplicationDisplayName(APP_DISPLAY_NAME)
        self._qapp.setOrganizationName("StreamDock")
        self._qapp.setDesktopFileName("streamdock")
        self._qapp.setWindowIcon(load_app_icon())
        apply_theme(self._qapp, self._design or get_design(), get_scheme())
        self._follow_desktop_scheme()
        install_exception_hook(lambda: self._window)

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
            self._wait_for_device()
        else:
            # Watching also seeds the device list, so no separate refresh.
            self._window.watch_devices_requested.emit()
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

    def _follow_desktop_scheme(self) -> None:
        """
        Repaint when the desktop switches between light and dark.

        Plasma and GNOME both flip at sunset if asked to, and Qt reports it
        through the same signal on either.
        """
        hints = self._qapp.styleHints()
        signal = getattr(hints, 'colorSchemeChanged', None)
        if signal is None:  # pragma: no cover - Qt below 6.5
            logger.debug("Qt does not report colour scheme changes")
            return
        signal.connect(lambda _scheme: theme_manager().refresh())

    def _build_window(self) -> None:
        self._window = MainWindow()

        # load_config reports its own failure; forgetting the path keeps the
        # startup from connecting the device to a file that did not open.
        if self._config_path and not self._window.load_config(self._config_path):
            logger.warning("Could not open %s", self._config_path)
            self._config_path = None

        if not self._config_path:
            self._window.config = ConfigDocument.new_empty()
            self._window.show_status(
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
        window.watch_devices_requested.connect(service.start_watching)
        window.connect_requested.connect(service.connect_device)
        window.disconnect_requested.connect(service.disconnect_device)
        window.apply_config_requested.connect(service.apply_config)
        window.recent_windows_provider = service.recent_windows

        # worker -> GUI
        service.devices_discovered.connect(window.on_devices_discovered)
        service.connection_state_changed.connect(window.on_connection_state_changed)
        service.config_applied.connect(window.on_config_applied)
        service.layout_changed.connect(window.on_layout_changed)
        service.error_occurred.connect(window.on_device_error)
        service.background_error.connect(window.on_background_error)
        service.busy_changed.connect(window.device_bar.set_busy)
        service.device_attached.connect(window.on_device_attached)
        service.device_detached.connect(window.on_device_detached)

        # device bar -> window
        window.device_bar.refresh_requested.connect(window.refresh_devices_requested)
        window.device_bar.connect_requested.connect(window.on_connect_requested)
        window.device_bar.disconnect_requested.connect(window.on_disconnect_requested)
        window.device_bar.apply_requested.connect(window.on_apply_requested)

        window.quit_requested.connect(self._qapp.quit)
        self._guard.activate_requested.connect(self._raise_window)

        if self._tray is not None:
            self._tray.show_requested.connect(self._raise_window)
            self._tray.quit_requested.connect(window.request_quit)
            self._tray.connect_requested.connect(
                lambda: window.on_connect_requested(
                    window.device_bar.selected_device_id() or ""))
            self._tray.disconnect_requested.connect(window.on_disconnect_requested)
            service.connection_state_changed.connect(self._tray.set_state)
            service.device_attached.connect(
                lambda label: self._notify_tray("Device connected", label))
            service.device_detached.connect(
                lambda label: self._notify_tray("Device unplugged", label))

    # ── lifecycle ─────────────────────────────────────────────────────────

    def _raise_window(self) -> None:
        self._window.show()
        self._window.setWindowState(
            self._window.windowState() & ~self._window.windowState().WindowMinimized)
        self._window.raise_()
        self._window.activateWindow()

    def _notify_tray(self, title: str, message: str) -> None:
        """Show a tray balloon, so hotplug is visible with the window hidden."""
        if self._tray is not None:
            self._tray.showMessage(title, message,
                                   QSystemTrayIcon.MessageIcon.Information, 4000)

    def _set_device_locked(self, locked: bool) -> None:
        self._window.device_locked = locked
        self._window.device_bar.setEnabled(not locked)
        if self._tray is not None:
            self._tray.set_locked(locked)

    def _warn_device_in_use(self) -> None:
        pid = self._lock.owner_pid()
        detail = f" (pid {pid})" if pid else ""
        self._set_device_locked(True)
        QMessageBox.warning(
            self._window, "Device in use",
            f"Another StreamDock process{detail} already controls the device.\n\n"
            "You can edit and save configurations, but connecting is disabled "
            "until that process exits.")

    def _wait_for_device(self) -> None:
        """Keep trying for the device, so the window takes over once the other process exits."""
        self._lock_timer = QTimer()
        self._lock_timer.setInterval(LOCK_RETRY_MS)
        self._lock_timer.timeout.connect(self._retry_lock)
        self._lock_timer.start()

    def _retry_lock(self) -> None:
        if not self._lock.acquire():
            return
        self._lock_timer.stop()
        logger.info("The device is free; taking it over")
        self._set_device_locked(False)
        self._window.show_status("The device is free again", 5000)
        self._window.watch_devices_requested.emit()

    def _shutdown(self) -> None:
        """Release the device and stop the worker thread."""
        if self._lock_timer is not None:
            self._lock_timer.stop()
        if self._service is not None:
            # On the worker, behind anything already queued there, so a
            # connect in flight cannot race the teardown. Called directly
            # only once the thread is gone: the device is released either way.
            try:
                if self._thread is not None and self._thread.isRunning():
                    QMetaObject.invokeMethod(
                        self._service, "shutdown",
                        Qt.ConnectionType.BlockingQueuedConnection)
                else:
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
         start_minimized: bool = False, design: Optional[str] = None) -> int:
    """
    Run the GUI.

    Args:
        config_path: Configuration to open
        device_id: Device to connect to, from device_key()
        start_minimized: Start hidden in the tray
        design: Force 'kde' or 'gnome' for this run only

    Returns:
        Process exit code
    """
    return StreamDockGui(config_path, device_id, start_minimized, design).run()
