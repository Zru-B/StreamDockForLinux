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

from StreamDock.entrypoint import determine_config_path, parse_args


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
