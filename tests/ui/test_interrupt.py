"""
Ctrl+C in the terminal quits the GUI, which Python alone can't do while Qt waits.
"""

import os
import signal
from unittest.mock import Mock

import pytest

from StreamDock.ui import app as gui_app


@pytest.fixture
def restore_sigint():
    original = signal.getsignal(signal.SIGINT)
    yield
    signal.signal(signal.SIGINT, original)


class TestQuitOnInterrupt:

    def test_ctrl_c_requests_a_quit(self, qtbot, restore_sigint):
        request_quit = Mock()
        timer = gui_app.quit_on_interrupt(request_quit)

        os.kill(os.getpid(), signal.SIGINT)
        # Only the timer gives Python a turn inside the event loop.
        qtbot.waitUntil(lambda: request_quit.called, timeout=2000)

        request_quit.assert_called_once()
        assert timer.isActive()

    def test_a_second_ctrl_c_is_left_to_the_default(self, qtbot, restore_sigint):
        request_quit = Mock()
        gui_app.quit_on_interrupt(request_quit)

        os.kill(os.getpid(), signal.SIGINT)
        qtbot.waitUntil(lambda: request_quit.called, timeout=2000)

        assert signal.getsignal(signal.SIGINT) is signal.SIG_DFL
