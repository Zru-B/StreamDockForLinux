"""
Where the window and its dialogs put their furniture.

Two arrangements ship: a Plasma one with a toolbar, a menu button and a
status bar, and a GNOME one with a header bar and toasts. The rest of the UI
describes what it needs and never picks between them.
"""

from StreamDock.ui.chrome.dialog import ThemedDialog, make_button
from StreamDock.ui.chrome.model import SEPARATOR, ChromeModel, MenuSpec
from StreamDock.ui.chrome.toast import Toast
from StreamDock.ui.chrome.window import (
    SHOW_MENUBAR_SHORTCUT,
    SHOW_MENUBAR_TEXT,
    GnomeChrome,
    KdeChrome,
    WindowChrome,
    make_chrome,
)

__all__ = [
    'ChromeModel',
    'GnomeChrome',
    'KdeChrome',
    'MenuSpec',
    'SEPARATOR',
    'SHOW_MENUBAR_SHORTCUT',
    'SHOW_MENUBAR_TEXT',
    'ThemedDialog',
    'Toast',
    'WindowChrome',
    'make_button',
    'make_chrome',
]
