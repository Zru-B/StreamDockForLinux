"""
System event monitoring and routing - Pure business logic.

This module provides event monitoring logic extracted from LockMonitor,
focusing purely on event routing, verification, and handler management.
No infrastructure dependencies - uses SystemInterface abstraction.
"""

import logging
import threading
import time
from enum import Enum
from typing import Callable, Dict, List, Optional

from StreamDock.infrastructure.system_interface import SystemInterface


logger = logging.getLogger(__name__)


class SystemEvent(Enum):
    """Types of system events that can be monitored."""
    LOCK = "lock"
    UNLOCK = "unlock"
    WINDOW_CHANGED = "window_changed"


class SystemEventMonitor:
    """
    Pure business logic for system event monitoring and routing.
    
    This class is responsible for:
    - Registering event handlers
    - Routing events to appropriate handlers
    - Event verification (e.g., confirm lock actually happened)
    - Debouncing and deduplication
    
    Design Principles:
    - PURE business logic - no infrastructure dependencies
    - Event-driven architecture with handler registration
    - Easily testable without real system events
    - Thread-safe event processing
    
    Extracted from: LockMonitor's event handling logic
    Dependencies: SystemInterface (infrastructure abstraction only)
    """
    
    def __init__(self, system_interface: SystemInterface, 
                 verification_delay: float = 2.0):
        """
        Initialize system event monitor.
        
        Args:
            system_interface: System abstraction for lock state polling
            verification_delay: Seconds to wait before confirming lock (default: 2.0)
            
        Design Contract:
            - Does NOT start monitoring on init
            - Caller must explicitly call start_monitoring()
            - Handlers can be registered before or after starting
        """
        self._system = system_interface
        self._verification_delay = verification_delay
        
        # Handler registry: event type -> list of callbacks
        self._handlers: Dict[SystemEvent, List[Callable[[SystemEvent], None]]] = {
            SystemEvent.LOCK: [],
            SystemEvent.UNLOCK: [],
            SystemEvent.WINDOW_CHANGED: []
        }
        
        # Current state tracking
        self._current_state = {
            'is_locked': False,
            'last_event_time': 0.0
        }
        
        # Lock verification state (handles aborted lock scenario)
        self._pending_verification: Optional[threading.Timer] = None
        self._processing = False  # Concurrent processing guard
        
        logger.debug("SystemEventMonitor initialized with verification_delay=%.1fs", 
                    verification_delay)
    
    def register_handler(self, event: SystemEvent, 
                        handler: Callable[[SystemEvent], None]) -> None:
        """
        Register a handler for system events.
        
        Multiple handlers can be registered for the same event type.
        Handlers are called in registration order.
        
        Args:
            event: Type of event to handle
            handler: Callback function, receives SystemEvent as argument
            
        Design Contract:
            - Handler called with SystemEvent type
            - Handler should not block (runs on monitor thread)
            - Handler exceptions are caught and logged (don't crash monitor)
            - Multiple handlers can be registered for same event
            - Safe to call while monitoring is active
        """
        self._handlers[event].append(handler)
        logger.debug(f"Registered handler for {event.value} event (total: {len(self._handlers[event])})")
    
    def unregister_handler(self, event: SystemEvent, 
                          handler: Callable[[SystemEvent], None]) -> None:
        """
        Remove a previously registered handler.
        
        Args:
            event: Event type
            handler: Handler to remove
            
        Design Contract:
            - Safe to call even if handler not registered
            - Safe to call while monitoring is active
        """
        if handler in self._handlers[event]:
            self._handlers[event].remove(handler)
            logger.debug(f"Unregistered handler for {event.value} event")
    
    def start_monitoring(self) -> bool:
        """
        Start monitoring system events.
        
        Uses SystemInterface to monitor lock/unlock events via D-Bus.
        
        Returns:
            True if monitoring started successfully, False otherwise
            
        Design Contract:
            - Registers callback with SystemInterface.start_lock_monitor()
            - Idempotent: safe to call multiple times
            - Can be called before or after registering handlers
        """
        try:
            callback = self._on_lock_state_changed
            success = self._system.start_lock_monitor(callback)
            
            if success:
                logger.info("System event monitoring started")
            else:
                logger.warning("Failed to start system event monitoring")
            
            return success
        except Exception as e:
            logger.exception(f"Error starting system event monitoring: {e}")
            return False
    
    def stop_monitoring(self) -> None:
        """
        Stop monitoring system events.
        
        Design Contract:
            - Cancels any pending lock verification
            - Cleans up resources
            - Safe to call even if not monitoring
            - Safe to call multiple times
        """
        self._cancel_pending_verification()
        
        try:
            self._system.stop_lock_monitor()
            logger.info("System event monitoring stopped")
        except Exception as e:
            logger.exception(f"Error stopping system event monitoring: {e}")
    
    def _on_lock_state_changed(self, is_locked: bool) -> None:
        """
        PURE BUSINESS LOGIC: Handle lock state change event from system.
        
        This is the core business logic extracted from LockMonitor:
        - For lock events: Schedules verification (handles abort scenario)
        - For unlock events: Processes immediately and cancels pending locks
        - Includes debouncing to ignore duplicate events
        - Includes concurrency guard to prevent race conditions
        
        Design:
        - Lock verification handles the case where user aborts lock by moving mouse
        - Unlock always cancels pending verification (user aborted lock)
        - Debouncing prevents duplicate event processing
        
        Args:
            is_locked: True if screen locked, False if unlocked
        """
       # Prevent concurrent processing first
        if self._processing:
            logger.debug("Already processing state change, ignoring")
            return
        
        # Debounce: Ignore if state hasn't changed
        # Special case: If there's a pending verification and we get unlock, allow it through
        # (this handles the abort scenario where user cancels lock before verification)
        current_locked = self._current_state['is_locked']
        if current_locked == is_locked and not (not is_locked and self._pending_verification):
            logger.debug(f"Lock state unchanged ({is_locked}), ignoring duplicate signal")
            return
        
        if is_locked:
            # Lock event: Schedule verification instead of immediate dispatch
            # This handles race condition where user aborts lock by moving mouse
            self._cancel_pending_verification()
            logger.debug(f"Lock signal received, scheduling verification in {self._verification_delay}s")
            
            self._pending_verification = threading.Timer(
                self._verification_delay,
                self._verify_and_dispatch_lock
            )
            self._pending_verification.daemon = True
            self._pending_verification.start()
        
        else:
            # Unlock event: Cancel any pending lock verification and dispatch immediately
            # No verification needed for unlock - process immediately
            self._cancel_pending_verification()
            
            self._processing = True
            try:
                self._current_state['is_locked'] = False
                self._current_state['last_event_time'] = time.time()
                logger.info("🔓 Unlock event confirmed")
                self._dispatch_event(SystemEvent.UNLOCK)
            finally:
                self._processing = False
    
    def _verify_and_dispatch_lock(self) -> None:
        """
        PURE BUSINESS LOGIC: Verify lock state and dispatch if confirmed.
        
        This method handles the race condition where a lock event fires but
        the user aborts the lock by moving the mouse before it completes.
        
        Process:
        1. Poll SystemInterface to get actual lock state
        2. If actually locked: Dispatch LOCK event
        3. If not locked: Ignore (lock was aborted by user)
        
        Design:
        - Extracted from LockMonitor._verify_and_handle_lock
        - Pure business logic - uses SystemInterface for polling
        - Fail-safe: if poll fails, assume locked
        """
        try:
            self._pending_verification = None  # Timer has fired
            
            # Poll system to confirm actual lock state
            actual_locked = self._system.poll_lock_state()
            
            if actual_locked:
                # Lock confirmed - dispatch event to handlers
                logger.info("🔒 Lock verification confirmed - screen is locked")
                
                self._processing = True
                try:
                    self._current_state['is_locked'] = True
                    self._current_state['last_event_time'] = time.time()
                    self._dispatch_event(SystemEvent.LOCK)
                finally:
                    self._processing = False
            else:
                # Lock was aborted - ignore
                logger.info("🔒 Lock was aborted (user activity detected), ignoring lock event")
                self._current_state['is_locked'] = False
        
        except Exception as e:
            logger.exception(f"Error during lock verification: {e}")
            self._processing = False
    
    def _dispatch_event(self, event: SystemEvent) -> None:
        """
        PURE BUSINESS LOGIC: Dispatch event to all registered handlers.
        
        Calls all registered handlers for the given event type.
        Handler exceptions are caught and logged to prevent one handler
        from crashing the entire monitoring system.
        
        Args:
            event: Event type to dispatch
            
        Design Contract:
            - Handlers called in registration order
            - Handler exceptions don't prevent other handlers from running
            - All handler exceptions are logged
        """
        handlers = self._handlers[event]
        logger.debug(f"Dispatching {event.value} event to {len(handlers)} handler(s)")
        
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.exception(f"Error in {event.value} event handler: {e}")
    
    def _cancel_pending_verification(self) -> None:
        """
        Cancel any pending lock verification timer.
        
        Called when:
        - A new lock signal arrives (to reset the timer)
        - An unlock signal arrives (lock was aborted)
        - Monitor is stopped
        
        Design Contract:
            - Safe to call even if no verification pending
            - Idempotent
        """
        if self._pending_verification:
            self._pending_verification.cancel()
            self._pending_verification = None
            logger.debug("Cancelled pending lock verification timer")
    
    def is_locked(self) -> bool:
        """
        Get current lock state.
        
        Returns:
            True if system is currently locked, False otherwise
            
        Design Contract:
            - Reflects verified lock state (not raw events)
            - Updated only after lock verification completes
        """
        return self._current_state['is_locked']
    
    def get_handler_count(self, event: SystemEvent) -> int:
        """
        Get number of registered handlers for an event type.
        
        Args:
            event: Event type to query
            
        Returns:
            Number of handlers registered for this event
        """
        return len(self._handlers[event])
