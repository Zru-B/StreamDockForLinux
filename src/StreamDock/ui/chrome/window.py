"""
The two window arrangements.

KDE puts a menu bar at the top and a status bar at the bottom, and lets the
title bar carry the document name. GNOME has neither: the actions live in a
header bar with a primary menu at its end, and messages arrive as a toast over
the content. The main window builds its actions once and hands them to
whichever of these is in use.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from StreamDock.ui.chrome.model import ChromeModel, MenuSpec
from StreamDock.ui.chrome.toast import Toast
from StreamDock.ui.theme import Flavor, assets_glyph, current_theme

logger = logging.getLogger(__name__)


class WindowChrome:
    """What every arrangement has to provide."""

    def __init__(self, window: QMainWindow, model: ChromeModel):
        self.window = window
        self.model = model

    def install(self) -> None:
        """Build the chrome and attach it to the window."""
        raise NotImplementedError

    def remove(self) -> None:
        """Take the chrome off again, so another can be installed."""
        raise NotImplementedError

    def show_status(self, message: str, timeout: int = 0) -> None:
        """
        Report something to the user.

        Args:
            message: The text to show
            timeout: Milliseconds before it disappears, 0 to leave it up
        """
        raise NotImplementedError

    def current_status(self) -> str:
        """
        Whatever the chrome is currently saying.

        Returns:
            The message, or '' when there is none
        """
        raise NotImplementedError

    def set_document(self, name: str, modified: bool) -> None:
        """
        Show which file is open.

        Args:
            name: File name, or '' when nothing is saved yet
            modified: Whether it has unsaved edits
        """


class KdeChrome(WindowChrome):
    """A menu bar above and a status bar below, the way a Plasma application sits."""

    def install(self) -> None:
        menubar = self.window.menuBar()
        menubar.clear()
        menubar.show()
        for spec in self.model.menus:
            _fill_menu(menubar.addMenu(spec.title), spec.entries)

        self.window.setStatusBar(QStatusBar(self.window))

    def remove(self) -> None:
        self.window.menuBar().clear()
        # Qt deletes a replaced menu bar for us; setMenuWidget cannot replace
        # one that is still installed, so it has to go first.
        self.window.setMenuBar(None)
        _drop_status_bar(self.window)

    def show_status(self, message: str, timeout: int = 0) -> None:
        self.window.statusBar().showMessage(message, timeout)

    def current_status(self) -> str:
        status = self.window.statusBar()
        return status.currentMessage() if status is not None else ""


class GnomeChrome(WindowChrome):
    """
    A header bar carrying the primary actions and a menu, with toasts for messages.

    The header is a strip inside the window rather than a real client-side
    decoration: replacing the title bar would cost the window management the
    rest of the session provides, for a border's worth of authenticity.
    """

    HEADER_HEIGHT = 46

    def __init__(self, window: QMainWindow, model: ChromeModel):
        super().__init__(window, model)
        self._header: Optional[QWidget] = None
        self._title: Optional[QLabel] = None
        self._subtitle: Optional[QLabel] = None
        self._toast: Optional[Toast] = None
        self._menu: Optional[QMenu] = None

    def install(self) -> None:
        metrics = current_theme().metrics

        self._header = QWidget()
        self._header.setObjectName("headerBar")
        self._header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._header.setFixedHeight(self.HEADER_HEIGHT)

        row = QHBoxLayout(self._header)
        row.setContentsMargins(metrics.spacing_tight, 6, metrics.spacing_tight, 6)
        row.setSpacing(metrics.spacing_tight)

        if self.model.open_action is not None:
            row.addWidget(_header_button(self.model.open_action))

        row.addStretch()
        row.addWidget(self._build_title())
        row.addStretch()

        if self.model.save_action is not None:
            save = _header_button(self.model.save_action)
            save.setProperty("buttonType", "primary")
            row.addWidget(save)

        row.addWidget(self._build_menu_button())

        self.window.setMenuWidget(self._header)
        _drop_status_bar(self.window)
        self._toast = Toast(self.window)

    def remove(self) -> None:
        if self._toast is not None:
            self._toast.deleteLater()
            self._toast = None
        self._menu = None
        self._title = None
        self._subtitle = None
        self._header = None
        # Qt deletes the widget it is replacing, so the header goes with it.
        self.window.setMenuWidget(None)

    def show_status(self, message: str, timeout: int = 0) -> None:
        if self._toast is not None:
            self._toast.show_message(message, timeout or 0)

    def current_status(self) -> str:
        return self._toast.message() if self._toast is not None else ""

    def set_document(self, name: str, modified: bool) -> None:
        if self._subtitle is None:
            return
        # GNOME writes the unsaved marker into the subtitle rather than the
        # title bar, which it does not control.
        suffix = " • Unsaved changes" if modified else ""
        self._subtitle.setText(f"{name or 'No configuration'}{suffix}")

    def _build_title(self) -> QWidget:
        """
        The centred title block.

        Returns:
            A widget holding the application name and the open document
        """
        block = QWidget()
        block.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        column = QVBoxLayout(block)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self._title = QLabel(self.model.title or "StreamDock")
        self._title.setObjectName("headerTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self._title)

        self._subtitle = QLabel("")
        self._subtitle.setObjectName("headerSubtitle")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self._subtitle)

        return block

    def _build_menu_button(self) -> QPushButton:
        """
        The primary menu, flattened out of the menu bar's groups.

        Returns:
            The hamburger button, with its menu attached
        """
        button = QPushButton()
        button.setObjectName("headerMenuButton")
        button.setToolTip("Main menu")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIconSize(QSize(16, 16))

        glyph = assets_glyph('menu', current_theme().palette.text_primary)
        if glyph:
            button.setIcon(QIcon(glyph))
        else:  # pragma: no cover - only when the cache is unwritable
            button.setText("☰")

        self._menu = QMenu(button)
        for index, spec in enumerate(self.model.menus):
            if index:
                self._menu.addSeparator()
            _fill_menu(self._menu, spec.entries)
        button.setMenu(self._menu)

        return button


def make_chrome(window: QMainWindow, model: ChromeModel) -> WindowChrome:
    """
    Build the arrangement the active design calls for.

    Args:
        window: The window to dress
        model: Its actions and their grouping

    Returns:
        The chrome, not yet installed
    """
    if current_theme().flavor is Flavor.GNOME:
        return GnomeChrome(window, model)
    return KdeChrome(window, model)


def _drop_status_bar(window: QMainWindow) -> None:
    """
    Take the status bar off a window for good.

    ``setStatusBar(None)`` only unlinks it from the layout - the widget stays
    a child of the window and keeps its geometry, so a design that has no
    status bar would still show a strip along the bottom.

    Args:
        window: The window to strip
    """
    existing = window.findChild(QStatusBar, options=Qt.FindChildOption.FindDirectChildrenOnly)
    window.setStatusBar(None)
    if existing is not None:
        existing.hide()
        existing.setParent(None)
        existing.deleteLater()


def _fill_menu(menu: QMenu, entries: List) -> QMenu:
    """
    Put one group's entries into a menu.

    Args:
        menu: The menu to fill
        entries: Actions, nested MenuSpecs, and None for separators

    Returns:
        The same menu
    """
    for entry in entries:
        if entry is None:
            menu.addSeparator()
        elif isinstance(entry, MenuSpec):
            _fill_menu(menu.addMenu(entry.title), entry.entries)
        else:
            menu.addAction(entry)
    return menu


def _header_button(action: QAction) -> QPushButton:
    """
    Promote an action into a header-bar button.

    Args:
        action: The action to fire

    Returns:
        A button wired to it, following its enabled state and tooltip
    """
    # The ampersands are menu mnemonics; a header button shows plain words.
    button = QPushButton(action.text().replace("&", "").rstrip("."))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(action.toolTip() or action.text().replace("&", ""))
    button.clicked.connect(action.trigger)
    button.setEnabled(action.isEnabled())
    action.changed.connect(lambda: button.setEnabled(action.isEnabled()))
    return button
