"""
The floating message GNOME shows instead of a status bar.

A toast sits over the content, says one thing, and leaves. It follows the
window as it resizes, so it never needs a place reserved for it in the layout.
"""

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

MARGIN = 20
DEFAULT_TIMEOUT = 5000


class Toast(QFrame):
    """A transient message pinned near the bottom of its parent."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Purely informational: clicking through to the content beneath is
        # better than a message stealing a press.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 16, 8)

        self._label = QLabel("")
        self._label.setObjectName("toastText")
        row.addWidget(self._label)

        self._message = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._clear)

        self.hide()
        parent.installEventFilter(self)

    def show_message(self, message: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        """
        Say something, briefly.

        Args:
            message: The text to show; empty hides the toast
            timeout: Milliseconds to stay up, or 0 to stay until replaced
        """
        self._timer.stop()
        self._message = message
        if not message:
            self.hide()
            return

        self._label.setText(message)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

        if timeout > 0:
            self._timer.start(timeout)

    def message(self) -> str:
        """
        Whatever the toast is currently saying.

        Reports what was set rather than what is painted: a window that has
        not been shown yet has no visible children, and the message is still
        the one the user will see.

        Returns:
            The message, or '' when it has expired or was never set
        """
        return self._message

    def _clear(self) -> None:
        """Take the message down when its time is up."""
        self._message = ""
        self.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Keep the toast centred as the window changes size."""
        if event.type() == QEvent.Type.Resize and watched is self.parent():
            self._reposition()
        return super().eventFilter(watched, event)

    def _reposition(self) -> None:
        """Centre the toast near the bottom of the window."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.move(max(MARGIN, (parent.width() - self.width()) // 2),
                  max(MARGIN, parent.height() - self.height() - MARGIN))
