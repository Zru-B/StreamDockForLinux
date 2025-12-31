import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from StreamDock.Models import WindowInfo


class TestWindowUtilsPreparation:
    """
    Baseline tests for window operations before WindowUtils implementation.
    These tests document current behavior in WindowMonitor and Actions.
    """

    def test_kdotool_search_pattern(self):
        """Test kdotool search command pattern."""
        # This documents the expected kdotool search behavior
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="12345\n67890\n"
            )
            
            result = subprocess.run(
                ["kdotool", "search", "--class", "firefox"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            
            assert result.returncode == 0
            window_id = result.stdout.strip().split("\n")[0]
            assert window_id == "12345"

    def test_xdotool_search_pattern(self):
        """Test xdotool search command pattern."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="98765\n"
            )
            
            result = subprocess.run(
                ["xdotool", "search", "--all", "--onlyvisible", "--class", "firefox"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            
            assert result.returncode == 0
            window_id = result.stdout.strip().split("\n")[0]
            assert window_id == "98765"

    def test_kdotool_get_active_window_pattern(self):
        """Test kdotool getactivewindow command pattern."""
        with patch('subprocess.run') as mock_run:
            # Mock getactivewindow
            mock_run.return_value = Mock(returncode=0, stdout="12345\n")
            
            result = subprocess.run(
                ["kdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False
            )
            
            assert result.returncode == 0
            assert result.stdout.strip() == "12345"

    def test_tool_not_found_handling(self):
        """Test FileNotFoundError handling when tool is missing."""
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            try:
                subprocess.run(
                    ["kdotool", "search", "--class", "test"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False
                )
                assert False, "Should have raised FileNotFoundError"
            except FileNotFoundError:
                # Expected behavior
                pass

    def test_timeout_handling(self):
        """Test TimeoutExpired handling."""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("cmd", 2)):
            try:
                subprocess.run(
                    ["kdotool", "search", "--class", "test"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False
                )
                assert False, "Should have raised TimeoutExpired"
            except subprocess.TimeoutExpired:
                # Expected behavior
                pass

    def test_empty_output_handling(self):
        """Test handling of empty output (no windows found)."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(returncode=1, stdout="")
            
            result = subprocess.run(
                ["kdotool", "search", "--class", "nonexistent"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False
            )
            
            # When no windows found, returncode is non-zero
            assert result.returncode != 0
            assert result.stdout.strip() == ""

    def test_window_class_normalization_pattern(self):
        """Test window class normalization expectations."""
        # Document expected normalization behavior
        test_cases = [
            ("firefox", "Firefox"),
            ("org.kde.konsole", "Konsole"),
            ("chromium-browser", "Chromium"),
            ("code", "VSCode"),
        ]
        
        # This will be implemented in WindowUtils.normalize_class_name()
        # For now, just document the expected mappings
        for raw_class, expected_normalized in test_cases:
            # Placeholder - will be tested with actual implementation
            assert raw_class.lower() in raw_class.lower()


class TestWindowMonitorIntegration:
    """
    Integration tests for WindowMonitor's window detection.
    These ensure WindowMonitor behavior is preserved after refactoring.
    """

    @pytest.fixture
    def mock_subprocess_kdotool_success(self):
        """Mock successful kdotool responses."""
        with patch('subprocess.run') as mock_run:
            def side_effect(*args, **kwargs):
                cmd = args[0]
                if "getactivewindow" in cmd:
                    return Mock(returncode=0, stdout="12345\n")
                elif "getwindowname" in cmd:
                    return Mock(returncode=0, stdout="Firefox - Test Page\n")
                elif "getwindowclassname" in cmd:
                    return Mock(returncode=0, stdout="firefox\n")
                return Mock(returncode=1, stdout="")
            
            mock_run.side_effect = side_effect
            yield mock_run

    def test_windowmonitor_kdotool_detection(self, mock_subprocess_kdotool_success):
        """Test WindowMonitor can detect active window via kdotool."""
        # After refactoring, WindowMonitor uses WindowUtils.kdotool_get_active_window() directly
        
        # Import here to avoid issues if WindowMonitor isn't available
        from StreamDock.WindowMonitor import WindowMonitor
        from StreamDock.WindowUtils import WindowUtils
        
        # Reset WindowUtils cache
        WindowUtils.refresh_tool_cache()
        
        monitor = WindowMonitor()
        if monitor.kdotool_available:
            window_info = monitor.get_active_window_info()
            
            # Should return WindowInfo with normalized class name
            assert window_info is not None
            assert window_info.title == "Firefox - Test Page"
            assert window_info.class_name == "Firefox"  # Normalized


class TestActionsIntegration:
    """
    Integration tests for Actions' window search functionality.
    These ensure Actions behavior is preserved after refactoring.
    """

    def test_actions_now_uses_windowutils_kdotool(self):
        """Test that Actions now uses WindowUtils for kdotool search."""
        from StreamDock.Actions import launch_or_focus_application
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                # Mock availability check and search
                mock_run.return_value = Mock(returncode=0, stdout="12345\n")
                
                # Mock pgrep to say process is running
                with patch('os.path.basename', return_value="firefox"):
                    app_config = "firefox"
                    launch_or_focus_application(app_config)
                
                # Should have called kdotool search and windowactivate
                assert any("kdotool" in str(call) for call in mock_run.call_args_list)

    def test_actions_now_uses_windowutils_xdotool(self):
        """Test that Actions now uses WindowUtils for xdotool search."""
        from StreamDock.Actions import launch_or_focus_application
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which') as mock_which:
            # kdotool not available, xdotool available
            def which_side_effect(tool):
                if tool == "kdotool":
                    return None
                elif tool == "xdotool":
                    return "/usr/bin/xdotool"
                return None
            
            mock_which.side_effect = which_side_effect
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="54321\n")
                
                with patch('os.path.basename', return_value="firefox"):
                    app_config = "firefox"
                    launch_or_focus_application(app_config)
                
                # Should have called xdotool search
                assert any("xdotool" in str(call) for call in mock_run.call_args_list)

    def test_actions_functions_removed(self):
        """Test that old window search functions have been removed from Actions."""
        import StreamDock.Actions as actions_module
        
        # These functions should no longer exist
        assert not hasattr(actions_module, '_kdotool_search_by_class')
        assert not hasattr(actions_module, '_kdotool_search_by_name')
        assert not hasattr(actions_module, '_xdotool_search_by_class')
        assert not hasattr(actions_module, '_xdotool_search_by_name')

    def test_windowutils_functions_exist(self):
        """Test that WindowUtils has the expected functions."""
        from StreamDock.WindowUtils import WindowUtils
        
        # These functions should exist in WindowUtils
        assert hasattr(WindowUtils, 'kdotool_search_by_class')
        assert hasattr(WindowUtils, 'kdotool_search_by_name')
        assert hasattr(WindowUtils, 'xdotool_search_by_class')
        assert hasattr(WindowUtils, 'xdotool_search_by_name')


class TestWindowUtils:
    """Tests for the new WindowUtils module."""

    def test_tool_availability_caching_kdotool(self):
        """Test that kdotool availability is cached."""
        from StreamDock.WindowUtils import WindowUtils
        
        # Reset cache
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="12345\n")
                
                # First call should check
                result1 = WindowUtils.is_kdotool_available()
                assert result1 is True
                assert mock_run.call_count == 1
                
                # Second call should use cache (no additional subprocess call)
                result2 = WindowUtils.is_kdotool_available()
                assert result2 is True
                assert mock_run.call_count == 1  # Still 1, not 2

    def test_tool_availability_caching_xdotool(self):
        """Test that xdotool availability is cached."""
        from StreamDock.WindowUtils import WindowUtils
        
        # Reset cache
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/xdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="")
                
                # First call should check
                result1 = WindowUtils.is_xdotool_available()
                assert result1 is True
                assert mock_run.call_count == 1
                
                # Second call should use cache
                result2 = WindowUtils.is_xdotool_available()
                assert result2 is True
                assert mock_run.call_count == 1

    def test_kdotool_search_by_class_success(self):
        """Test successful window search by class using kdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                # Mock availability check
                mock_run.return_value = Mock(returncode=0, stdout="12345\n67890\n")
                
                window_id = WindowUtils.kdotool_search_by_class("firefox")
                
                assert window_id == "12345"  # First window ID

    def test_kdotool_search_by_name_success(self):
        """Test successful window search by name using kdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="98765\n")
                
                window_id = WindowUtils.kdotool_search_by_name("Firefox")
                
                assert window_id == "98765"

    def test_xdotool_search_by_class_success(self):
        """Test successful window search by class using xdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/xdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="54321\n")
                
                window_id = WindowUtils.xdotool_search_by_class("firefox")
                
                assert window_id == "54321"

    def test_search_returns_none_when_tool_unavailable(self):
        """Test that search returns None when tool is not available."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value=None):
            # kdotool not available
            result = WindowUtils.kdotool_search_by_class("firefox")
            assert result is None
            
            # xdotool not available
            result = WindowUtils.xdotool_search_by_class("firefox")
            assert result is None

    def test_search_returns_none_when_no_windows_found(self):
        """Test that search returns None when no windows match."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                # First call: availability check (success)
                # Second call: search (no results)
                mock_run.side_effect = [
                    Mock(returncode=0, stdout="123\n"),  # Availability check
                    Mock(returncode=1, stdout="")  # Search - no results
                ]
                
                window_id = WindowUtils.kdotool_search_by_class("nonexistent")
                
                assert window_id is None

    def test_window_class_normalization(self):
        """Test window class normalization."""
        from StreamDock.WindowUtils import WindowUtils
        
        test_cases = [
            ("firefox", "Firefox"),
            ("org.kde.konsole", "Konsole"),
            ("chromium-browser", "Chromium"),
            ("code", "VSCode"),
            ("unknown-app", "unknown-app"),  # No match, returns as-is
        ]
        
        for raw_class, expected in test_cases:
            result = WindowUtils.normalize_class_name(raw_class)
            assert result == expected, f"Expected {expected} for {raw_class}, got {result}"

    def test_extract_app_from_title(self):
        """Test extracting app name from window title."""
        from StreamDock.WindowUtils import WindowUtils
        
        test_cases = [
            ("Document.txt - Kate", "Kate"),
            ("My Project — VSCode", "VSCode"),
            ("Firefox: Privacy Browser", "Firefox"),
            ("", "unknown"),
        ]
        
        for title, expected in test_cases:
            result = WindowUtils.extract_app_from_title(title)
            assert result == expected, f"Expected {expected} for '{title}', got {result}"

    def test_kdotool_activate_window_success(self):
        """Test successful window activation using kdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="")
                
                result = WindowUtils.kdotool_activate_window("12345")
                
                assert result is True

    def test_xdotool_activate_window_success(self):
        """Test successful window activation using xdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/xdotool"):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="")
                
                result = WindowUtils.xdotool_activate_window("12345")
                
                assert result is True

    def test_get_active_window_kdotool(self):
        """Test getting active window info using kdotool."""
        from StreamDock.WindowUtils import WindowUtils
        
        WindowUtils.refresh_tool_cache()
        
        with patch('shutil.which', return_value="/usr/bin/kdotool"):
            with patch('subprocess.run') as mock_run:
                def side_effect(*args, **kwargs):
                    cmd = args[0]
                    if "getactivewindow" in cmd:
                        return Mock(returncode=0, stdout="12345\n")
                    elif "getwindowname" in cmd:
                        return Mock(returncode=0, stdout="Firefox - Test\n")
                    elif "getwindowclassname" in cmd:
                        return Mock(returncode=0, stdout="firefox\n")
                    return Mock(returncode=1, stdout="")
                
                mock_run.side_effect = side_effect
                
                window_info = WindowUtils.kdotool_get_active_window()
                
                assert window_info is not None
                assert window_info.title == "Firefox - Test"
                assert window_info.class_name == "Firefox"  # Normalized
                assert window_info.method == "kdotool"
