"""
SingleInstanceGuard: the socket must be private to the user.
"""

import os

from PyQt6.QtCore import QCoreApplication

from StreamDock.ui.single_instance import SingleInstanceGuard, socket_path


class TestSocketPlacement:
    """A bare name lands in /tmp, shared by every user on the machine."""

    def test_the_socket_lives_in_the_runtime_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

        assert socket_path("guard") == str(tmp_path / "guard")

    def test_without_a_runtime_dir_the_name_is_per_user(self, monkeypatch):
        monkeypatch.setenv("XDG_RUNTIME_DIR", "/nonexistent-runtime-dir")
        monkeypatch.setattr(
            "StreamDock.ui.single_instance.QStandardPaths.writableLocation",
            lambda _location: "")

        assert socket_path("guard") == f"guard-{os.getuid()}"


class TestGuard:
    """One primary; a second instance defers to it."""

    def test_a_second_guard_finds_the_first(self, qtbot, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        first, second = SingleInstanceGuard("guard"), SingleInstanceGuard("guard")
        try:
            assert first.try_acquire() is True
            assert (tmp_path / "guard").exists()
            assert second.try_acquire() is False
        finally:
            first.close()
            second.close()
        QCoreApplication.processEvents()
