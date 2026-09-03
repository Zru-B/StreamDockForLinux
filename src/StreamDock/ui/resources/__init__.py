"""Bundled UI assets."""

from pathlib import Path

from PyQt6.QtGui import QIcon

ICON_NAME = "streamdock"


def load_app_icon() -> QIcon:
    """
    The window and tray icon.

    Returns:
        The themed icon when one is installed (so a desktop theme can
        override it), otherwise the bundled SVG, otherwise an empty QIcon -
        a missing icon must never stop the application from starting.
    """
    themed = QIcon.fromTheme(ICON_NAME)
    if not themed.isNull():
        return themed

    bundled = Path(__file__).with_name(f"{ICON_NAME}.svg")
    return QIcon(str(bundled)) if bundled.exists() else QIcon()
