"""
Raise the running window instead of starting a second one.

Complements InstanceLock: the lock decides who owns the device, this decides
what a second launch does about it. Kept separate because the headless entry
point has no Qt and cannot participate here.
"""

import logging
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

DEFAULT_KEY = "streamdock-gui"
ACTIVATE = b"RAISE"
CONNECT_TIMEOUT_MS = 200


class SingleInstanceGuard(QObject):
    """A local socket the first GUI listens on and later ones knock at."""

    activate_requested = pyqtSignal()

    def __init__(self, key: str = DEFAULT_KEY, parent: Optional[QObject] = None):
        """
        Args:
            key: Local socket name. Per-user on Linux, since it lives in
                XDG_RUNTIME_DIR.
            parent: Qt parent
        """
        super().__init__(parent)
        self._key = key
        self._server: Optional[QLocalServer] = None

    def try_acquire(self) -> bool:
        """
        Become the primary instance.

        Returns:
            True if this process is now the primary instance, False if
            another GUI is already running.
        """
        if self._is_running():
            return False

        # Clears a socket file left behind by a crash; harmless otherwise,
        # because nothing answered the probe above.
        QLocalServer.removeServer(self._key)

        server = QLocalServer(self)
        if not server.listen(self._key):
            logger.warning("Could not listen on %s: %s", self._key, server.errorString())
            return True

        server.newConnection.connect(self._on_connection)
        self._server = server
        return True

    def signal_existing(self) -> bool:
        """
        Ask the running instance to show itself.

        Returns:
            True if the message was delivered.
        """
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        if not socket.waitForConnected(CONNECT_TIMEOUT_MS):
            return False

        socket.write(ACTIVATE)
        socket.flush()
        socket.waitForBytesWritten(CONNECT_TIMEOUT_MS)
        socket.disconnectFromServer()
        return True

    def close(self) -> None:
        """Stop listening. Safe to call when never acquired."""
        if self._server is not None:
            self._server.close()
            QLocalServer.removeServer(self._key)
            self._server = None

    def _is_running(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self._key)
        connected = socket.waitForConnected(CONNECT_TIMEOUT_MS)
        if connected:
            socket.disconnectFromServer()
        return connected

    def _on_connection(self) -> None:
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._on_ready(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _on_ready(self, socket: QLocalSocket) -> None:
        if ACTIVATE in bytes(socket.readAll()):
            self.activate_requested.emit()
