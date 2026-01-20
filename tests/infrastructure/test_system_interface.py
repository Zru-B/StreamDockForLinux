"""
Unit tests for SystemInterface and LinuxSystemInterface implementation.

Tests the wrapper around WindowUtils, verifying delegation, error handling,
and design contract compliance.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
import threading
import time

from StreamDock.infrastructure.system_interface import SystemInterface, WindowInfo
from StreamDock.infrastructure.linux_system_interface import LinuxSystemInterface


class TestLinuxSystemInterface:
    """Tests for LinuxSystemInterface implementation."""
    
    @pytest.fixture
    def system_interface(self):
        """LinuxSystemInterface instance."""
        return LinuxSystemInterface()
    
    # ==================== Tool Availability Tests ====================
    
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_kdotool_available_delegates_to_window_utils(self, mock_kdotool, system_interface):
        """Design contract: Tool availability delegated to WindowUtils."""
        mock_kdotool.return_value = True
        
        result = system_interface.is_kdotool_available()
        
        assert result is True
        mock_kdotool.assert_called_once()
    
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_xdotool_available_delegates_to_window_utils(self, mock_xdotool, system_interface):
        """Design contract: Tool availability delegated to WindowUtils."""
        mock_xdotool.return_value = True
        
        result = system_interface.is_xdotool_available()
        
        assert result is True
        mock_xdotool.assert_called_once()
    
    @patch('StreamDock.window_utils.WindowUtils.is_dbus_available')
    def test_dbus_available_delegates_to_window_utils(self, mock_dbus, system_interface):
        """Design contract: Tool availability delegated to WindowUtils."""
        mock_dbus.return_value = True
        
        result = system_interface.is_dbus_available()
        
        assert result is True
        mock_dbus.assert_called_once()
    
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_pactl_available_delegates_to_window_utils(self, mock_pactl, system_interface):
        """Design contract: Tool availability delegated to WindowUtils."""
        mock_pactl.return_value = True
        
        result = system_interface.is_pactl_available()
        
        assert result is True
        mock_pactl.assert_called_once()
    
    # ==================== Window Operation Tests ====================
    
    @patch('StreamDock.window_utils.WindowUtils.kdotool_get_active_window')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_get_active_window_tries_kdotool_first(self, mock_available, mock_get_window, system_interface):
        """Design contract: Try kdotool before xdotool."""
        mock_available.return_value = True
        mock_get_window.return_value = WindowInfo(title='Test', class_='firefox')
        
        window = system_interface.get_active_window()
        
        assert window.title == 'Test'
        assert window.class_ == 'firefox'
        mock_get_window.assert_called_once()
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_get_active_window')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.kdotool_get_active_window')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_get_active_window_falls_back_to_xdotool(self, mock_kdotool_avail, mock_kdotool_get,
                                                       mock_xdotool_avail, mock_xdotool_get, system_interface):
        """Design contract: Fallback to xdotool if kdotool not available."""
        mock_kdotool_avail.return_value = False
        mock_xdotool_avail.return_value = True
        mock_xdotool_get.return_value = WindowInfo(title='Fallback', class_='chrome')
        
        window = system_interface.get_active_window()
        
        assert window.title == 'Fallback'
        mock_xdotool_get.assert_called_once()
        mock_kdotool_get.assert_not_called()
    
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_get_active_window_returns_none_when_no_tools(self, mock_kdotool, mock_xdotool, system_interface):
        """Design contract: Returns None when no tools available."""
        mock_kdotool.return_value = False
        mock_xdotool.return_value = False
        
        window = system_interface.get_active_window()
        
        assert window is None
    
    @patch('StreamDock.window_utils.WindowUtils.kdotool_search_by_class')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_search_window_by_class_uses_kdotool(self, mock_available, mock_search, system_interface):
        """Design contract: Search uses available tool."""
        mock_available.return_value = True
        mock_search.return_value = '12345'
        
        window_id = system_interface.search_window_by_class('firefox')
        
        assert window_id == '12345'
        mock_search.assert_called_once_with('firefox')
    
    @patch('StreamDock.window_utils.WindowUtils.kdotool_activate_window')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_activate_window_success(self, mock_available, mock_activate, system_interface):
        """Design contract: Activate window using available tool."""
        mock_available.return_value = True
        mock_activate.return_value = True
        
        result = system_interface.activate_window('12345')
        
        assert result is True
        mock_activate.assert_called_once_with('12345')
    
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_activate_window_returns_false_when_no_tools(self, mock_kdotool, mock_xdotool, system_interface):
        """Error handling: Returns False when no tools available."""
        mock_kdotool.return_value = False
        mock_xdotool.return_value = False
        
        result = system_interface.activate_window('12345')
        
        assert result is False
    
    # ==================== Input Simulation Tests ====================
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_key')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_send_key_combo_delegates_to_xdotool(self, mock_available, mock_key, system_interface):
        """Design contract: Key combo uses xdotool."""
        mock_available.return_value = True
        mock_key.return_value = True
        
        result = system_interface.send_key_combo('ctrl+c')
        
        assert result is True
        mock_key.assert_called_once_with('ctrl+c')
    
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_send_key_combo_returns_false_when_no_xdotool(self, mock_available, system_interface):
        """Error handling: Returns False when xdotool not available."""
        mock_available.return_value = False
        
        result = system_interface.send_key_combo('ctrl+c')
        
        assert result is False
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_type')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_type_text_delegates_to_xdotool(self, mock_available, mock_type, system_interface):
        """Design contract: Text typing uses xdotool."""
        mock_available.return_value = True
        
        result = system_interface.type_text('Hello World')
        
        assert result is True
        mock_type.assert_called_once_with('Hello World')
    
    @patch('subprocess.Popen')
    def test_execute_command_success(self, mock_popen, system_interface):
        """Design contract: Command execution uses subprocess."""
        result = system_interface.execute_command('echo test')
        
        assert result is True
        mock_popen.assert_called_once()
        # Verify command was passed
        call_args = mock_popen.call_args
        assert call_args[0][0] == 'echo test'
    
    @patch('subprocess.Popen')
    def test_execute_command_handles_exception(self, mock_popen, system_interface):
        """Error handling: Returns False on exception."""
        mock_popen.side_effect = Exception("Command failed")
        
        result = system_interface.execute_command('invalid')
        
        assert result is False
    
    # ==================== Lock Monitoring Tests ====================
    
    @patch('dbus.SessionBus')
    def test_poll_lock_state_kde_interface(self, mock_bus, system_interface):
        """Design contract: Poll lock state via D-Bus KDE interface."""
        mock_iface = Mock()
        mock_iface.GetActive.return_value = True
        
        mock_proxy = Mock()
        mock_bus.return_value.get_object.return_value = mock_proxy
        
        with patch('dbus.Interface', return_value=mock_iface):
            result = system_interface.poll_lock_state()
        
        assert result is True
        mock_iface.GetActive.assert_called_once()
    
    @patch('dbus.SessionBus')
    def test_poll_lock_state_returns_false_on_error(self, mock_bus, system_interface):
        """Error handling: Returns False on D-Bus error."""
        mock_bus.side_effect = Exception("D-Bus error")
        
        result = system_interface.poll_lock_state()
        
        assert result is False
    
    @patch('dbus.SessionBus')
    def test_start_lock_monitor_starts_thread(self, mock_bus, system_interface):
        """Design contract: Start monitoring creates background thread."""
        callback = Mock()
        
        result = system_interface.start_lock_monitor(callback)
        
        assert result is True
        assert system_interface._lock_monitor_thread is not None
        assert system_interface._lock_monitor_thread.is_alive()
        
        # Cleanup
        system_interface.stop_lock_monitor()
    
    @patch('dbus.SessionBus')
    def test_start_lock_monitor_fails_when_already_running(self, mock_bus, system_interface):
        """Error handling: Returns False if monitor already running."""
        callback = Mock()
        system_interface.start_lock_monitor(callback)
        
        # Try to start again
        result = system_interface.start_lock_monitor(callback)
        
        assert result is False
        
        # Cleanup
        system_interface.stop_lock_monitor()
    
    def test_stop_lock_monitor_stops_thread(self, system_interface):
        """Design contract: Stop monitoring cleans up thread."""
        with patch('dbus.SessionBus'):
            callback = Mock()
            system_interface.start_lock_monitor(callback)
            
            system_interface.stop_lock_monitor()
        
        # Thread should be stopped
        assert system_interface._lock_monitor_thread is None or not system_interface._lock_monitor_thread.is_alive()
    
    def test_stop_lock_monitor_safe_when_not_running(self, system_interface):
        """Design contract: Safe to call stop when not running."""
        system_interface.stop_lock_monitor()  # Should not raise
        
        assert system_interface._lock_monitor_thread is None
    
    # ==================== Media Control Tests ====================
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_key')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_send_media_key_maps_to_x_key(self, mock_available, mock_key, system_interface):
        """Design contract: Media keys mapped to X key symbols."""
        mock_available.return_value = True
        mock_key.return_value = True
        
        result = system_interface.send_media_key('PlayPause')
        
        assert result is True
        mock_key.assert_called_once_with('XF86AudioPlay')
    
    @patch('subprocess.run')
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_set_volume_uses_pactl(self, mock_available, mock_run, system_interface):
        """Design contract: Volume control uses pactl."""
        mock_available.return_value = True
        mock_run.return_value = Mock(returncode=0)
        
        result = system_interface.set_volume(75)
        
        assert result is True
        mock_run.assert_called_once()
        # Verify pactl command
        call_args = mock_run.call_args
        assert 'pactl' in call_args[0][0]
        assert '75%' in call_args[0][0]
    
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_set_volume_returns_false_when_pactl_unavailable(self, mock_available, system_interface):
        """Error handling: Returns False when pactl not available."""
        mock_available.return_value = False
        
        result = system_interface.set_volume(50)
        
        assert result is False
    
    @patch('subprocess.run')
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_set_volume_clamps_to_0_100(self, mock_available, mock_run, system_interface):
        """Design contract: Volume clamped to valid range."""
        mock_available.return_value = True
        mock_run.return_value = Mock(returncode=0)
        
        # Test upper bound
        system_interface.set_volume(150)
        call_args = mock_run.call_args[0][0]
        assert '100%' in call_args
        
        # Test lower bound
        system_interface.set_volume(-10)
        call_args = mock_run.call_args[0][0]
        assert '0%' in call_args
    
    # ==================== Additional Error Handling Tests ====================
    
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_kdotool_available_handles_exception(self, mock_kdotool, system_interface):
        """Error handling: Returns False on exception."""
        mock_kdotool.side_effect = Exception("Tool check failed")
        
        result = system_interface.is_kdotool_available()
        
        assert result is False
    
    @patch('StreamDock.window_utils.WindowUtils.kdotool_get_active_window')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_get_active_window_handles_exception(self, mock_available, mock_get, system_interface):
        """Error handling: Returns None on exception."""
        mock_available.return_value = True
        mock_get.side_effect = Exception("Window detection failed")
        
        window = system_interface.get_active_window()
        
        assert window is None
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_search_by_class')
    @patch('StreamDock.window_utils.WindowUtils.kdotool_search_by_class')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_search_window_by_class_tries_xdotool_fallback(self, mock_kdotool_avail, mock_xdotool_avail,
                                                             mock_kdotool_search, mock_xdotool_search, system_interface):
        """Design contract: Falls back to xdotool if kdotool fails."""
        mock_kdotool_avail.return_value = True
        mock_xdotool_avail.return_value = True
        mock_kdotool_search.return_value = None  # kdotool didn't find it
        mock_xdotool_search.return_value = '99999'  # xdotool found it
        
        window_id = system_interface.search_window_by_class('firefox')
        
        assert window_id == '99999'
        mock_xdotool_search.assert_called_once()
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_activate_window')
    @patch('StreamDock.window_utils.WindowUtils.kdotool_activate_window')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    @patch('StreamDock.window_utils.WindowUtils.is_kdotool_available')
    def test_activate_window_tries_xdotool_fallback(self, mock_kdotool_avail, mock_xdotool_avail,
                                                      mock_kdotool_activate, mock_xdotool_activate, system_interface):
        """Design contract: Falls back to xdotool if kdotool not available."""
        mock_kdotool_avail.return_value = False
        mock_xdotool_avail.return_value = True
        mock_xdotool_activate.return_value = True
        
        result = system_interface.activate_window('12345')
        
        assert result is True
        mock_xdotool_activate.assert_called_once_with('12345')
        mock_kdotool_activate.assert_not_called()
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_key')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_send_key_combo_handles_exception(self, mock_available, mock_key, system_interface):
        """Error handling: Returns False on exception."""
        mock_available.return_value = True
        mock_key.side_effect = Exception("Key send failed")
        
        result = system_interface.send_key_combo('ctrl+c')
        
        assert result is False
    
    @patch('StreamDock.window_utils.WindowUtils.xdotool_type')
    @patch('StreamDock.window_utils.WindowUtils.is_xdotool_available')
    def test_type_text_handles_exception(self, mock_available, mock_type, system_interface):
        """Error handling: Returns False on exception."""
        mock_available.return_value = True
        mock_type.side_effect = Exception("Type failed")
        
        result = system_interface.type_text('test')
        
        assert result is False
    
    @patch('dbus.SessionBus')
    def test_poll_lock_state_tries_gnome_fallback(self, mock_bus, system_interface):
        """Design contract: Falls back to GNOME interface if KDE fails."""
        import dbus
        
        # Mock KDE interface to fail
        kde_proxy = Mock()
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
        """Error handling: Returns False when dbus not available."""
        with patch.dict('sys.modules', {'dbus': None}):
            result = system_interface.poll_lock_state()
        
        assert result is False
    
    @patch('subprocess.run')
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_set_volume_handles_pactl_failure(self, mock_available, mock_run, system_interface):
        """Error handling: Returns False when pactl command fails."""
        mock_available.return_value = True
        mock_run.return_value = Mock(returncode=1, stderr=b'error')
        
        result = system_interface.set_volume(50)
        
        assert result is False
    
    @patch('subprocess.run')
    @patch('StreamDock.window_utils.WindowUtils.is_pactl_available')
    def test_set_volume_handles_exception(self, mock_available, mock_run, system_interface):
        """Error handling: Returns False on exception."""
        mock_available.return_value = True
        mock_run.side_effect = Exception("Pactl failed")
        
        result = system_interface.set_volume(50)
        
        assert result is False
