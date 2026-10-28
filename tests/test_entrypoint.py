"""
Tests for the unified entry point.

The one guarantee worth pinning: --headless must not pull in Qt, so the
controller still runs on a machine with no display.
"""

import os
import subprocess
import sys
import tempfile

import pytest

from StreamDock.entrypoint import determine_config_path, parse_args, run_headless


class TestArguments:
    """parse_args()."""

    def test_gui_is_the_default(self):
        assert parse_args([]).headless is False

    def test_headless_flag(self):
        assert parse_args(['--headless']).headless is True

    def test_positional_config(self):
        assert parse_args(['/tmp/config.yml']).config == '/tmp/config.yml'

    def test_device_selection(self):
        assert parse_args(['--device', '6603:1006@x']).device == '6603:1006@x'

    def test_minimized_flag(self):
        assert parse_args(['--minimized']).minimized is True

    def test_the_design_follows_the_desktop_unless_forced(self):
        assert parse_args([]).design is None

    def test_the_design_can_be_forced_for_one_run(self):
        assert parse_args(['--design', 'gnome']).design == 'gnome'

    def test_an_unknown_design_is_refused(self):
        with pytest.raises(SystemExit):
            parse_args(['--design', 'aqua'])

    def test_mock_flag_is_gone(self):
        """It was a dead alias and MockDevice does not work."""
        with pytest.raises(SystemExit):
            parse_args(['--mock'])


class TestConfigResolution:
    """determine_config_path()."""

    def test_explicit_path_wins(self):
        assert determine_config_path('/tmp/x.yml', required=True) == '/tmp/x.yml'

    def test_finds_config_in_the_working_directory(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'config.yml')
            with open(path, 'w') as f:
                f.write("streamdock: {}\n")
            monkeypatch.chdir(tmpdir)

            assert determine_config_path(None, required=True) == path

    def test_headless_exits_when_nothing_is_found(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            determine_config_path(None, required=True)

    def test_gui_tolerates_no_configuration(self, monkeypatch, tmp_path):
        """The GUI opens with an empty document rather than refusing to start."""
        monkeypatch.chdir(tmp_path)
        assert determine_config_path(None, required=False) is None

    def test_gui_ignores_config_in_the_working_directory(self, monkeypatch, tmp_path):
        """A stray ./config.yml must not replace the remembered default in the GUI."""
        (tmp_path / 'config.yml').write_text("streamdock: {}\n")
        monkeypatch.chdir(tmp_path)

        found = determine_config_path(None, required=False, gui=True)

        assert found != str(tmp_path / 'config.yml')

    def test_gui_prefers_the_remembered_default(self, monkeypatch, tmp_path):
        (tmp_path / 'config.yml').write_text("streamdock: {}\n")
        monkeypatch.chdir(tmp_path)

        assert determine_config_path(None, required=False, gui=True,
                                     remembered='/home/u/deck.yml') == '/home/u/deck.yml'

    def test_gui_explicit_path_still_wins(self):
        assert determine_config_path('/tmp/x.yml', required=False, gui=True,
                                     remembered='/home/u/deck.yml') == '/tmp/x.yml'


NO_QT_PROBE = """
import sys
sys.path.insert(0, {src!r})

import builtins
real_import = builtins.__import__
def guard(name, *a, **k):
    if name.split('.')[0] == 'PyQt6':
        raise AssertionError('headless path imported ' + name)
    return real_import(name, *a, **k)
builtins.__import__ = guard

from StreamDock.entrypoint import main, run_headless
from StreamDock.application import Application
from StreamDock.application.instance_lock import InstanceLock
print('OK')
"""


def test_the_headless_path_imports_no_qt():
    """A machine with no display must still be able to run the controller."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')

    result = subprocess.run(
        [sys.executable, '-c', NO_QT_PROBE.format(src=src)],
        capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'


DEPENDENCY_PROBE = """
import sys
sys.path.insert(0, {src!r})
from StreamDock.dependency_check import DependencyChecker
checker = DependencyChecker()
checker.run_check()
checker.get_summary()
heavy = [name for name in ('PyQt6', 'cairosvg', 'gi', 'dbus', 'PIL', 'pyudev') if name in sys.modules]
print(','.join(heavy) or 'NONE')
"""


def test_the_dependency_check_imports_nothing():
    """It runs on every start; importing the packages it checks cost more than startup."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')

    result = subprocess.run(
        [sys.executable, '-c', DEPENDENCY_PROBE.format(src=src)],
        capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'NONE'


def test_headless_does_not_require_pyqt6():
    from StreamDock.dependency_check import DependencyChecker

    categories = {dep.name: dep.category
                  for dep in DependencyChecker(headless=True).python_packages_templates}

    assert categories['PyQt6'] == 'Optional'
    assert {dep.name: dep.category for dep in
            DependencyChecker().python_packages_templates}['PyQt6'] == 'Required'


def test_headless_retries_a_dock_that_would_not_open(monkeypatch):
    """No udev event follows a dock that failed to open; a timer has to try again."""
    import StreamDock.application as application_module
    import StreamDock.application.device_watcher as watcher_module
    import StreamDock.application.instance_lock as lock_module
    import StreamDock.entrypoint as entrypoint
    from unittest.mock import Mock

    device = Mock(vendor_id=0x6603, product_id=0x1006, serial_number='', path='/dev/hidraw0',
                  manufacturer='Test', product='StreamDock', device_id='d')
    watcher = Mock()
    watcher.devices = Mock(return_value=[device])
    monkeypatch.setattr(watcher_module, 'DeviceWatcher', Mock(return_value=watcher))
    lock = Mock()
    lock.acquire = Mock(return_value=True)
    monkeypatch.setattr(lock_module, 'InstanceLock', Mock(return_value=lock))

    attempts = []

    def make_app(*_args, **_kwargs):
        app = Mock()
        app.start = Mock(return_value=True)
        # Busy the first time, free the second.
        app.get_device = Mock(return_value=None if not attempts else Mock())
        app.get_device_info = Mock(return_value=device)
        attempts.append(app)
        return app

    monkeypatch.setattr(application_module, 'Application', make_app)
    monkeypatch.setattr(entrypoint, 'HEADLESS_RETRY_SECONDS', 0.01)

    def sleep(_seconds):
        if len(attempts) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(entrypoint.time, 'sleep', sleep)

    assert run_headless('/nonexistent.yml') == 0
    assert len(attempts) == 2
