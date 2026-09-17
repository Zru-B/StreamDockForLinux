"""
Icons from the desktop's own theme.

A Plasma application does not draw its own toolbar glyphs: it names them, and
the icon theme the user chose supplies the picture. This module is that
naming, with the fallbacks that keep the window usable on a system where the
theme cannot be found - a button with no icon still has its text.
"""

import logging
from typing import Dict, Iterable, Optional, Tuple

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyle

from StreamDock.ui.theme.detection import (
    Scheme,
    icon_theme_directories,
    read_kde_icon_theme,
)

logger = logging.getLogger(__name__)

# The icon each design puts on a dialog button, keyed by the button's label.
# These follow KStandardGuiItem, which is what every KDE dialog uses.
BUTTON_ICONS: Dict[str, Tuple[str, ...]] = {
    'ok': ('dialog-ok',),
    'save': ('document-save',),
    'cancel': ('dialog-cancel',),
    'close': ('dialog-close',),
    'apply': ('dialog-ok-apply',),
    'delete': ('edit-delete',),
    'remove': ('edit-delete', 'list-remove'),
    'add': ('list-add',),
    'add action': ('list-add',),
    'browse': ('document-open',),
    'select icon': ('insert-image', 'document-open'),
    'choose': ('color-picker',),
    'reset to default': ('edit-undo',),
    'open': ('document-open',),
    'new': ('document-new',),
    'connect': ('network-connect',),
    'disconnect': ('network-disconnect',),
}

# Qt's own standard pictures, translated into freedesktop icon names so a
# message box or a file dialog shows the desktop's icons rather than the
# base style's.
STANDARD_ICONS: Dict[QStyle.StandardPixmap, Tuple[str, ...]] = {
    QStyle.StandardPixmap.SP_MessageBoxInformation: ('dialog-information',),
    QStyle.StandardPixmap.SP_MessageBoxWarning: ('dialog-warning',),
    QStyle.StandardPixmap.SP_MessageBoxCritical: ('dialog-error',),
    QStyle.StandardPixmap.SP_MessageBoxQuestion: ('dialog-question',),
    QStyle.StandardPixmap.SP_DialogOkButton: ('dialog-ok',),
    QStyle.StandardPixmap.SP_DialogCancelButton: ('dialog-cancel',),
    QStyle.StandardPixmap.SP_DialogHelpButton: ('help-contents',),
    QStyle.StandardPixmap.SP_DialogOpenButton: ('document-open',),
    QStyle.StandardPixmap.SP_DialogSaveButton: ('document-save',),
    QStyle.StandardPixmap.SP_DialogCloseButton: ('dialog-close',),
    QStyle.StandardPixmap.SP_DialogApplyButton: ('dialog-ok-apply',),
    QStyle.StandardPixmap.SP_DialogResetButton: ('edit-undo',),
    QStyle.StandardPixmap.SP_DialogDiscardButton: ('edit-delete',),
    QStyle.StandardPixmap.SP_DialogYesButton: ('dialog-ok',),
    QStyle.StandardPixmap.SP_DialogNoButton: ('dialog-cancel',),
    QStyle.StandardPixmap.SP_DialogAbortButton: ('dialog-cancel',),
    QStyle.StandardPixmap.SP_DialogRetryButton: ('view-refresh',),
    QStyle.StandardPixmap.SP_DialogIgnoreButton: ('dialog-ok',),
    QStyle.StandardPixmap.SP_DialogYesToAllButton: ('dialog-ok',),
    QStyle.StandardPixmap.SP_DialogNoToAllButton: ('dialog-cancel',),
    QStyle.StandardPixmap.SP_DialogSaveAllButton: ('document-save-all', 'document-save'),
    QStyle.StandardPixmap.SP_ArrowUp: ('go-up',),
    QStyle.StandardPixmap.SP_ArrowDown: ('go-down',),
    QStyle.StandardPixmap.SP_ArrowLeft: ('go-previous',),
    QStyle.StandardPixmap.SP_ArrowRight: ('go-next',),
    QStyle.StandardPixmap.SP_ArrowBack: ('go-previous',),
    QStyle.StandardPixmap.SP_ArrowForward: ('go-next',),
    QStyle.StandardPixmap.SP_DirIcon: ('folder',),
    QStyle.StandardPixmap.SP_DirOpenIcon: ('folder-open',),
    QStyle.StandardPixmap.SP_DirClosedIcon: ('folder',),
    QStyle.StandardPixmap.SP_DirHomeIcon: ('user-home',),
    QStyle.StandardPixmap.SP_FileIcon: ('text-x-generic',),
    QStyle.StandardPixmap.SP_FileDialogNewFolder: ('folder-new',),
    QStyle.StandardPixmap.SP_FileDialogBack: ('go-previous',),
    QStyle.StandardPixmap.SP_FileDialogToParent: ('go-up',),
    QStyle.StandardPixmap.SP_FileDialogDetailedView: ('view-list-details',),
    QStyle.StandardPixmap.SP_FileDialogListView: ('view-list-icons',),
    QStyle.StandardPixmap.SP_BrowserReload: ('view-refresh',),
    QStyle.StandardPixmap.SP_BrowserStop: ('process-stop',),
    QStyle.StandardPixmap.SP_TrashIcon: ('user-trash',),
    QStyle.StandardPixmap.SP_LineEditClearButton: ('edit-clear',),
}

# The icon themes Plasma ships, one per scheme.
BREEZE_ICON_THEMES = {Scheme.LIGHT: 'breeze', Scheme.DARK: 'breeze-dark'}


def themed_icon(*names: str, fallback: Optional[QIcon] = None) -> QIcon:
    """
    The first icon of these the theme can supply.

    Args:
        names: freedesktop icon names, most specific first
        fallback: What to return when none resolves

    Returns:
        The icon, or ``fallback``, or an empty QIcon
    """
    for name in names:
        if not name:
            continue
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            return icon
    return fallback if fallback is not None else QIcon()


def button_icon(text: str) -> QIcon:
    """
    The icon a KDE dialog puts on a button with this label.

    Args:
        text: The button label, with or without a trailing ellipsis

    Returns:
        The icon, empty when the label is not a standard one or the theme
        has nothing for it
    """
    key = text.replace('&', '').rstrip('.…').strip().lower()
    names = BUTTON_ICONS.get(key)
    if names is None:
        return QIcon()
    return themed_icon(*names)


def standard_icon(pixmap: QStyle.StandardPixmap) -> QIcon:
    """
    The themed replacement for one of Qt's standard pictures.

    Args:
        pixmap: What Qt asked for

    Returns:
        The icon, empty when the theme has nothing for it
    """
    names = STANDARD_ICONS.get(pixmap)
    if names is None:
        return QIcon()
    return themed_icon(*names)


def ensure_icon_theme(scheme: Scheme) -> str:
    """
    Make sure ``QIcon.fromTheme`` has a theme to look in.

    Qt finds the session's icon theme through its platform theme. A PyQt
    wheel has no KDE platform plugin, and under some platforms Qt then
    reports no theme at all, so every icon comes back empty; this fills in
    what Plasma would have said. A theme Qt did resolve is left alone,
    except that the stock Breeze pair is matched to the scheme being painted:
    the dark variant's icons are white, and vanish on a light window.

    Args:
        scheme: The scheme about to be painted

    Returns:
        The theme name in force afterwards
    """
    wanted = BREEZE_ICON_THEMES[scheme]
    current = QIcon.themeName()

    if current in BREEZE_ICON_THEMES.values() and current != wanted:
        QIcon.setThemeName(wanted)
        return wanted

    if current:
        return current

    directories = icon_theme_directories()
    if directories:
        QIcon.setThemeSearchPaths(directories + list(QIcon.themeSearchPaths()))

    configured = read_kde_icon_theme()
    name = configured if configured and configured not in BREEZE_ICON_THEMES.values() else wanted
    QIcon.setThemeName(name)
    if not QIcon.fallbackThemeName():
        QIcon.setFallbackThemeName(BREEZE_ICON_THEMES[Scheme.LIGHT])
    logger.debug("Icon theme set to %r", name)
    return name


def has_any_icon(names: Iterable[str]) -> bool:
    """
    Whether the theme can supply at least one of these icons.

    Args:
        names: freedesktop icon names

    Returns:
        True when one resolves
    """
    return not themed_icon(*names).isNull()
