"""
Integration tests for DeviceOrchestrator.

Tests orchestration logic by coordinating infrastructure and business logic components.
"""

import pytest
from unittest.mock import Mock, call, MagicMock

from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator
from StreamDock.business_logic import SystemEventMonitor, SystemEvent, LayoutManager
from StreamDock.infrastructure import HardwareInterface, SystemInterface, DeviceRegistry, TrackedDevice
from StreamDock.infrastructure.window_interface import WindowInterface
from StreamDock.domain.Models import WindowInfo


class TestDeviceOrchestrator:
    """Integration tests for DeviceOrchestrator."""
    
    @pytest.fixture
    def mock_hardware(self):
        """Mock HardwareInterface."""
        hardware = Mock(spec=HardwareInterface)
        hardware.set_brightness.return_value = True
        hardware.send_image.return_value = True
        return hardware
    
    @pytest.fixture
    def mock_system(self):
        """Mock SystemInterface."""
        system = Mock(spec=SystemInterface)
        system.start_lock_monitor.return_value = True
        return system
    
    @pytest.fixture
    def mock_windows(self):
        """Mock WindowInterface."""
        windows = Mock(spec=WindowInterface)
        windows.get_active_window.return_value = WindowInfo(
            title="Test Window",
            class_="test_class",
            raw="test"
        )
        return windows
    
    @pytest.fixture
    def mock_registry(self):
        """Mock DeviceRegistry."""
        registry = Mock(spec=DeviceRegistry)
        # Return a mock device
        test_device = Mock()
        test_device.device_info.serial = "SERIAL"
        test_device.is_connected = True
        
        registry.get_all_devices.return_value = [test_device]
        return registry
    
    @pytest.fixture
    def mock_event_monitor(self):
        """Mock SystemEventMonitor."""
        monitor = Mock(spec=SystemEventMonitor)
        monitor.start_monitoring.return_value = True
        return monitor
    
    @pytest.fixture
    def mock_layout_manager(self):
        """Mock LayoutManager."""
        manager = Mock(spec=LayoutManager)
        manager.get_default_layout.return_value = "default"
        manager.select_layout.return_value = "default"
        return manager
    
    @pytest.fixture
    def mock_layout(self):
        """Mock Layout object."""
        layout = Mock()
        layout.apply = Mock()
        return layout
    
    @pytest.fixture
    def orchestrator(self, mock_hardware, mock_system, mock_windows, mock_registry, 
                     mock_event_monitor, mock_layout_manager):
        """DeviceOrchestrator instance with mocked dependencies."""
        return DeviceOrchestrator(
            hardware=mock_hardware,
            system=mock_system,
            window_manager=mock_windows,
            registry=mock_registry,
            event_monitor=mock_event_monitor,
            layout_manager=mock_layout_manager
        )
    
    # ==================== Initialization Tests ====================
    
    def test_initialization_with_dependencies(self, orchestrator, mock_event_monitor):
        """Design contract: Orchestrator initializes with all dependencies."""
        assert orchestrator._hardware is not None
        assert orchestrator._system is not None
        assert orchestrator._registry is not None
        assert orchestrator._event_monitor is not None
        assert orchestrator._layout_manager is not None
        
        # Check event handlers registered
        assert mock_event_monitor.register_handler.call_count == 3
    
    def test_register_layout(self, orchestrator, mock_layout):
        """Design contract: Layouts can be registered."""
        orchestrator.register_layout("test_layout", mock_layout)
        
        assert "test_layout" in orchestrator._layouts
        assert orchestrator._layouts["test_layout"] == mock_layout
    
    def test_set_default_brightness(self, orchestrator):
        """Design contract: Default brightness can be set."""
        orchestrator.set_default_brightness(75)
        
        assert orchestrator._default_brightness == 75
    
    def test_set_default_brightness_clamps(self, orchestrator):
        """Error handling: Brightness is clamped to valid range."""
        orchestrator.set_default_brightness(150)
        assert orchestrator._default_brightness == 100
        
        orchestrator.set_default_brightness(-10)
        assert orchestrator._default_brightness == 0
    
    # ==================== Start/Stop Tests ====================
    
    def test_start_initializes_devices_and_monitoring(self, orchestrator, 
                                                       mock_registry, mock_event_monitor):
        """CRITICAL: Start initializes devices and starts monitoring."""
        result = orchestrator.start()
        
        assert result is True
        mock_registry.get_all_devices.assert_called_once()
        mock_event_monitor.start_monitoring.assert_called_once()
        assert orchestrator.get_device_count() == 1
    
    def test_start_returns_false_on_monitoring_failure(self, orchestrator, mock_event_monitor):
        """Error handling: Start returns False if monitoring fails."""
        mock_event_monitor.start_monitoring.return_value = False
        
        result = orchestrator.start()
        
        assert result is False
    
    def test_stop_cleans_up(self, orchestrator, mock_event_monitor):
        """Design contract: Stop cleans up resources."""
        orchestrator.start()
        orchestrator.stop()
        
        mock_event_monitor.stop_monitoring.assert_called_once()
        assert orchestrator.get_device_count() == 0
    
    # ==================== Event Handling Tests ====================
    
    def test_lock_event_turns_off_screens(self, orchestrator, mock_registry):
        """CRITICAL: Lock event turns off screens and closes connections."""
        orchestrator.start()
        
        # Simulate lock event
        orchestrator._on_lock(SystemEvent.LOCK)
        
        # Verify screen turned off and connection closed
        device = mock_registry.get_all_devices.return_value[0].device_instance
        device.screen_off.assert_called_once()
        device.close.assert_called_once()
        assert orchestrator.is_locked() is True
    
    def test_unlock_event_restores_screens(self, orchestrator, mock_registry):
        """CRITICAL: Unlock event restores brightness and connections."""
        orchestrator.start()
        orchestrator.set_default_brightness(75)
        
        # Lock first
        orchestrator._on_lock(SystemEvent.LOCK)
        
        # Then unlock
        orchestrator._on_unlock(SystemEvent.UNLOCK)
        
        # Verify brightness restored and screen turned on
        device = mock_registry.get_all_devices.return_value[0].device_instance
        device.open.assert_called_once()
        device.init.assert_called_once()
        device.set_brightness.assert_called_once_with(75)
        assert orchestrator.is_locked() is False
    
    def test_unlock_triggers_reenumeration_on_open_failure(self, orchestrator, mock_registry, mock_hardware):
        """CRITICAL: Failed open during unlock triggers USB re-enumeration."""
        orchestrator.start()
        
        device = mock_registry.get_all_devices.return_value[0].device_instance
        device.path = '/dev/hidraw_old'
        device.vendor_id = 0x6603
        device.product_id = 0x1006
        
        # Simulate open failure the first time, success the second time
        device.open.side_effect = [False, True]
        
        # Setup mock hardware to return a new device path
        new_device_info = MagicMock()
        new_device_info.path = '/dev/hidraw_new'
        mock_hardware.enumerate_devices.return_value = [new_device_info]
        
        # Lock and unlock
        orchestrator._on_lock(SystemEvent.LOCK)
        orchestrator._on_unlock(SystemEvent.UNLOCK)
        
        # Verify enumerate_devices was called
        mock_hardware.enumerate_devices.assert_called_once_with(0x6603, 0x1006)
        
        # Verify path updated and open retried
        assert device.path == '/dev/hidraw_new'
        assert device.open.call_count == 2
        device.init.assert_called_once()

    
    def test_window_changed_selects_layout(self, orchestrator, mock_layout_manager, 
                                          mock_windows):
        """CRITICAL: Window change triggers layout selection."""
        orchestrator.start()
        
        # Simulate window change
        orchestrator._on_window_changed(SystemEvent.WINDOW_CHANGED)
        
        # Verify layout selection was queried
        mock_windows.get_active_window.assert_called_once()
        mock_layout_manager.select_layout.assert_called_once()
    
    def test_window_changed_applies_different_layout(self, orchestrator, 
                                                      mock_layout_manager, mock_layout):
        """CRITICAL: Window change applies new layout if different."""
        orchestrator.start()
        orchestrator.register_layout("browser", mock_layout)
        
        # Change layout selection to return "browser"
        mock_layout_manager.select_layout.return_value = "browser"
        
        # Simulate window change
        orchestrator._on_window_changed(SystemEvent.WINDOW_CHANGED)
        
        # Verify layout was applied
        mock_layout.apply.assert_called_once()
        
        # Check current layout updated
        device_id = list(orchestrator._devices.keys())[0]
        assert orchestrator.get_current_layout(device_id) == "browser"
    
    def test_window_changed_skipped_when_locked(self, orchestrator, mock_layout):
        """Design contract: Layout changes skipped while locked."""
        orchestrator.start()
        orchestrator.register_layout("browser", mock_layout)
        
        # Lock the system
        orchestrator._on_lock(SystemEvent.LOCK)
        
        # Simulate window change
        orchestrator._on_window_changed(SystemEvent.WINDOW_CHANGED)
        
        # Verify layout was NOT applied
        mock_layout.apply.assert_not_called()
    
    # ==================== Layout Management Tests ====================
    
    def test_apply_layout_changes_device_layout(self, orchestrator, mock_layout):
        """Design contract: Applying layout updates device state."""
        orchestrator.start()
        orchestrator.register_layout("test", mock_layout)
        
        device_id = list(orchestrator._devices.keys())[0]
        orchestrator._apply_layout(device_id, "test")
        
        mock_layout.apply.assert_called_once()
        assert orchestrator.get_current_layout(device_id) == "test"
    
    def test_layout_not_changed_if_same(self, orchestrator, mock_layout):
        """Design contract: Same layout not reapplied unless forced."""
        # Use test_layout (not default) to avoid initial state collision
        orchestrator.register_layout("test_layout", mock_layout)
        orchestrator.start()
        
        device_id = list(orchestrator._devices.keys())[0]
        
        # Apply same layout twice (second should be skipped)
        orchestrator._apply_layout(device_id, "test_layout")
        orchestrator._apply_layout(device_id, "test_layout")
        
        # Should only be called once (skipped second time)
        assert mock_layout.apply.call_count == 1
    
    def test_layout_forced_reapply(self, orchestrator, mock_layout):
        """Design contract: Forced apply reapplies same layout."""
        # Use test_layout (not default) to avoid initial state collision
        orchestrator.register_layout("test_layout", mock_layout)
        orchestrator.start()
        
        device_id = list(orchestrator._devices.keys())[0]
        
        # Apply same layout twice with force=True
        orchestrator._apply_layout(device_id, "test_layout")
        orchestrator._apply_layout(device_id, "test_layout", force=True)
        
        # Should be called twice
        assert mock_layout.apply.call_count == 2
    
    def test_apply_layout_handles_missing_layout(self, orchestrator):
        """Error handling: Missing layout is handled gracefully."""
        orchestrator.start()
        
        device_id = list(orchestrator._devices.keys())[0]
        
        # Try to apply non-existent layout (should not crash)
        orchestrator._apply_layout(device_id, "nonexistent")
        
        # Current layout should still be default
        assert orchestrator.get_current_layout(device_id) == "default"
    
    # ==================== Action Execution Tests ====================
    
    def test_execute_key_press_action(self, orchestrator, mock_system):
        """Design contract: KEY_PRESS action calls system interface."""
        orchestrator.execute_action("KEY_PRESS", "CTRL+C")
        
        mock_system.send_key_combo.assert_called_once_with("CTRL+C")
    
    def test_execute_wait_action(self, orchestrator):
        """Design contract: WAIT action sleeps."""
        import time
        start = time.time()
        orchestrator.execute_action("WAIT", 0.01)
        elapsed = time.time() - start
        
        assert elapsed >= 0.01
    
    def test_execute_brightness_up_action(self, orchestrator, mock_hardware):
        """Design contract: DEVICE_BRIGHTNESS_UP increases brightness."""
        orchestrator.set_default_brightness(50)
        orchestrator.execute_action("DEVICE_BRIGHTNESS_UP", None)
        
        assert orchestrator._default_brightness == 60
        mock_hardware.set_brightness.assert_called_with(60)
    
    def test_execute_brightness_down_action(self, orchestrator, mock_hardware):
        """Design contract: DEVICE_BRIGHTNESS_DOWN decreases brightness."""
        orchestrator.set_default_brightness(50)
        orchestrator.execute_action("DEVICE_BRIGHTNESS_DOWN", None)
        
        assert orchestrator._default_brightness == 40
        mock_hardware.set_brightness.assert_called_with(40)
    
    def test_execute_change_layout_action(self, orchestrator, mock_layout):
        """Design contract: CHANGE_LAYOUT action applies layout."""
        orchestrator.start()
        orchestrator.register_layout("browser", mock_layout)
        
        device_id = list(orchestrator._devices.keys())[0]
        orchestrator.execute_action("CHANGE_LAYOUT", "browser", device_id=device_id)
        
        mock_layout.apply.assert_called_once()
        assert orchestrator.get_current_layout(device_id) == "browser"
    
    def test_execute_unknown_action(self, orchestrator):
        """Error handling: Unknown actions are logged but don't crash."""
        # Should not raise exception
        orchestrator.execute_action("UNKNOWN_ACTION", "parameter")
    
    # ==================== State Query Tests ====================
    
    def test_get_device_count(self, orchestrator):
        """Design contract: Device count tracked correctly."""
        assert orchestrator.get_device_count() == 0
        
        orchestrator.start()
        assert orchestrator.get_device_count() == 1
        
        orchestrator.stop()
        assert orchestrator.get_device_count() == 0
    
    def test_get_current_layout(self, orchestrator):
        """Design contract: Current layout can be queried."""
        orchestrator.start()
        
        device_id = list(orchestrator._devices.keys())[0]
        layout = orchestrator.get_current_layout(device_id)
        
        assert layout == "default"
    
    def test_is_locked(self, orchestrator):
        """Design contract: Lock state can be queried."""
        assert orchestrator.is_locked() is False
        
        orchestrator._on_lock(SystemEvent.LOCK)
        assert orchestrator.is_locked() is True
        
        orchestrator._on_unlock(SystemEvent.UNLOCK)
        assert orchestrator.is_locked() is False
