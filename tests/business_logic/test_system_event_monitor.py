"""
Unit tests for SystemEventMonitor.

Tests pure business logic for event routing, verification, and handler management.
"""

import pytest
from unittest.mock import Mock, call
import time
import threading

from StreamDock.business_logic.system_event_monitor import SystemEventMonitor, SystemEvent
from StreamDock.infrastructure.system_interface import SystemInterface


class TestSystemEvent:
    """Tests for SystemEvent enum."""
    
    def test_system_event_values(self):
        """Design contract: SystemEvent has defined event types."""
        assert SystemEvent.LOCK.value == "lock"
        assert SystemEvent.UNLOCK.value == "unlock"
        assert SystemEvent.WINDOW_CHANGED.value == "window_changed"


class TestSystemEventMonitor:
    """Tests for SystemEventMonitor business logic."""
    
    @pytest.fixture
    def mock_system(self):
        """Mock SystemInterface."""
        system = Mock(spec=SystemInterface)
        system.start_lock_monitor.return_value = True
        system.poll_lock_state.return_value = True
        return system
    
    @pytest.fixture
    def monitor(self, mock_system):
        """SystemEventMonitor instance with short verification delay for testing."""
        return SystemEventMonitor(mock_system, verification_delay=0.1)
    
    # ==================== Initialization Tests ====================
    
    def test_initialization(self, monitor, mock_system):
        """Design contract: Monitor initializes without starting."""
        assert monitor._system is mock_system
        assert monitor._verification_delay == 0.1
        assert not monitor.is_locked()
        assert monitor.get_handler_count(SystemEvent.LOCK) == 0
    
    # ==================== Handler Registration Tests ====================
    
    def test_register_handler(self, monitor):
        """Design contract: Handlers can be registered."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        assert monitor.get_handler_count(SystemEvent.LOCK) == 1
    
    def test_register_multiple_handlers(self, monitor):
        """Design contract: Multiple handlers for same event."""
        handler1 = Mock()
        handler2 = Mock()
        
        monitor.register_handler(SystemEvent.LOCK, handler1)
        monitor.register_handler(SystemEvent.LOCK, handler2)
        
        assert monitor.get_handler_count(SystemEvent.LOCK) == 2
    
    def test_unregister_handler(self, monitor):
        """Design contract: Handlers can be unregistered."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        monitor.unregister_handler(SystemEvent.LOCK, handler)
        
        assert monitor.get_handler_count(SystemEvent.LOCK) == 0
    
    def test_unregister_unknown_handler(self, monitor):
        """Error handling: Unregistering unknown handler is safe."""
        handler = Mock()
        monitor.unregister_handler(SystemEvent.LOCK, handler)  # Should not raise
    
    # ==================== Monitoring Start/Stop Tests ====================
    
    def test_start_monitoring(self, monitor, mock_system):
        """Design contract: Start monitoring delegates to SystemInterface."""
        result = monitor.start_monitoring()
        
        assert result is True
        mock_system.start_lock_monitor.assert_called_once()
        # Verify callback was registered
        callback = mock_system.start_lock_monitor.call_args[0][0]
        assert callback == monitor._on_lock_state_changed
    
    def test_start_monitoring_failure(self, monitor, mock_system):
        """Error handling: Start failure reported correctly."""
        mock_system.start_lock_monitor.return_value = False
        
        result = monitor.start_monitoring()
        
        assert result is False
    
    def test_stop_monitoring(self, monitor, mock_system):
        """Design contract: Stop monitoring cleans up resources."""
        monitor.stop_monitoring()
        
        mock_system.stop_lock_monitor.assert_called_once()
    
    # ==================== Event Dispatch Tests ====================
    
    def test_unlock_event_dispatches_immediately(self, monitor, mock_system):
        """CRITICAL: Unlock events dispatch immediately without verification."""
        handler = Mock()
        monitor.register_handler(SystemEvent.UNLOCK, handler)
        
        # First get into locked state
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)  # Wait for lock verification
        
        # Now simulate unlock event
        monitor._on_lock_state_changed(False)
        
        # Handler should be called immediately (no verification for unlock)
        handler.assert_called_once_with(SystemEvent.UNLOCK)
        assert not monitor.is_locked()
    
    def test_lock_event_triggers_verification(self, monitor, mock_system):
        """CRITICAL: Lock events trigger verification, not immediate dispatch."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        # Simulate lock event
        monitor._on_lock_state_changed(True)
        
        # Handler should NOT be called immediately
        handler.assert_not_called()
        
        # Wait for verification
        time.sleep(0.15)
        
        # Now handler should be called (after verification)
        handler.assert_called_once_with(SystemEvent.LOCK)
        assert monitor.is_locked()
    
    def test_lock_verification_confirms_and_dispatches(self, monitor, mock_system):
        """CRITICAL: Lock verification polls system and dispatches if confirmed."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        # System confirms lock
        mock_system.poll_lock_state.return_value = True
        
        # Simulate lock event
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        # Verify polling happened
        mock_system.poll_lock_state.assert_called_once()
        
        # Handler should be called (lock confirmed)
        handler.assert_called_once_with(SystemEvent.LOCK)
        assert monitor.is_locked()
    
    def test_lock_verification_aborted_no_dispatch(self, monitor, mock_system):
        """CRITICAL: Lock aborted by user doesn't dispatch event."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        # System reports NOT locked (user aborted)
        mock_system.poll_lock_state.return_value = False
        
        # Simulate lock event
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        # Verify polling happened
        mock_system.poll_lock_state.assert_called_once()
        
        # Handler should NOT be called (lock was aborted)
        handler.assert_not_called()
        assert not monitor.is_locked()
    
    # ==================== Debouncing Tests ====================
    
    def test_duplicate_lock_events_ignored(self, monitor, mock_system):
        """Design contract: Duplicate lock signals are debounced."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        # First lock
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        handler.assert_called_once()
        handler.reset_mock()
        
        # Second lock (duplicate)
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        # Should NOT trigger again
        handler.assert_not_called()
    
    def test_duplicate_unlock_events_ignored(self, monitor, mock_system):
        """Design contract: Duplicate unlock signals are debounced."""
        handler = Mock()
        monitor.register_handler(SystemEvent.UNLOCK, handler)
        
        # Get into locked state first
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        # First unlock
        monitor._on_lock_state_changed(False)
        handler.assert_called_once()
        handler.reset_mock()
        
        # Second unlock (duplicate)
        monitor._on_lock_state_changed(False)
        
        # Should NOT trigger again
        handler.assert_not_called()
    
    # ==================== Verification Cancellation Tests ====================
    
    def test_unlock_cancels_pending_lock_verification(self, monitor, mock_system):
        """CRITICAL: Unlock signal cancels pending lock verification."""
        lock_handler = Mock()
        unlock_handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, lock_handler)
        monitor.register_handler(SystemEvent.UNLOCK, unlock_handler)
        
        # Simulate lock event (starts verification timer with longer delay for this test)
        monitor._verification_delay = 0.3  # Longer delay to ensure we can cancel
        monitor._on_lock_state_changed(True)
        
        # Verify timer was started
        assert monitor._pending_verification is not None
        
        # Immediately unlock (should cancel verification)
        monitor._on_lock_state_changed(False)
        
        # Verify timer was cancelled
        assert monitor._pending_verification is None
        
        # Wait to ensure lock handler doesn't fire
        time.sleep(0.4)
        
        # Lock handler should NOT be called (verification cancelled)
        lock_handler.assert_not_called()
        
        # Only unlock handler called
        unlock_handler.assert_called_once()
        assert not monitor.is_locked()
    
    def test_new_lock_cancels_previous_verification(self, monitor, mock_system):
        """Edge case: New lock signal resets verification timer."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        mock_system.poll_lock_state.return_value = True
        
        # First lock signal
        monitor._on_lock_state_changed(True)
        
        # Second lock signal before verification (resets timer)
        time.sleep(0.05)
        monitor._on_lock_state_changed(False)  # Change to unlock first
        monitor._current_state['is_locked'] = False  # Reset state
        monitor._on_lock_state_changed(True)
        
        # Wait for verification
        time.sleep(0.15)
        
        # Should only dispatch once (second verification)
        assert handler.call_count == 1
    
    # ==================== Concurrency Tests ====================
    
    def test_concurrent_processing_prevented(self, monitor, mock_system):
        """Design contract: Concurrent event processing is prevented."""
        # Get into locked state first
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        # Create a handler that blocks for a moment
        call_count = [0]
        def slow_handler(e):
            call_count[0] += 1
            time.sleep(0.05)
        
        monitor.register_handler(SystemEvent.UNLOCK, slow_handler)
        
        # Simulate rapid unlock events in thread
        def send_events():
            monitor._on_lock_state_changed(False)
            monitor._on_lock_state_changed(False)  # Should be ignored (debounced)
        
        thread = threading.Thread(target=send_events)
        thread.start()
        thread.join()
        
        # Only one handler call (second was debounced as duplicate)
        assert call_count[0] == 1
    
    # ==================== Handler Error Tests ====================
    
    def test_handler_exception_does_not_crash_monitor(self, monitor, mock_system):
        """Error handling: Handler exceptions are caught and logged."""
        # Get into locked state first
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        failing_handler = Mock(side_effect=Exception("Handler failed"))
        working_handler = Mock()
        
        monitor.register_handler(SystemEvent.UNLOCK, failing_handler)
        monitor.register_handler(SystemEvent.UNLOCK, working_handler)
        
        # Simulate unlock
        monitor._on_lock_state_changed(False)
        
        # Both handlers should be called despite exception
        failing_handler.assert_called_once()
        working_handler.assert_called_once()
    
    def test_multiple_handlers_all_called_even_if_one_fails(self, monitor, mock_system):
        """Design contract: All handlers called even if one raises exception."""
        # Get into locked state first
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        handler1 = Mock()
        handler2 = Mock(side_effect=Exception("Fail"))
        handler3 = Mock()
        
        monitor.register_handler(SystemEvent.UNLOCK, handler1)
        monitor.register_handler(SystemEvent.UNLOCK, handler2)
        monitor.register_handler(SystemEvent.UNLOCK, handler3)
        
        monitor._on_lock_state_changed(False)
        
        # All three should be called
        handler1.assert_called_once()
        handler2.assert_called_once()
        handler3.assert_called_once()
    
    # ==================== Integration-Style Tests ====================
    
    def test_complete_lock_unlock_cycle(self, monitor, mock_system):
        """Logical test: Complete lock/unlock cycle."""
        events = []
        
        lock_handler = lambda e: events.append('lock')
        unlock_handler = lambda e: events.append('unlock')
        
        monitor.register_handler(SystemEvent.LOCK, lock_handler)
        monitor.register_handler(SystemEvent.UNLOCK, unlock_handler)
        
        # Lock
        mock_system.poll_lock_state.return_value = True
        monitor._on_lock_state_changed(True)
        time.sleep(0.15)
        
        assert events == ['lock']
        assert monitor.is_locked()
        
        # Unlock
        monitor._on_lock_state_changed(False)
        
        assert events == ['lock', 'unlock']
        assert not monitor.is_locked()
    
    def test_stop_monitoring_cancels_pending_verification(self, monitor, mock_system):
        """Design contract: Stopping monitor cancels pending verification."""
        handler = Mock()
        monitor.register_handler(SystemEvent.LOCK, handler)
        
        # Start lock verification
        monitor._on_lock_state_changed(True)
        
        # Stop monitoring before verification completes
        monitor.stop_monitoring()
        
        # Wait past verification delay
        time.sleep(0.15)
        
        # Handler should NOT be called (verification cancelled)
        handler.assert_not_called()
