"""
Switching debug logging on and off while the application runs.

Every module logs through ``logging.getLogger(__name__)``, so the root logger's
level and its handlers' levels decide what all of them print. Widget processes
are separate Python interpreters: they read ``STREAMDOCK_DEBUG`` when they
start, so a widget started after the switch follows it.
"""

import logging
import os

DEBUG_ENV = 'STREAMDOCK_DEBUG'

# Libraries that drown the application's own messages at debug level.
_QUIET_LOGGERS = ('PIL.PngImagePlugin',)


def is_debug() -> bool:
    """Whether the root logger currently lets debug messages through."""
    return logging.getLogger().getEffectiveLevel() <= logging.DEBUG


def set_debug(enabled: bool) -> None:
    """
    Apply a debug or normal log level to every logger.

    Args:
        enabled: True for debug, False for info
    """
    level = logging.DEBUG if enabled else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    for handler in root.handlers:
        handler.setLevel(level)
    # A logger somebody gave its own level would ignore the root's.
    for name, candidate in list(logging.root.manager.loggerDict.items()):
        if isinstance(candidate, logging.Logger) and name not in _QUIET_LOGGERS:
            candidate.setLevel(logging.NOTSET)
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.INFO)

    if enabled:
        os.environ[DEBUG_ENV] = '1'
    else:
        os.environ.pop(DEBUG_ENV, None)
    logging.getLogger(__name__).info("Debug logging %s", "enabled" if enabled else "disabled")
