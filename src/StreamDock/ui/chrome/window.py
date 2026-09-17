"""
The two window arrangements.

Plasma 6 applications - Dolphin, Kate, Okular - keep their actions in a
toolbar along the top of the window, with a menu button at its far end and
the traditional menu bar hidden until Ctrl+M asks for it. The toolbar and the
title bar share the header colour, which dims when the window loses focus,
and messages land in a status bar along the bottom.

GNOME has none of that: the actions live in a header bar with a primary menu
at its end, and messages arrive as a toast over the content. The main window
builds its actions once and hands them to whichever of these is in use.
"""

import logging
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import QEvent, QObject, QSize, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from StreamDock.ui.chrome.model import ChromeModel, MenuSpec
from StreamDock.ui.chrome.toast import Toast
from StreamDock.ui.settings_store import get_menubar_visible, set_menubar_visible
from StreamDock.ui.theme import Flavor, assets_glyph, current_theme, themed_icon

logger = logging.getLogger(__name__)

SHOW_MENUBAR_TEXT = "Show &Menu Bar"
SHOW_MENUBAR_SHORTCUT = "Ctrl+M"
MENU_BUTTON_TEXT = "Open Menu"
MENUBAR_HIDDEN_HINT = "Menu bar hidden. Press Ctrl+M to show it again."

# Where the menu-bar toggle is filed when a menu bar is showing: KDE puts it
# under Settings, as the last thing before the configuration entries.
_SETTINGS_MENU_TITLE = "settings"


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

    def set_document(self, name: str, modified: bool, path: str = "") -> None:
        """
        Show which file is open.

        Args:
            name: File name, or '' when nothing is saved yet
            modified: Whether it has unsaved edits
            path: The full path, when there is one
        """

    def hosts_device_bar(self) -> bool:
        """
        Whether the chrome has taken the device controls into itself.

        Returns:
            True when the window should not place them in its own layout
        """
        return False


class KdeChrome(WindowChrome):
    """
    Plasma 6: a toolbar with a menu button, a status bar, and a menu bar on request.

    The toolbar is the tools area: the file actions on the left, the device
    picker and Apply after them, the menu button at the far right. The menu
    bar is built regardless, so its shortcuts and mnemonics exist, but stays
    hidden unless the user turned it on.
    """

    def __init__(self, window: QMainWindow, model: ChromeModel):
        super().__init__(window, model)
        self._toolbar: Optional[QToolBar] = None
        self._menu_button: Optional[QToolButton] = None
        self._menu: Optional[QMenu] = None
        self._menubar_action: Optional[QAction] = None
        self._document_label: Optional[QLabel] = None
        self._watcher: Optional[_ActivationWatcher] = None

    # ── building ──────────────────────────────────────────────────────────

    def install(self) -> None:
        menubar = self._build_menubar()
        self._toolbar = self._build_toolbar()
        self.window.addToolBar(Qt.ToolBarArea.TopToolBarArea, self._toolbar)
        self.window.setStatusBar(self._build_status_bar())

        # The tools area follows the window's focus, the way Breeze's title
        # bar does: header colour when active, window colour when not.
        self._watcher = _ActivationWatcher(self.window, [menubar, self._toolbar])
        self.window.installEventFilter(self._watcher)
        self._watcher.refresh()

    def remove(self) -> None:
        if self._watcher is not None:
            self.window.removeEventFilter(self._watcher)
            self._watcher = None

        if self._toolbar is not None:
            # Handing the device controls back before the toolbar goes: the
            # toolbar would otherwise take them with it.
            if self.model.device_action is not None:
                self._toolbar.removeAction(self.model.device_action)
            self.window.removeToolBar(self._toolbar)
            self._toolbar.setParent(None)
            self._toolbar.deleteLater()
            self._toolbar = None
        self._menu_button = None
        self._menu = None

        if self._menubar_action is not None:
            self.window.removeAction(self._menubar_action)
            self._menubar_action.deleteLater()
            self._menubar_action = None

        self.window.menuBar().clear()
        # Qt deletes a replaced menu bar for us; setMenuWidget cannot replace
        # one that is still installed, so it has to go first.
        self.window.setMenuBar(None)
        _drop_status_bar(self.window)
        self._document_label = None

    def show_status(self, message: str, timeout: int = 0) -> None:
        self.window.statusBar().showMessage(message, timeout)

    def current_status(self) -> str:
        status = self.window.statusBar()
        return status.currentMessage() if status is not None else ""

    def set_document(self, name: str, modified: bool, path: str = "") -> None:
        if self._document_label is None:
            return
        self._document_label.setText(_pretty_path(path) if path else name)
        self._document_label.setToolTip(path)

    def hosts_device_bar(self) -> bool:
        return (self._toolbar is not None and self.model.device_action is not None
                and self.model.device_action in self._toolbar.actions())

    @property
    def menubar_visible(self) -> bool:
        """Whether the traditional menu bar is currently showing."""
        return not self.window.menuBar().isHidden()

    @property
    def menubar_action(self) -> Optional[QAction]:
        """The Ctrl+M toggle."""
        return self._menubar_action

    @property
    def menu_button(self) -> Optional[QToolButton]:
        """The button at the end of the toolbar that opens the menu."""
        return self._menu_button

    @property
    def toolbar(self) -> Optional[QToolBar]:
        """The tools area."""
        return self._toolbar

    # ── pieces ────────────────────────────────────────────────────────────

    def _build_menubar(self) -> QMenuBar:
        """
        The traditional menu bar, hidden unless the user asked for it.

        Returns:
            The window's menu bar, filled
        """
        menubar = self.window.menuBar()
        menubar.clear()
        for spec in self.model.menus:
            _fill_menu(menubar.addMenu(spec.title), spec.entries)

        self._menubar_action = QAction(SHOW_MENUBAR_TEXT, self.window)
        self._menubar_action.setCheckable(True)
        self._menubar_action.setShortcut(QKeySequence(SHOW_MENUBAR_SHORTCUT))
        self._menubar_action.setIcon(themed_icon('show-menu', 'application-menu'))
        self._menubar_action.setChecked(get_menubar_visible())
        self._menubar_action.toggled.connect(self._on_menubar_toggled)
        # On the window itself, so Ctrl+M works while the menu bar - the
        # only other place it would live - is hidden.
        self.window.addAction(self._menubar_action)

        settings = _find_menu(menubar, _SETTINGS_MENU_TITLE)
        if settings is not None:
            settings.addSeparator()
            settings.addAction(self._menubar_action)

        menubar.setVisible(self._menubar_action.isChecked())
        return menubar

    def _build_toolbar(self) -> QToolBar:
        """
        The tools area.

        Returns:
            The toolbar, not yet attached
        """
        metrics = current_theme().metrics

        toolbar = QToolBar("Main Toolbar", self.window)
        toolbar.setObjectName("mainToolBar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        toolbar.setIconSize(QSize(metrics.icon_size, metrics.icon_size))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        # Qt's own toolbar menu could hide the strip with nothing to bring
        # it back; the menu button is the way into the window's options.
        toolbar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

        for action in self.model.toolbar_actions:
            toolbar.addAction(action)

        if self.model.device_action is not None:
            if self.model.toolbar_actions:
                toolbar.addSeparator()
            toolbar.addAction(self.model.device_action)
        else:
            spacer = QWidget()
            spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            toolbar.addWidget(spacer)

        self._menu_button = self._build_menu_button()
        toolbar.addWidget(self._menu_button)

        # Toolbar buttons are for the pointer; Tab moves between the controls
        # in the window, as it does in every KDE application.
        for action in toolbar.actions():
            button = toolbar.widgetForAction(action)
            if isinstance(button, QToolButton):
                button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return toolbar

    def _build_menu_button(self) -> QToolButton:
        """
        The menu button at the end of the toolbar, and the menu behind it.

        The menu carries every command the menu bar does, sectioned rather
        than nested, with the menu-bar toggle and Quit at the bottom - the
        arrangement KDE's own hamburger menus settle on.

        Returns:
            The button, with its menu attached
        """
        button = QToolButton()
        button.setObjectName("menuButton")
        button.setText(MENU_BUTTON_TEXT)
        button.setToolTip(MENU_BUTTON_TEXT)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)

        glyph = assets_glyph('menu', current_theme().palette.text_primary)
        button.setIcon(themed_icon('application-menu', 'open-menu-symbolic',
                                   fallback=QIcon(glyph) if glyph else None))

        self._menu = QMenu(button)
        quit_actions: List[QAction] = []
        for spec in self.model.menus:
            entries = []
            for entry in spec.entries:
                # Quit closes the menu, whichever group filed it.
                if _is_quit(entry):
                    quit_actions.append(entry)
                else:
                    entries.append(entry)
            entries = _trim_separators(entries)
            if not entries:
                continue
            if self._menu.actions():
                self._menu.addSeparator()
            _fill_menu(self._menu, entries)

        if self._menubar_action is not None:
            self._menu.addSeparator()
            self._menu.addAction(self._menubar_action)
        if quit_actions:
            self._menu.addSeparator()
            for action in quit_actions:
                self._menu.addAction(action)

        button.setMenu(self._menu)
        return button

    def _build_status_bar(self) -> QStatusBar:
        """
        The status bar: messages on the left, the open file on the right.

        Returns:
            The status bar, not yet attached
        """
        status = QStatusBar(self.window)
        status.setSizeGripEnabled(False)

        self._document_label = QLabel()
        self._document_label.setObjectName("statusDocument")
        status.addPermanentWidget(self._document_label)
        return status

    def _on_menubar_toggled(self, visible: bool) -> None:
        """
        Show or hide the menu bar, and remember the choice.

        Args:
            visible: Whether it should be showing
        """
        self.window.menuBar().setVisible(visible)
        set_menubar_visible(visible)
        if not visible:
            self.show_status(MENUBAR_HIDDEN_HINT, 6000)


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

    def set_document(self, name: str, modified: bool, path: str = "") -> None:
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


class _ActivationWatcher(QObject):
    """
    Marks the tools area as active or inactive along with its window.

    The stylesheet reads the ``windowActive`` property; Qt does not restyle
    on a property change by itself, so each strip is repolished.
    """

    def __init__(self, window: QMainWindow, strips: List[QWidget]):
        super().__init__(window)
        self._window = window
        self._strips = strips

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate,
                            QEvent.Type.ActivationChange):
            self.refresh()
        return super().eventFilter(watched, event)

    def refresh(self) -> None:
        """Read the window's state and paint the strips to match."""
        active = self._window.isActiveWindow() or not self._window.isVisible()
        for strip in self._strips:
            if strip.property("windowActive") == active:
                continue
            strip.setProperty("windowActive", active)
            strip.style().unpolish(strip)
            strip.style().polish(strip)
            strip.update()


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


def _find_menu(menubar: QMenuBar, title: str) -> Optional[QMenu]:
    """
    Find a top-level menu by its title, ignoring mnemonics and case.

    Args:
        menubar: Where to look
        title: The title, without ampersands

    Returns:
        The menu, or None
    """
    for action in menubar.actions():
        menu = action.menu()
        if menu is not None and action.text().replace("&", "").strip().lower() == title:
            return menu
    return None


def _is_quit(entry) -> bool:
    """Whether a menu entry is the application's Quit action."""
    return isinstance(entry, QAction) and entry.menuRole() == QAction.MenuRole.QuitRole


def _trim_separators(entries: List) -> List:
    """
    Drop separators left dangling at either end of a group.

    Args:
        entries: A group's entries

    Returns:
        The entries without leading, trailing or doubled separators
    """
    trimmed: List = []
    for entry in entries:
        if entry is None and (not trimmed or trimmed[-1] is None):
            continue
        trimmed.append(entry)
    while trimmed and trimmed[-1] is None:
        trimmed.pop()
    return trimmed


def _pretty_path(path: str) -> str:
    """
    A path as a person would write it: home abbreviated to a tilde.

    Args:
        path: An absolute path

    Returns:
        The path with the home directory collapsed
    """
    try:
        return "~/" + Path(path).relative_to(Path.home()).as_posix()
    except ValueError:
        return path


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
