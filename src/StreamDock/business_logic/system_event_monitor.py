"""
System event monitoring and routing - Pure business logic.

This module provides event monitoring logic extracted from LockMonitor,
focusing purely on event routing, verification, and handler management.
No infrastructure dependencies - uses SystemInterface abstraction.
"""

import logging
import threading
import time
from collections import deque
from enum import Enum
from typing import Callable, Dict, List, Optional

from StreamDock.infrastructure.system_interface import SystemInterface
from StreamDock.infrastructure.window_interface import WindowInterface

logger = logging.getLogger(__name__)

RECENT_WINDOW_COUNT = 15

# Never equal to a polled window key, so the next poll always dispatches.
_WINDOW_UNKNOWN = object()


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
                 window_manager: WindowInterface,
                 verification_delay: float = 2.0):
        """
        Initialize system event monitor.

        Args:
            system_interface: System abstraction for lock state polling
            window_manager: Window abstraction for polling active window
            verification_delay: Seconds to wait before confirming lock (default: 2.0)

        Design Contract:
            - Does NOT start monitoring on init
            - Caller must explicitly call start_monitoring()
            - Handlers can be registered before or after starting
        """
        self._system = system_interface
        self._windows = window_manager
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

        # Lock verification state (handles aborted lock scenario). The timer
        # stays set until its verification has finished, including the poll,
        # so a signal arriving mid-poll still sees a lock being verified.
        self._pending_verification: Optional[threading.Timer] = None
        # Guards the lock state, the verification timer and the dispatch
        # queue: signals arrive on the D-Bus thread, verification on a timer.
        self._state_lock = threading.Lock()
        # Bumped on every lock-state signal; a verification that finds it
        # changed after its poll is stale and must not dispatch.
        self._generation = 0
        # Handlers run one event at a time. A signal arriving while they run
        # is queued here (only the newest counts) rather than dropped, so the
        # final state always reaches the handlers.
        self._queued_event: Optional[SystemEvent] = None
        self._dispatching = False

        # Window polling state
        self._window_poll_thread: Optional[threading.Thread] = None
        self._window_poll_running = False
        self._window_poll_interval = 0.5  # seconds
        # Class and title: a browser switching tabs keeps its class, and both
        # title-based layout rules and widgets watching for a web app need it.
        self._last_window_key: object = None
        self._current_window = None
        # Recently focused windows, newest last, for the rule editor's picker:
        # by the time the user is editing a rule, the window they mean has
        # already lost focus to the editor.
        self._recent_windows: deque = deque(maxlen=RECENT_WINDOW_COUNT)
        self._recent_lock = threading.Lock()

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
        logger.debug("Registered handler for %s event (total: %d)",
                     event.value, len(self._handlers[event]))

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
            logger.debug("Unregistered handler for %s event", event.value)

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
            lock_callback = self._on_lock_state_changed
            success = self._system.start_lock_monitor(lock_callback)

            # Seed the internal lock state from the real system state before
            # subscribing to D-Bus change signals.  Without this, if the system
            # is already locked when monitoring starts (e.g. the app restarted
            # because the device was reconnected while the screen was locked),
            # the debounce check in _on_lock_state_changed would see
            # current_locked==False==is_locked and swallow the subsequent
            # unlock signal, leaving the orchestrator stuck in the wrong state.
            # None means the state could not be read: keep the one we have.
            polled = self._system.poll_lock_state()
            if polled is not None:
                self._current_state['is_locked'] = bool(polled)
            if self._current_state['is_locked']:
                logger.info("Lock state initialised: system is currently locked")

            if success:
                logger.info("System event monitoring started")
            else:
                logger.warning("Failed to start system event monitoring")

            # Start window polling thread regardless of lock monitor success
            self._start_window_polling()

            return success
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error starting system event monitoring: %s", e)
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
        with self._state_lock:
            # Also invalidates a verification already past its timer.
            self._generation += 1
            self._cancel_pending_verification()
        self._stop_window_polling()

        try:
            self._system.stop_lock_monitor()
            logger.info("System event monitoring stopped")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error stopping system event monitoring: %s", e)

    def _start_window_polling(self) -> None:
        """Start the window polling background thread."""
        if self._window_poll_running:
            return
        self._window_poll_running = True
        self._window_poll_thread = threading.Thread(
            target=self._window_poll_loop, name="window-poll", daemon=True
        )
        self._window_poll_thread.start()
        logger.info("Window polling started (interval=%.1fs)", self._window_poll_interval)

    def _stop_window_polling(self) -> None:
        """Stop the window polling thread."""
        self._window_poll_running = False
        if self._window_poll_thread is not None:
            self._window_poll_thread.join(timeout=2)
            self._window_poll_thread = None
        logger.debug("Window polling stopped")

    def _window_poll_loop(self) -> None:
        """Poll the active window and fire WINDOW_CHANGED when it changes."""
        while self._window_poll_running:
            try:
                # Suppress window change dispatches while a lock is being
                # verified or is in force: the lock screen holds focus, and
                # the first poll after unlocking must report the real window
                # even if it is the one focused before the lock.
                if self._pending_verification is not None or self._current_state['is_locked']:
                    self._last_window_key = _WINDOW_UNKNOWN
                    time.sleep(self._window_poll_interval)
                    continue

                window_info = self._windows.get_active_window()
                key = (window_info.class_, window_info.title) if window_info else None

                if key != self._last_window_key:
                    self._last_window_key = key
                    self._current_window = window_info
                    self._remember_window(window_info)
                    logger.debug("Window changed: %s", key[0] if key else None)
                    self._dispatch_event(SystemEvent.WINDOW_CHANGED)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error in window poll loop: %s", e)

            time.sleep(self._window_poll_interval)

    def _on_lock_state_changed(self, is_locked: bool) -> None:
        """
        Handle a lock state change signal from the system.

        - Lock: schedules a verification, since the user can abort a lock by
          moving the mouse before it completes.
        - Unlock: cancels any pending verification and dispatches immediately.
        - A signal repeating the current state is ignored, except an unlock
          while a lock is being verified (the aborted-lock case).

        Args:
            is_locked: True if screen locked, False if unlocked
        """
        with self._state_lock:
            self._generation += 1
            current_locked = self._current_state['is_locked']
            verifying = self._pending_verification is not None
            if current_locked == is_locked and not (not is_locked and verifying):
                logger.debug("Lock state unchanged (%s), ignoring duplicate signal", is_locked)
                return

            self._cancel_pending_verification()

            if is_locked:
                logger.debug("Lock signal received, scheduling verification in %.1fs",
                             self._verification_delay)
                self._pending_verification = threading.Timer(
                    self._verification_delay,
                    self._verify_and_dispatch_lock,
                    args=(self._generation,)
                )
                self._pending_verification.daemon = True
                self._pending_verification.start()
                return

            self._current_state['is_locked'] = False
            self._current_state['last_event_time'] = time.time()
            self._queued_event = SystemEvent.UNLOCK
            logger.info("🔓 Unlock event confirmed")

        self._run_queued_events()

    def _verify_and_dispatch_lock(self, generation: Optional[int] = None) -> None:
        """
        Verify the lock state after the delay and dispatch LOCK if confirmed.

        Handles the user aborting a lock by moving the mouse before it
        completes: the poll then reports unlocked and nothing is dispatched.
        Any lock-state signal arriving while the poll runs supersedes it.

        Args:
            generation: Signal generation that scheduled this verification;
                None means the latest one
        """
        try:
            with self._state_lock:
                if generation is None:
                    generation = self._generation
                elif generation != self._generation:
                    return

            actual_locked = self._system.poll_lock_state()

            with self._state_lock:
                if generation != self._generation:
                    logger.info("🔒 Lock state changed during verification, discarding its result")
                    return
                self._pending_verification = None

                # Only a definite "unlocked" aborts. An unreadable state
                # (None) keeps the signal's word for it: failing open would
                # leave the deck lit and usable on a locked screen.
                if actual_locked is False:
                    logger.info("🔒 Lock was aborted (user activity detected), ignoring lock event")
                    self._current_state['is_locked'] = False
                    return

                if actual_locked is None:
                    logger.warning("🔒 Lock state could not be verified - assuming locked")
                else:
                    logger.info("🔒 Lock verification confirmed - screen is locked")
                self._current_state['is_locked'] = True
                self._current_state['last_event_time'] = time.time()
                self._queued_event = SystemEvent.LOCK

            self._run_queued_events()

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error during lock verification: %s", e)

    def _run_queued_events(self) -> None:
        """
        Dispatch queued lock events one at a time.

        Whoever finds no dispatch running becomes the dispatcher and keeps
        going until the queue is empty; anyone else just leaves its event
        queued. So a signal arriving during a slow handler is delivered right
        after it instead of being lost.
        """
        with self._state_lock:
            if self._dispatching:
                return
            self._dispatching = True

        try:
            while True:
                with self._state_lock:
                    event = self._queued_event
                    self._queued_event = None
                    if event is None:
                        self._dispatching = False
                        return
                self._dispatch_event(event)
        except BaseException:
            with self._state_lock:
                self._dispatching = False
            raise

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
        logger.debug("Dispatching %s event to %d handler(s)", event.value, len(handlers))

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error in %s event handler: %s", event.value, e)

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

    def _remember_window(self, window_info) -> None:
        if window_info is None or not (window_info.class_ or window_info.title):
            return
        key = (window_info.class_, window_info.title)
        with self._recent_lock:
            for existing in list(self._recent_windows):
                if (existing.class_, existing.title) == key:
                    self._recent_windows.remove(existing)
            self._recent_windows.append(window_info)

    @property
    def recent_windows(self) -> list:
        """Recently focused windows (WindowInfo), newest first, without repeats."""
        with self._recent_lock:
            return list(reversed(self._recent_windows))

    def seed_window(self, window_info) -> None:
        """
        Record a window already acted on before monitoring starts.

        The application applies the layout for the focused window itself at
        startup; seeded here, the first poll does not report that same window
        as a change and render the layout a second time.
        """
        if window_info is None:
            return
        self._current_window = window_info
        self._last_window_key = (window_info.class_, window_info.title)
        self._remember_window(window_info)

    @property
    def current_window(self):
        """The focused window as last polled (a WindowInfo), or None."""
        return self._current_window

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
