"""
Unit tests for LinuxSystemInterface.

Window operations are verified through a mock WindowInterface (injected).
Non-window operations (key combos, volume, lock) patch subprocess/dbus directly.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call

from StreamDock.domain.Models import WindowInfo
from StreamDock.infrastructure.system_interface import SystemInterface
from StreamDock.infrastructure.window_interface import WindowInterface
from StreamDock.infrastructure.linux_system_interface import LinuxSystemInterface

LSI_MODULE = "StreamDock.infrastructure.linux_system_interface"


@pytest.fixture
def system_interface():
    return LinuxSystemInterface()


# ==================== Process Status ====================

class TestProcessStatus:
    
    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_is_process_running_true(self, mock_run, system_interface):
        mock_run.return_value = Mock(returncode=0, stdout="1234\n")
        assert system_interface.is_process_running("firefox") is True
        mock_run.assert_called_once_with(
            ["pgrep", "-x", "firefox"],
            capture_output=True, text=True, timeout=1,
        )

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_is_process_running_false_bad_returncode(self, mock_run, system_interface):
        mock_run.return_value = Mock(returncode=1, stdout="")
        assert system_interface.is_process_running("firefox") is False

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_is_process_running_false_empty_stdout(self, mock_run, system_interface):
        mock_run.return_value = Mock(returncode=0, stdout="\n  \n")
        assert system_interface.is_process_running("firefox") is False

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_is_process_running_exception(self, mock_run, system_interface):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(["pgrep"], 1)
        assert system_interface.is_process_running("firefox") is False


# ==================== Input Simulation ====================

class TestInputSimulation:

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_send_key_combo_success(self, mock_run, system_interface):
        """Design contract: send_key_combo calls xdotool key."""
        mock_run.return_value = Mock(returncode=0)

        result = system_interface.send_key_combo('ctrl+c')

        assert result is True
        mock_run.assert_called_once_with(
            ["xdotool", "key", "ctrl+c"],
            check=True, capture_output=True,
        )

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_send_key_combo_returns_false_on_failure(self, mock_run, system_interface):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "xdotool")
        assert system_interface.send_key_combo('ctrl+c') is False

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_send_key_combo_returns_false_when_xdotool_missing(self, mock_run, system_interface):
        mock_run.side_effect = FileNotFoundError
        assert system_interface.send_key_combo('ctrl+c') is False

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_type_text_success(self, mock_run, system_interface):
        mock_run.return_value = Mock(returncode=0)
        result = system_interface.type_text('Hello World')
        assert result is True
        mock_run.assert_called_once_with(
            ["xdotool", "type", "--clearmodifiers", "--delay", "1", "--", "Hello World"],
            check=True, capture_output=True,
        )

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_type_text_returns_false_on_failure(self, mock_run, system_interface):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "xdotool")
        assert system_interface.type_text('test') is False

    @patch(f"{LSI_MODULE}.subprocess.Popen")
    def test_execute_command_success(self, mock_popen, system_interface):
        """Design contract: Command execution uses subprocess.Popen (detached)."""
        result = system_interface.execute_command('echo test')

        assert result is True
        mock_popen.assert_called_once()
        assert mock_popen.call_args[0][0] == 'echo test'

    @patch(f"{LSI_MODULE}.subprocess.Popen")
    def test_execute_command_handles_exception(self, mock_popen, system_interface):
        mock_popen.side_effect = Exception("Command failed")
        assert system_interface.execute_command('invalid') is False


# ==================== Lock Monitoring ====================

class TestLockMonitoring:

    @patch('dbus.SessionBus')
    def test_poll_lock_state_kde_interface(self, mock_bus, system_interface):
        """Design contract: Poll lock state via D-Bus KDE interface."""
        mock_iface = Mock()
        mock_iface.GetActive.return_value = True
        mock_bus.return_value.get_object.return_value = Mock()

        with patch('dbus.Interface', return_value=mock_iface):
            result = system_interface.poll_lock_state()

        assert result is True
        mock_iface.GetActive.assert_called_once()

    @patch('dbus.SessionBus')
    def test_poll_lock_state_returns_false_on_error(self, mock_bus, system_interface):
        mock_bus.side_effect = Exception("D-Bus error")
        assert system_interface.poll_lock_state() is False

    @patch('dbus.SessionBus')
    def test_poll_lock_state_tries_gnome_fallback(self, mock_bus, system_interface):
        """Design contract: Falls back to GNOME interface if KDE fails."""
        import dbus

        gnome_proxy = Mock()

        def get_object_side_effect(bus_name, path):
            if 'freedesktop' in bus_name:
                raise dbus.DBusException("KDE not available")
            return gnome_proxy

        mock_bus.return_value.get_object.side_effect = get_object_side_effect
        gnome_iface = Mock()
        gnome_iface.GetActive.return_value = True

        with patch('dbus.Interface', return_value=gnome_iface):
            result = system_interface.poll_lock_state()

        assert result is True
        gnome_iface.GetActive.assert_called_once()

    def test_poll_lock_state_handles_import_error(self, system_interface):
        with patch.dict('sys.modules', {'dbus': None}):
            assert system_interface.poll_lock_state() is False

    @patch('dbus.SessionBus')
    def test_start_lock_monitor_starts_thread(self, mock_bus, system_interface):
        callback = Mock()
        result = system_interface.start_lock_monitor(callback)

        assert result is True
        assert system_interface._lock_monitor_thread is not None
        assert system_interface._lock_monitor_thread.is_alive()

        system_interface.stop_lock_monitor()

    @patch('dbus.SessionBus')
    def test_start_lock_monitor_fails_when_already_running(self, mock_bus, system_interface):
        callback = Mock()
        system_interface.start_lock_monitor(callback)
        assert system_interface.start_lock_monitor(callback) is False
        system_interface.stop_lock_monitor()

    def test_stop_lock_monitor_safe_when_not_running(self, system_interface):
        system_interface.stop_lock_monitor()  # must not raise
        assert system_interface._lock_monitor_thread is None


# ==================== Media Controls ====================

class TestMediaControls:

    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_send_media_key_maps_playpause(self, mock_run, system_interface):
        """Design contract: PlayPause maps to XF86AudioPlay."""
        mock_run.return_value = Mock(returncode=0)

        result = system_interface.send_media_key('PlayPause')

        assert result is True
        mock_run.assert_called_once_with(
            ["xdotool", "key", "XF86AudioPlay"],
            check=True, capture_output=True,
        )

    @patch(f"{LSI_MODULE}.shutil.which")
    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_set_volume_uses_pactl(self, mock_run, mock_which, system_interface):
        """Design contract: Volume control uses pactl."""
        mock_which.return_value = "/usr/bin/pactl"
        mock_run.return_value = Mock(returncode=0)

        result = system_interface.set_volume(75)

        assert result is True
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "pactl"
        assert "75%" in cmd

    @patch(f"{LSI_MODULE}.shutil.which")
    def test_set_volume_returns_false_when_pactl_unavailable(self, mock_which, system_interface):
        mock_which.return_value = None
        assert system_interface.set_volume(50) is False

    @patch(f"{LSI_MODULE}.shutil.which")
    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_set_volume_clamps_to_0_100(self, mock_run, mock_which, system_interface):
        mock_which.return_value = "/usr/bin/pactl"
        mock_run.return_value = Mock(returncode=0)

        system_interface.set_volume(150)
        assert "100%" in mock_run.call_args[0][0]

        system_interface.set_volume(-10)
        assert "0%" in mock_run.call_args[0][0]

    @patch(f"{LSI_MODULE}.shutil.which")
    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_set_volume_handles_pactl_failure(self, mock_run, mock_which, system_interface):
        mock_which.return_value = "/usr/bin/pactl"
        mock_run.return_value = Mock(returncode=1, stderr=b'error')
        assert system_interface.set_volume(50) is False

    @patch(f"{LSI_MODULE}.shutil.which")
    @patch(f"{LSI_MODULE}.subprocess.run")
    def test_set_volume_handles_exception(self, mock_run, mock_which, system_interface):
        mock_which.return_value = "/usr/bin/pactl"
        mock_run.side_effect = Exception("Pactl failed")
        assert system_interface.set_volume(50) is False


# ==================== Tool-availability methods removed ====================

class TestRemovedToolAvailabilityMethods:
    """
    Verify the tool-availability methods were removed from LinuxSystemInterface.
    These are implementation details; business logic must never depend on them.
    """

    def test_is_kdotool_available_removed(self, system_interface):
        assert not hasattr(system_interface, 'is_kdotool_available')

    def test_is_xdotool_available_removed(self, system_interface):
        assert not hasattr(system_interface, 'is_xdotool_available')

    def test_is_dbus_available_removed(self, system_interface):
        assert not hasattr(system_interface, 'is_dbus_available')

    def test_is_pactl_available_removed(self, system_interface):
        assert not hasattr(system_interface, 'is_pactl_available')
