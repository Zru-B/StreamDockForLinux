"""
Shared setup for the GUI tests.

pytest-qt closes every registered widget when a test ends, which re-enters
MainWindow.closeEvent. A window left with unsaved changes would then open the
real unsaved-changes dialog and block forever, since nothing is there to click
it. Stub the prompt for the whole package: no UI test wants a blocking modal.
"""

import pytest
from PyQt6.QtWidgets import QMessageBox

from StreamDock.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def discard_unsaved_changes(monkeypatch):
    """Answer the unsaved-changes prompt with Discard unless a test overrides it."""
    monkeypatch.setattr(
        MainWindow, 'ask_about_unsaved_changes',
        lambda self: QMessageBox.StandardButton.Discard)
