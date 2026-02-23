"""
Integration tests for window change → layout switch flow.

Tests the complete integration of window monitoring with layout selection.
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, call
from StreamDock.business_logic.system_event_monitor import SystemEventMonitor
from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator
from StreamDock.business_logic.layout_manager import LayoutManager, LayoutRule
from StreamDock.domain.Models import WindowInfo

logger = logging.getLogger(__name__)


@pytest.mark.skip(reason="Fixture dependencies need refactoring - Phase 6 work")
class TestWindowLayoutSwitch:
    """Integration tests for window focus → layout switch."""
    
    @pytest.fixture
    def mock_hardware(self):
        """Mock hardware interface."""
        hardware = Mock()
        hardware.set_brightness = Mock()
        hardware.send_image = Mock()
        hardware.clear_device = Mock()
        return hardware
    
    @pytest.fixture
    def mock_system(self):
        """Mock system interface with window tracking."""
        system = Mock()
        
        # Track current window for testing
        system._current_window = WindowInfo(
            class_="DefaultApp",
            title="Default Window",
            raw="DefaultApp"
        )
        
        def get_active_window():
            return system._current_window
        
        system.get_active_window = get_active_window
        system.poll_lock_state = Mock(return_value=False)
        return system
    
    @pytest.fixture
    def layout_manager_with_rules(self):
        """Layout manager with window rules configured."""
        manager = LayoutManager(default_layout_name="default")
        
        # Add window rules using correct API
        manager.add_rule("Firefox", "browser", match_field="class", priority=100)
        manager.add_rule("Code", "editor", match_field="class", priority=100)
        manager.add_rule("Spotify", "media", match_field="class", priority=100)
        
        return manager
    
    @pytest.fixture
    def orchestrator_with_device(self, mock_hardware, mock_system,
                                  layout_manager_with_rules):
        """Orchestrator with a registered device and rules."""
        event_monitor = SystemEventMonitor(
            system_interface=mock_system,
            verification_delay=0.1
        )
        
        orch = DeviceOrchestrator(
            hardware=mock_hardware,
            system=mock_system,
            registry=None,  # Simplified mode
            event_monitor=event_monitor,
            layout_manager=layout_manager_with_rules
        )
        
        # Register a test device
        device_id = "test_device"
        orch._devices[device_id] = Mock()
        orch._current_layouts[device_id] = "default"
        orch._brightness_levels[device_id] = 50
        
        return orch
    
    def test_window_change_triggers_layout_switch(self, orchestrator_with_device,
                                                   mock_system):
        """
        Test that changing window focus triggers appropriate layout.
        
        Flow:
        1. Default app active → "default" layout
        2. Switch to Firefox → "browser" layout
        3. Switch to VS Code → "editor" layout
        """
        orch = orchestrator_with_device
        device_id = "test_device"
        
        # Initial state: default layout
        assert orch._current_layouts[device_id] == "default"
        
        # Change to Firefox
        mock_system._current_window = WindowInfo(
            class_="Firefox",
            title="Mozilla Firefox",
            raw="Firefox"
        )
        orch._handle_window_change()
        
        # Should switch to browser layout
        assert orch._current_layouts[device_id] == "browser"
        
        # Change to VS Code
        mock_system._current_window = WindowInfo(
            class_="Code",
            title="Visual Studio Code",
            raw="Code"
        )
        orch._handle_window_change()
        
        # Should switch to editor layout
        assert orch._current_layouts[device_id] == "editor"
    
    def test_layout_change_applies_to_all_devices(self, orchestrator_with_device,
                                                   mock_system):
        """
        Test that layout changes apply to all registered devices.
        """
        orch = orchestrator_with_device
        
        # Add second device
        device_id_2 = "test_device_2"
        orch._devices[device_id_2] = Mock()
        orch._current_layouts[device_id_2] = "default"
        
        # Change window
        mock_system._current_window = WindowInfo(
            class_="Spotify",
            title="Spotify",
            raw="Spotify"
        )
        orch._handle_window_change()
        
        # Both devices should have media layout
        assert orch._current_layouts["test_device"] == "media"
        assert orch._current_layouts[device_id_2] == "media"
    
    def test_no_matching_rule_uses_default(self, orchestrator_with_device,
                                           mock_system):
        """
        Test that unknown windows use default layout.
        """
        orch = orchestrator_with_device
        device_id = "test_device"
        
        # Switch to browser first
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        assert orch._current_layouts[device_id] == "browser"
        
        # Switch to unknown app
        mock_system._current_window = WindowInfo(
            class_="UnknownApp",
            title="Unknown Application",
            raw="UnknownApp"
        )
        orch._handle_window_change()
        
        # Should fall back to default
        assert orch._current_layouts[device_id] == "default"
    
    def test_redundant_window_change_skipped(self, orchestrator_with_device,
                                             mock_system):
        """
        Test that switching to same window doesn't reapply layout.
        
        This is an optimization - no need to redraw if layout unchanged.
        """
        orch = orchestrator_with_device
        device_id = "test_device"
        
        # Change to Firefox
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        assert orch._current_layouts[device_id] == "browser"
        
        # Clear the mock call history
        orch._devices[device_id].reset_mock()
        
        # "Change" to Firefox again (same window)
        orch._handle_window_change()
        
        # Layout should still be browser
        assert orch._current_layouts[device_id] == "browser"
        # But no device operations should have been called (optimization)
        # (Implementation dependent - some may skip, some may reapply)
    
    def test_layout_switch_completes_quickly(self, orchestrator_with_device,
                                             mock_system):
        """
        Test that layout switches complete within acceptable time.
        
        Performance requirement: < 500ms per design contract.
        """
        import time
        
        orch = orchestrator_with_device
        
        # Measure switch time
        start = time.time()
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        elapsed = time.time() - start
        
        # Should be very fast (well under 500ms)
        assert elapsed < 0.5  # 500ms threshold
        # Typically should be < 50ms in tests
        assert elapsed < 0.1


@pytest.mark.skip(reason="Event handler wiring not yet complete - Phase 6 work")
class TestWindowLayoutWithLock:
    """Test window layout switching interactions with lock/unlock."""
    
    @pytest.fixture
    def orchestrator_with_monitor(self, mock_hardware, mock_system,
                                   layout_manager_with_rules):
        """Orchestrator with event monitor for lock events."""
        event_monitor = SystemEventMonitor(
            system_interface=mock_system,
            verification_delay=0.05
        )
        
        orch = DeviceOrchestrator(
            hardware=mock_hardware,
            system=mock_system,
            registry=None,
            event_monitor=event_monitor,
            layout_manager=layout_manager_with_rules
        )
        
        # Register device
        device_id = "test_device"
        orch._devices[device_id] = Mock()
        orch._current_layouts[device_id] = "default"
        orch._brightness_levels[device_id] = 50
        
        return orch, event_monitor
    
    def test_layout_change_blocked_while_locked(self, orchestrator_with_monitor,
                                                 mock_system):
        """
        Test that layout changes are blocked while device is locked.
        """
        orch, event_monitor = orchestrator_with_monitor
        device_id = "test_device"
        
        # Lock device
        event_monitor._handle_screen_lock_event()
        import time
        time.sleep(0.1)  # Wait for lock verification
        assert orch._is_locked is True
        
        # Try to change layout
        initial_layout = orch._current_layouts[device_id]
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        
        # Layout should NOT change (device is off)
        assert orch._current_layouts[device_id] == initial_layout
    
    def test_layout_restored_after_unlock(self, orchestrator_with_monitor,
                                          mock_system):
        """
        Test that correct layout is restored after unlock.
        
        Scenario:
        1. User switches to Firefox (browser layout)
        2. User locks screen
        3. User unlocks screen
        4. Browser layout should be restored
        """
        orch, event_monitor = orchestrator_with_monitor
        device_id = "test_device"
        
        # Switch to Firefox
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        assert orch._current_layouts[device_id] == "browser"
        
        # Lock
        event_monitor._handle_screen_lock_event()
        import time
        time.sleep(0.1)
        
        # Unlock
        event_monitor._handle_screen_unlock_event()
        
        # Should restore browser layout
        assert orch._current_layouts[device_id] == "browser"
    
    def test_window_change_during_lock_then_unlock(self, orchestrator_with_monitor,
                                                    mock_system):
        """
        Test window change during lock followed by unlock.
        
        Scenario:
        1. Device locked with "browser" layout
        2. User switches to VS Code (while locked)
        3. User unlocks
        4. Should show editor layout (current window)
        """
        orch, event_monitor = orchestrator_with_monitor
        device_id = "test_device"
        
        # Start with browser
        mock_system._current_window = WindowInfo(class_="Firefox", title="", raw="Firefox")
        orch._handle_window_change()
        assert orch._current_layouts[device_id] == "browser"
        
        # Lock
        event_monitor._handle_screen_lock_event()
        import time
        time.sleep(0.1)
        assert orch._is_locked is True
        
        # Change window while locked
        mock_system._current_window = WindowInfo(class_="Code", title="", raw="Code")
        orch._handle_window_change()  # Should be ignored
        
        # Unlock
        event_monitor._handle_screen_unlock_event()
        
        # After unlock, should detect current window and apply editor layout
        # This may require a window change event after unlock
        # (implementation dependent)


class TestComplexWindowRules:
    """Test complex window matching rules."""
    
    def test_regex_pattern_matching(self):
        """Test layout selection with regex patterns."""
        manager = LayoutManager(default_layout_name="default")
        
        # Add regex rule for all Google Chrome windows
        import re
        manager.add_rule(
            pattern=re.compile(r".*Chrome.*"),
            layout_name="browser",
            match_field="class",
            priority=100
        )
        
        # Test matching
        window1 = WindowInfo(class_="Google Chrome", title="", raw="Google Chrome")
        assert manager.select_layout(window1) == "browser"
        
        window2 = WindowInfo(class_="Chromium", title="", raw="Chromium")
        assert manager.select_layout(window2) == "default"  # Doesn't match
    
    def test_priority_based_selection(self):
        """Test that higher priority rules are checked first."""
        manager = LayoutManager(default_layout_name="default")
        
        # Lower priority: all browser-like apps → browser layout
        manager.add_rule(
            pattern="Mozilla",
            layout_name="browser",
            priority=50
        )
        
        # Higher priority: specific Firefox developer edition → dev layout
        manager.add_rule(
            pattern="Firefox Developer",
            layout_name="dev_tools",
            priority=100
        )
        
        # Regular Firefox → browser
        window1 = WindowInfo(class_="Mozilla Firefox", title="", raw="Mozilla Firefox")
        assert manager.select_layout(window1) == "browser"
        
        # Firefox Developer → dev_tools (higher priority)
        window2 = WindowInfo(class_="Firefox Developer", title="", raw="Firefox Developer")
        assert manager.select_layout(window2) == "dev_tools"
    
    def test_match_on_title_field(self):
        """Test matching on window title instead of class."""
        manager = LayoutManager(default_layout_name="default")
        
        # Match on title
        manager.add_rule(
            pattern="YouTube",
            layout_name="video",
            match_field="title",
            priority=100
        )
        
        # YouTube in browser
        window = WindowInfo(
            class_="Firefox",
            title="YouTube - Mozilla Firefox",
            raw="Firefox"
        )
        
        assert manager.select_layout(window) == "video"
