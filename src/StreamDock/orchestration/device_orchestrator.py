"""
Device orchestration - Coordinates all layers.

This module provides the DeviceOrchestrator which is the central coordinator
that connects infrastructure, business logic, and device management.
"""

import functools
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from StreamDock.business_logic import LayoutManager, SystemEvent, SystemEventMonitor
from StreamDock.business_logic.action_executor import ActionExecutor
from StreamDock.devices.product_ids import STREAMDOCK_293V3_PID, STREAMDOCK_VID
from StreamDock.infrastructure import (
    DeviceRegistry,
    HardwareInterface,
    SystemInterface,
    TrackedDevice,
)
from StreamDock.infrastructure.window_interface import WindowInterface

logger = logging.getLogger(__name__)


def _unwrap(device: Any) -> Any:
    """
    Return the real device behind a registry wrapper.

    Checked by type rather than with hasattr: every attribute exists on a Mock,
    so duck-typing here silently swaps the device for a child mock and device
    calls vanish in tests.

    Args:
        device: Either a device instance or a TrackedDevice wrapping one

    Returns:
        The device instance
    """
    if isinstance(device, TrackedDevice):
        return device.device_instance
    return device


def _serialized(method):
    """
    Serialise an operation that talks to the device.

    Layout application, lock/unlock and shutdown each arrive on a different
    thread - start() applies the context-aware layout on the caller's thread
    while the window-poll thread may already be applying one. Key images are
    multi-packet HID transfers, so overlapping operations interleave their
    packets and keys end up blank.
    """
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._device_lock:  # pylint: disable=protected-access
            return method(self, *args, **kwargs)
    return wrapper


class DeviceOrchestrator:
    """
    Central orchestrator for all StreamDock operations.

    This is the SOLE orchestration component - the glue between layers.

    Responsibilities:
    - Device lifecycle management (init, connect, disconnect)
    - Event coordination (system events → business logic → actions)
    - Layout management (selection + application)
    - State management (current layout, brightness)
    - Action execution (coordinates infrastructure + device)

    Design Principles:
    - Coordinates ALL layers (infrastructure, business logic)
    - Event-driven (listens to SystemEventMonitor)
    - Stateful (tracks current state per device)
    - Single Responsibility (ONLY orchestration)
    - Dependency Injection (all dependencies injected)

    Dependencies:
    - Infrastructure: HardwareInterface, SystemInterface, DeviceRegistry
    - Business Logic: SystemEventMonitor, LayoutManager

    NOT Responsible For:
    - Window detection (SystemInterface does this)
    - Device communication (HardwareInterface does this)
    - Rule matching (LayoutManager does this)
    - Event verification (SystemEventMonitor does this)
    - Configuration parsing (Application layer does this)
    """

    def __init__(self,  # pylint: disable=too-many-positional-arguments
                 hardware: HardwareInterface,
                 system: SystemInterface,
                 window_manager: WindowInterface,
                 registry: Optional[DeviceRegistry],
                 event_monitor: SystemEventMonitor,
                 layout_manager: LayoutManager,
                 action_executor: Optional[ActionExecutor] = None):
        """
        Initialize orchestrator with all dependencies.

        Args:
            hardware: Hardware abstraction for device communication
            system: System abstraction for OS interactions
            registry: Device registry for tracking devices (optional for simplified mode)
            event_monitor: System event monitor for event routing
            layout_manager: Layout manager for layout selection

        Design Contract:
            - All dependencies injected (no creation)
            - Does NOT start monitoring on init
            - Caller must call start() explicitly
            - Event handlers registered immediately
        """
        self._hardware = hardware
        self._system = system
        self._windows = window_manager
        self._registry = registry  # Can be None in simplified mode
        self._event_monitor = event_monitor
        self._layout_manager = layout_manager
        self._action_executor = action_executor

        # State management
        self._devices: Dict[str, Any] = {}  # device_id -> device instance
        self._current_layouts: Dict[str, str] = {}  # device_id -> layout_name
        self._layouts: Dict[str, Any] = {}  # layout_name -> Layout object
        self._default_brightness: int = 100
        self._is_locked: bool = False

        # Guards every device-touching operation (see @_serialized)
        self._device_lock = threading.RLock()

        # Device configuration callback (HYBRID: for ConfigLoader integration)
        self._device_config_callback: Optional[Any] = None

        # Notified with the layout name whenever the active layout changes.
        # A plain callable, not a Qt signal: this layer must stay GUI-free.
        self._layout_changed_callback: Optional[Callable[[str], None]] = None

        # Register event handlers with SystemEventMonitor
        self._event_monitor.register_handler(SystemEvent.LOCK, self._on_lock)
        self._event_monitor.register_handler(SystemEvent.UNLOCK, self._on_unlock)
        self._event_monitor.register_handler(SystemEvent.WINDOW_CHANGED, self._on_window_changed)

        logger.debug("DeviceOrchestrator initialized with dependencies")

    def attach_device(self, device_id: str, device: Any,
                      current_layout: Optional[str] = None) -> None:
        """
        Put a device under this orchestrator's control.

        Args:
            device_id: Identifier to track the device by
            device: Device instance (already open)
            current_layout: Layout already on screen, so the first window
                change does not redundantly re-render it

        Design Contract:
            - Does NOT open or configure the device; the caller owns that
            - Replaces any device previously attached under this id
        """
        with self._device_lock:
            self._devices[device_id] = device
            if current_layout is not None:
                self._current_layouts[device_id] = current_layout
            else:
                self._current_layouts.pop(device_id, None)

        logger.debug("Attached device %s (layout=%s)", device_id, current_layout)

    @_serialized
    def detach_device(self, device_id: str, *, screen_off: bool = True,
                      close: bool = True) -> None:
        """
        Release a device from this orchestrator's control.

        Args:
            device_id: Identifier the device was attached under
            screen_off: Blank the screen on the way out
            close: Close the connection on the way out

        Design Contract:
            - Both flags off means "stop tracking but leave the hardware
              alone", which is what a configuration reload needs: the HID
              handle and its reader thread must survive
            - Safe to call for an unknown device_id
        """
        device = self._devices.pop(device_id, None)
        self._current_layouts.pop(device_id, None)

        if device is None:
            return

        device = _unwrap(device)

        try:
            if screen_off and hasattr(device, 'screen_off'):
                device.screen_off()
            if close and hasattr(device, 'close'):
                device.close()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error detaching device %s: %s", device_id, e)

        logger.debug("Detached device %s (screen_off=%s, close=%s)",
                     device_id, screen_off, close)

    @_serialized
    def run_exclusive(self, operation: Callable[[], Any]) -> Any:
        """
        Run an operation holding the device lock.

        Multi-packet HID transfers interleave if two threads write at once, so
        anything that talks to the device from outside the orchestrator must
        go through here rather than calling the device directly.

        Args:
            operation: Zero-argument callable performing the device work

        Returns:
            Whatever the operation returns
        """
        return operation()

    def register_layout(self, name: str, layout: Any) -> None:
        """
        Register a layout for use by devices.

        Args:
            name: Unique name for the layout
            layout: Layout object (from legacy Layout class)

        Design Contract:
            - Layouts must be registered before start()
            - Layout names must match LayoutManager rule targets
            - Can register layouts before or after start()
        """
        self._layouts[name] = layout
        logger.debug("Registered layout: %s", name)

    def set_default_brightness(self, brightness: int) -> None:
        """
        Set default brightness level.

        Args:
            brightness: Brightness level (0-100)

        Design Contract:
            - Used when restoring from lock
            - Applied to all devices
        """
        self._default_brightness = max(0, min(100, brightness))
        logger.debug("Default brightness set to: %s", self._default_brightness)

    def set_layout_changed_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """
        Register a callback fired whenever the active layout changes.

        Args:
            callback: Called with the new layout name, or None to clear

        Design Contract:
            - Called on whichever thread applied the layout, usually the
              window-poll thread; the callback must not touch a GUI directly
            - Exceptions raised by the callback are caught and logged
        """
        self._layout_changed_callback = callback

    def _notify_layout_changed(self, layout_name: str) -> None:
        """Fire the layout-changed callback, never letting it break a render."""
        if self._layout_changed_callback is None:
            return
        try:
            self._layout_changed_callback(layout_name)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error in layout changed callback: %s", e)

    def set_device_config_callback(self, callback: Any) -> None:
        """
        Set callback for device configuration (HYBRID).

        This callback is called when a device connects to apply configuration.
        Used for integrating ConfigLoader temporarily.

        Args:
            callback: Function(device_instance) -> None
        """
        self._device_config_callback = callback
        logger.debug("Device configuration callback registered")

    def start(self) -> bool:
        """
        Start orchestrator - initialize devices and start monitoring.

        Returns:
            True if started successfully, False otherwise

        Design Contract:
            - Initializes devices from registry
            - Starts system event monitoring
            - Applies default layout to all devices
            - Idempotent: safe to call multiple times
        """
        try:
            # Initialize devices from registry
            self._initialize_devices()

            # Start system event monitoring
            success = self._event_monitor.start_monitoring()

            # Security: if the system is already locked when the application
            # starts (device reconnected while screen was locked), apply the
            # locked state immediately so the device screen is never exposed.
            # poll_lock_state() is called here rather than relying on a D-Bus
            # change signal, which would never fire because there was no change.
            if self._devices and self._system.poll_lock_state():
                logger.warning(
                    "System is locked at startup — applying lock state immediately "
                    "(device reconnected while screen was locked)"
                )
                self._on_lock(SystemEvent.LOCK)
            elif self._devices:
                # Apply the context-aware layout for the current active window
                # immediately at startup, without waiting for the first poll cycle.
                # If window detection fails (e.g. display not yet ready), the
                # default layout applied during initialize() remains on-screen.
                logger.debug("Applying initial window-based layout at startup")
                self._on_window_changed(SystemEvent.WINDOW_CHANGED)

            if success:
                logger.info("DeviceOrchestrator started successfully")
            else:
                logger.warning("DeviceOrchestrator started but monitoring failed")

            return success

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error starting DeviceOrchestrator: %s", e)
            return False

    def stop(self, *, release_devices: bool = True) -> None:
        """
        Stop orchestrator and clean up resources.

        Args:
            release_devices: Blank and close the devices on the way out. A
                configuration reload passes False: it rebuilds everything
                above the device but keeps the HID handle, its reader thread
                and its workers alive, so the deck does not go dark on every
                Apply.

        Design Contract:
            - Stops system event monitoring
            - Cleans up device resources
            - Safe to call even if not started
            - Safe to call multiple times
        """
        try:
            self._event_monitor.stop_monitoring()
            self._cleanup_devices(release=release_devices)
            logger.info("DeviceOrchestrator stopped")
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error stopping DeviceOrchestrator: %s", e)

    def _initialize_devices(self) -> None:
        """
        Initialize all devices from registry.

        Called during start() to set up initial device state.

        Design:
        - Gets tracked devices from registry
        - Creates device instances (future: via factory)
        - Applies default layout
        """
        logger.debug("Initializing devices from registry")

        # Skip if no registry (simplified mode)
        if self._registry is None:
            logger.debug("No registry - skipping device initialization (simplified mode)")
            return

        # Get tracked devices from registry
        tracked_devices = self._registry.get_all_devices()

        if not tracked_devices:
            logger.warning("No devices found in registry")
            return

        for tracked_device in tracked_devices:
            device_id = tracked_device.device_info.serial
            logger.info("Initializing device: %s", device_id)

            # Store device (future: create actual device instance)
            self._devices[device_id] = tracked_device

            # HYBRID: Call device config callback if registered
            if self._device_config_callback and tracked_device.device_instance:
                try:
                    logger.debug("Calling device config callback for %s", device_id)
                    self._device_config_callback(tracked_device.device_instance)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.exception("Error in device config callback for %s: %s", device_id, e)

            # Apply default layout (tracked for orchestration)
            default_layout_name = self._layout_manager.get_default_layout()
            self._current_layouts[device_id] = default_layout_name

        logger.info("Initialized %d device(s)", len(self._devices))

    @_serialized
    def _cleanup_devices(self, release: bool = True) -> None:
        """
        Clean up device resources.

        Args:
            release: Blank and close each device. False stops tracking them
                but leaves the hardware connected (configuration reload).
        """
        logger.debug("Cleaning up %d device(s) (release=%s)", len(self._devices), release)

        for device_id in list(self._devices):
            self.detach_device(device_id, screen_off=release, close=release)

        self._devices.clear()
        self._current_layouts.clear()

    @_serialized
    def _on_lock(self, event: SystemEvent) -> None:
        """
        Handle lock event - turn off device screens and close connections.

        Args:
            event: LOCK event from SystemEventMonitor

        Design:
        - Turns off device screen
        - Closes connection to stop input processing
        - Tracks locked state
        - Called by SystemEventMonitor after verification
        """
        logger.info("🔒 Lock event received - turning off device screens and closing connections")

        self._is_locked = True

        # Turn off all device screens and close connections
        for device_id, device in self._devices.items():
            try:
                device = _unwrap(device)

                # Turn off screen physically if supported
                if hasattr(device, 'screen_off'):
                    device.screen_off()
                    logger.debug("Device %s screen turned off", device_id)
                elif hasattr(device, 'set_brightness'):
                    device.set_brightness(0)
                    logger.debug("Device %s brightness set to 0", device_id)
                else:
                    self._hardware.set_brightness(0)
                    logger.debug("Hardware brightness set to 0")

                # Close connection to safely stop processing inputs
                if hasattr(device, 'close'):
                    device.close()
                    logger.debug("Device %s connection closed", device_id)

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.exception("Error turning off device %s: %s", device_id, e)

    @_serialized
    def _on_unlock(self, event: SystemEvent) -> None:
        """
        Handle unlock event - restore device screens and connections.

        Args:
            event: UNLOCK event from SystemEventMonitor

        Design:
        - Reopens active connection to device
        - Turns screen back on
        - Restores brightness to default level
        - Reapplies current layout
        - Tracks unlocked state
        """
        logger.info("🔓 Unlock event received - restoring device screens and connections")

        self._is_locked = False

        # Restore device screens
        for device_id, device in self._devices.items():
            try:
                device = _unwrap(device)

                # Reopen connection
                success = True
                if hasattr(device, 'open'):
                    success = device.open()
                    if not success:
                        path_str = getattr(device, 'path', 'unknown')
                        logger.warning("Device %s failed to open at %s. Re-enumerating USB...", device_id, path_str)
                        vid = getattr(device, 'vendor_id', STREAMDOCK_VID)
                        pid = getattr(device, 'product_id', STREAMDOCK_293V3_PID)
                        devices = self._hardware.enumerate_devices(vid, pid)
                        
                        if devices:
                            new_info = devices[0]
                            logger.info("Found StreamDock at new path: %s", new_info.path)
                            # Update the device's internal path
                            device.path = new_info.path
                            success = device.open()
                            if success:
                                logger.info("Successfully reopened device %s at new path", device_id)
                            else:
                                logger.error("Failed to reopen device %s even with new path %s", device_id, new_info.path)
                        else:
                            logger.error("Could not find any StreamDock devices during re-enumeration")
                    else:
                        logger.debug("Device %s connection reopened successfully", device_id)

                if not success:
                    logger.warning("Skipping restoration for %s due to closed connection", device_id)
                    continue

                # Initialize hardware or turn on screen physically to break out of factory mode
                if hasattr(device, 'init'):
                    device.init(self._default_brightness)
                    logger.debug("Device %s initialized (exited factory mode)", device_id)
                elif hasattr(device, 'screen_on'):
                    device.screen_on()
                    logger.debug("Device %s screen turned on", device_id)

                # Restore brightness
                if hasattr(device, 'set_brightness'):
                    device.set_brightness(self._default_brightness)
                else:
                    self._hardware.set_brightness(self._default_brightness)
                logger.debug("Device %s brightness restored to %s", device_id, self._default_brightness)

                # Reapply current layout
                current_layout_name = self._current_layouts.get(device_id)
                if current_layout_name:
                    self._apply_layout(device_id, current_layout_name, force=True)

            except Exception as e:
                logger.exception("Error restoring device %s: %s", device_id, e)

    def _on_window_changed(self, event: SystemEvent) -> None:
        """
        Handle window change - select and apply appropriate layout.

        Args:
            event: WINDOW_CHANGED event from SystemEventMonitor

        Design:
        - Gets current window info from SystemInterface
        - Queries LayoutManager for layout selection
        - Applies layout if different from current
        - Skips if locked (no need to switch while screen is off)
        """
        logger.info("🔄 Window change event received.")

        # Skip layout changes while locked
        if self._is_locked:
            logger.debug("Skipping layout change - device is locked")
            return

        # Check if we have devices
        if not self._devices:
            logger.warning("⚠️  No devices registered in orchestrator (count: %d)", len(self._devices))
            return

        # Get current window info
        try:
            window_info = self._windows.get_active_window()

            if not window_info or window_info.class_ == "":
                logger.debug("No active window detected")
                return

            # Query layout manager for layout selection
            layout_name = self._layout_manager.select_layout(window_info)

            logger.info(
                "Window '%s' → Layout '%s'",
                window_info.class_, layout_name
            )

            # Apply layout to all devices if changed
            for device_id in self._devices:
                current = self._current_layouts.get(device_id)
                logger.debug("Device %s: current=%s, new=%s", device_id, current, layout_name)
                if current != layout_name:
                    self._apply_layout(device_id, layout_name)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error handling window change: %s", e)

    @_serialized
    def _apply_layout(self, device_id: str, layout_name: str, force: bool = False) -> None:
        """
        Apply layout to device.

        Args:
            device_id: Device identifier
            layout_name: Name of layout to apply
            force: If True, apply even if already current layout

        Design:
        - Looks up layout by name
        - Calls layout.apply() (legacy Layout class)
        - Updates current layout tracking
        - Logs layout changes
        """
        # Check if layout exists
        layout = self._layouts.get(layout_name)
        if not layout:
            logger.warning("Layout not found: %s", layout_name)
            return

        # Check if already current (unless forced)
        if not force:
            current = self._current_layouts.get(device_id)
            if current == layout_name:
                logger.debug("Layout '%s' already active on %s", layout_name, device_id)
                return

        # Apply layout
        try:
            layout.apply()
            self._current_layouts[device_id] = layout_name
            logger.info("✓ Applied layout '%s' to device %s", layout_name, device_id)
            self._notify_layout_changed(layout_name)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error applying layout '%s' to %s: %s", layout_name, device_id, e)

    def execute_action(self, action_type: str, parameter: Any, device_id: Optional[str] = None) -> None:
        """
        Execute an action by coordinating infrastructure and device operations.

        Args:
            action_type: Type of action to execute
            parameter: Action-specific parameter
            device_id: Optional device identifier for device-specific actions

        Design:
        - Coordinates between infrastructure layers
        - Delegates to appropriate interfaces
        - Handles action-specific logic

        Action Types:
        - System actions (KEY_PRESS, TYPE_TEXT, EXECUTE_COMMAND, DBUS)
        - Device actions (CHANGE_KEY_IMAGE, DEVICE_BRIGHTNESS_UP/DOWN)
        - Orchestration actions (CHANGE_LAYOUT, WAIT)
        """
        try:
            if action_type == "KEY_PRESS":
                self._system.send_key_combo(parameter)

            elif action_type == "WAIT":
                time.sleep(parameter)

            elif action_type == "CHANGE_LAYOUT":
                if device_id:
                    self._apply_layout(device_id, parameter)

            elif action_type == "DEVICE_BRIGHTNESS_UP":
                current = self._default_brightness
                self._default_brightness = min(100, current + 10)
                self._hardware.set_brightness(self._default_brightness)

            elif action_type == "DEVICE_BRIGHTNESS_DOWN":
                current = self._default_brightness
                self._default_brightness = max(0, current - 10)
                self._hardware.set_brightness(self._default_brightness)

            else:
                logger.warning("Unknown action type: %s", action_type)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("Error executing action %s: %s", action_type, e)

    def get_device_count(self) -> int:
        """
        Get number of managed devices.

        Returns:
            Number of devices
        """
        return len(self._devices)

    def get_current_layout(self, device_id: str) -> Optional[str]:
        """
        Get current layout for device.

        Args:
            device_id: Device identifier

        Returns:
            Current layout name or None
        """
        return self._current_layouts.get(device_id)

    def is_locked(self) -> bool:
        """
        Check if system is currently locked.

        Returns:
            True if locked, False otherwise
        """
        return self._is_locked
