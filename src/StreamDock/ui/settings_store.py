"""
Small persistent preferences, kept in QSettings.

Only the default configuration path lives here: which file the application
opens on startup, which the user chooses when they open a different one.
"""

import logging
import os
from typing import Optional

from PyQt6.QtCore import QSettings

logger = logging.getLogger(__name__)

ORGANISATION = "StreamDock"
APPLICATION = "StreamDock"
DEFAULT_CONFIG_KEY = "config/default_path"


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
