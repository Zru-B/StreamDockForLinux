"""
The GUI's sys.excepthook: an exception in a slot is reported, not fatal.
"""

import sys
from unittest.mock import patch

import pytest

from StreamDock.ui import app as gui_app


@pytest.fixture
def restore_hook():
    original = sys.excepthook
    yield
    sys.excepthook = original


def raise_and_hook(exc):
    try:
        raise exc
    except BaseException:  # pylint: disable=broad-exception-caught
        sys.excepthook(*sys.exc_info())


class TestExceptionHook:
    """PyQt6 aborts the process on an unhandled slot exception with the default hook."""

    def test_an_exception_is_logged_and_shown_once(self, qtbot, restore_hook, caplog):
        gui_app.install_exception_hook()

        with patch.object(gui_app, 'QMessageBox') as box_cls:
            raise_and_hook(ValueError("boom"))
            raise_and_hook(ValueError("again"))

        assert "Unhandled exception" in caplog.text
        box_cls.return_value.show.assert_called_once()
        box_cls.return_value.exec.assert_not_called()

    def test_keyboard_interrupt_keeps_the_default_behaviour(self, qtbot, restore_hook):
        gui_app.install_exception_hook()

        with patch.object(gui_app, 'QMessageBox') as box_cls, \
                patch.object(sys, '__excepthook__') as default:
            raise_and_hook(KeyboardInterrupt())

        default.assert_called_once()
        box_cls.assert_not_called()
