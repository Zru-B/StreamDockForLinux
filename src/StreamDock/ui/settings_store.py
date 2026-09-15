"""
Small persistent preferences, kept in QSettings.

Three things live here: which configuration file the application opens on
startup, how the user wants it to look when the session's own answer is not
the one they want, and whether they asked for the menu bar back.
"""

import logging
import os
from typing import Optional

from PyQt6.QtCore import QSettings

logger = logging.getLogger(__name__)

ORGANISATION = "StreamDock"
APPLICATION = "StreamDock"
DEFAULT_CONFIG_KEY = "config/default_path"
DESIGN_KEY = "appearance/design"
SCHEME_KEY = "appearance/scheme"
MENUBAR_KEY = "chrome/menubar_visible"

AUTO = "auto"
DESIGNS = ("auto", "kde", "gnome")
SCHEMES = ("auto", "light", "dark")


def _settings() -> QSettings:
    return QSettings(ORGANISATION, APPLICATION)


def get_default_config_path() -> Optional[str]:
    """
    The configuration opened at startup.

    Returns:
        The stored path if it still exists, otherwise None - a default
        pointing at a deleted file should not block startup.
    """
    stored = _settings().value(DEFAULT_CONFIG_KEY, type=str)
    if stored and os.path.exists(stored):
        return stored
    if stored:
        logger.info("Default configuration %s no longer exists", stored)
    return None


def set_default_config_path(path: str) -> None:
    """
    Remember a configuration as the startup default.

    Args:
        path: Configuration file to open on startup
    """
    _settings().setValue(DEFAULT_CONFIG_KEY, os.path.abspath(path))


def clear_default_config_path() -> None:
    """Forget the startup default."""
    _settings().remove(DEFAULT_CONFIG_KEY)


def get_design() -> str:
    """
    The interface design to wear.

    Returns:
        'auto' to follow the running desktop, or 'kde' / 'gnome'
    """
    return _one_of(_settings().value(DESIGN_KEY, type=str), DESIGNS)


def set_design(design: str) -> None:
    """
    Remember which interface design to wear.

    Args:
        design: 'auto', 'kde' or 'gnome'
    """
    _settings().setValue(DESIGN_KEY, _one_of(design, DESIGNS))


def get_scheme() -> str:
    """
    Whether to paint light or dark.

    Returns:
        'auto' to follow the running desktop, or 'light' / 'dark'
    """
    return _one_of(_settings().value(SCHEME_KEY, type=str), SCHEMES)


def set_scheme(scheme: str) -> None:
    """
    Remember whether to paint light or dark.

    Args:
        scheme: 'auto', 'light' or 'dark'
    """
    _settings().setValue(SCHEME_KEY, _one_of(scheme, SCHEMES))


def _one_of(value: Optional[str], allowed: tuple) -> str:
    """
    Keep a stored preference inside the set the application understands.

    A settings file is a text file a user can edit, and an unknown value must
    not decide what the window looks like.

    Args:
        value: The stored or offered value
        allowed: Values the application accepts, the first being the default

    Returns:
        The value, or the default
    """
    return value if value in allowed else allowed[0]


def get_menubar_visible() -> bool:
    """
    Whether the Plasma design should show its menu bar.

    Hidden by default, as in every Plasma 6 application; Ctrl+M brings it
    back and the choice is kept here.

    Returns:
        True when the menu bar should be showing
    """
    return bool(_settings().value(MENUBAR_KEY, False, type=bool))


def set_menubar_visible(visible: bool) -> None:
    """
    Remember whether the menu bar should be showing.

    Args:
        visible: True to show it
    """
    _settings().setValue(MENUBAR_KEY, bool(visible))
