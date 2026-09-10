"""
Dialogs that wear the active design.

The two desktops disagree about where a dialog's decisions live. Breeze puts
them in a row along the bottom, affirmative last. Adwaita puts them in the
header: cancel at the start, the action that leads at the end, and nothing
along the bottom at all. Subclasses build their content and say what the
decisions are; where those land is settled here.
"""

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from StreamDock.ui.theme import Flavor, current_theme

CANCEL_TEXT = "Cancel"


def make_button(text: str, role: str = "") -> QPushButton:
    """
    Build a dialog button at the size the active design uses.

    The look comes from the stylesheet; this only fixes the geometry so a row
    of them lines up rather than each swelling to fill the layout.

    Args:
        text: Button label
        role: 'primary' or 'danger' to mark the action that leads, '' for a
            quiet one

    Returns:
        The button
    """
    metrics = current_theme().metrics
    button = QPushButton(text)
    button.setMinimumWidth(metrics.button_min_width)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if role:
        button.setProperty("buttonType", role)
    return button


class ThemedDialog(QDialog):
    """
    A dialog whose content is separate from its decisions.

    Build into :attr:`content_layout`, then call :meth:`add_actions` once at
    the end of setup.
    """

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        if title:
            self.setWindowTitle(title)

        metrics = current_theme().metrics
        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(0)

        content = QWidget()
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(
            metrics.window_margin, metrics.window_margin,
            metrics.window_margin, metrics.window_margin)
        self._content_layout.setSpacing(metrics.spacing)
        self._outer.addWidget(content, stretch=1)

        self.affirmative_button: Optional[QPushButton] = None
        self.cancel_button: Optional[QPushButton] = None

    @property
    def content_layout(self) -> QVBoxLayout:
        """
        Where the dialog's own widgets go.

        Returns:
            The content layout
        """
        return self._content_layout

    def add_actions(self, affirmative: str, on_affirmative: Callable,
                    cancel: Optional[str] = CANCEL_TEXT,
                    on_cancel: Optional[Callable] = None,
                    role: str = "primary") -> None:
        """
        Attach the dialog's decisions where the active design puts them.

        Args:
            affirmative: Label for the action that leads
            on_affirmative: What it does
            cancel: Label for the way out, or None for a dialog that only
                closes
            on_cancel: What that does; defaults to rejecting the dialog
            role: 'primary' or 'danger', deciding how loudly the affirmative
                is drawn
        """
        self.affirmative_button = make_button(affirmative, role)
        self.affirmative_button.clicked.connect(on_affirmative)
        self.affirmative_button.setDefault(True)

        if cancel is not None:
            self.cancel_button = make_button(cancel)
            self.cancel_button.clicked.connect(on_cancel or self.reject)
            self.cancel_button.setAutoDefault(False)

        if current_theme().flavor is Flavor.GNOME:
            self._outer.insertWidget(0, self._header_bar())
        else:
            self._outer.addLayout(self._button_row())

    # ── the two arrangements ──────────────────────────────────────────────

    def _button_row(self) -> QHBoxLayout:
        """
        Breeze: one right-aligned row along the bottom, affirmative last.

        Returns:
            The row
        """
        metrics = current_theme().metrics
        row = QHBoxLayout()
        row.setContentsMargins(metrics.window_margin, 0,
                               metrics.window_margin, metrics.window_margin)
        row.setSpacing(metrics.spacing_tight)
        row.addStretch()
        if self.cancel_button is not None:
            row.addWidget(self.cancel_button)
        row.addWidget(self.affirmative_button)
        return row

    def _header_bar(self) -> QWidget:
        """
        Adwaita: the decisions in the header, with the title between them.

        Returns:
            The header strip
        """
        metrics = current_theme().metrics

        header = QWidget()
        header.setObjectName("dialogHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QHBoxLayout(header)
        row.setContentsMargins(metrics.spacing_tight, 6, metrics.spacing_tight, 6)
        row.setSpacing(metrics.spacing_tight)

        if self.cancel_button is not None:
            row.addWidget(self.cancel_button)
        else:
            row.addSpacing(metrics.button_min_width)

        title = QLabel(self.windowTitle())
        title.setObjectName("dialogHeaderTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(title, stretch=1)

        row.addWidget(self.affirmative_button)
        return header
