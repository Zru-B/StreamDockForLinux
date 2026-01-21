"""
Device orchestration - Coordinates all layers.

This module provides the DeviceOrchestrator which is the central coordinator
that connects infrastructure, business logic, and device management.
"""

import logging
import time
from typing import Any, Dict, Optional

from StreamDock.business_logic import SystemEventMonitor, SystemEvent, LayoutManager
from StreamDock.infrastructure import HardwareInterface, SystemInterface, DeviceRegistry
from StreamDock.Models import WindowInfo


logger = logging.getLogger(__name__)


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
    
    def __init__(self,
                 hardware: HardwareInterface,
                 system: SystemInterface,
                 registry: DeviceRegistry,
                 event_monitor: SystemEventMonitor,
                 layout_manager: LayoutManager):
        """
        Initialize orchestrator with all dependencies.
        
        Args:
            hardware: Hardware abstraction for device communication
            system: System abstraction for OS interactions
            registry: Device registry for tracking devices
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
        self._registry = registry
        self._event_monitor = event_monitor
        self._layout_manager = layout_manager
        
        # State management
        self._devices: Dict[str, Any] = {}  # device_id -> device instance
        self._current_layouts: Dict[str, str] = {}  # device_id -> layout_name
        self._layouts: Dict[str, Any] = {}  # layout_name -> Layout object
        self._default_brightness: int = 100
        self._is_locked: bool = False
        
        # Register event handlers with SystemEventMonitor
        self._event_monitor.register_handler(SystemEvent.LOCK, self._on_lock)
        self._event_monitor.register_handler(SystemEvent.UNLOCK, self._on_unlock)
        self._event_monitor.register_handler(SystemEvent.WINDOW_CHANGED, self._on_window_changed)
        
        logger.debug("DeviceOrchestrator initialized with dependencies")
    
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
        logger.debug(f"Registered layout: {name}")
    
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
        logger.debug(f"Default brightness set to: {self._default_brightness}")
    
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
            
            if success:
                logger.info("DeviceOrchestrator started successfully")
            else:
                logger.warning("DeviceOrchestrator started but monitoring failed")
            
            return success
        
        except Exception as e:
            logger.exception(f"Error starting DeviceOrchestrator: {e}")
            return False
    
    def stop(self) -> None:
        """
        Stop orchestrator and clean up resources.
        
        Design Contract:
            - Stops system event monitoring
            - Cleans up device resources
            - Safe to call even if not started
            - Safe to call multiple times
        """
        try:
            self._event_monitor.stop_monitoring()
            self._cleanup_devices()
            logger.info("DeviceOrchestrator stopped")
        except Exception as e:
            logger.exception(f"Error stopping DeviceOrchestrator: {e}")
    
    def _initialize_devices(self) -> None:
        """
        Initialize all devices from registry.
        
        Called during start() to set up initial device state.
        
        Design:
        - Gets tracked devices from registry
        - Creates device instances (future: via factory)
        - Applies default layout
        - Sets default brightness
        """
        logger.debug("Initializing devices from registry")
        
        # Get tracked devices from registry
        tracked_devices = self._registry.get_all_devices()
        
        if not tracked_devices:
            logger.warning("No devices found in registry")
            return
        
        for tracked_device in tracked_devices:
            device_id = tracked_device.device_info.serial
            logger.info(f"Initialized device: {device_id}")
            
            # Store device (future: create actual device instance)
            self._devices[device_id] = tracked_device
            
            # Apply default layout
            default_layout_name = self._layout_manager.get_default_layout()
            self._current_layouts[device_id] = default_layout_name
        
        logger.info(f"Initialized {len(self._devices)} device(s)")
    
    def _cleanup_devices(self) -> None:
        """
        Clean up device resources.
        
        Called during stop() to release resources.
        """
        logger.debug(f"Cleaning up {len(self._devices)} device(s)")
        self._devices.clear()
        self._current_layouts.clear()
    
    def _on_lock(self, event: SystemEvent) -> None:
        """
        Handle lock event - turn off device screens.
        
        Args:
            event: LOCK event from SystemEventMonitor
            
        Design:
        - Sets brightness to 0 for all devices
        - Tracks locked state
        - Called by SystemEventMonitor after verification
        """
        logger.info("🔒 Lock event received - turning off device screens")
        
        self._is_locked = True
        
        # Turn off all device screens
        for device_id in self._devices:
            try:
                self._hardware.set_brightness(0)
                logger.debug(f"Device {device_id} screen turned off")
            except Exception as e:
                logger.exception(f"Error turning off device {device_id}: {e}")
    
    def _on_unlock(self, event: SystemEvent) -> None:
        """
        Handle unlock event - restore device screens.
        
        Args:
            event: UNLOCK event from SystemEventMonitor
            
        Design:
        - Restores brightness to default level
        - Reapplies current layout
        - Tracks unlocked state
        """
        logger.info("🔓 Unlock event received - restoring device screens")
        
        self._is_locked = False
        
        # Restore device screens
        for device_id in self._devices:
            try:
                # Restore brightness
                self._hardware.set_brightness(self._default_brightness)
                logger.debug(f"Device {device_id} brightness restored to {self._default_brightness}")
                
                # Reapply current layout
                current_layout_name = self._current_layouts.get(device_id)
                if current_layout_name:
                    self._apply_layout(device_id, current_layout_name, force=True)
            
            except Exception as e:
                logger.exception(f"Error restoring device {device_id}: {e}")
    
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
        # Skip layout changes while locked
        if self._is_locked:
            logger.debug("Skipping layout change - device is locked")
            return
        
        # Get current window info
        try:
            window_info = self._system.get_active_window()
            
            if not window_info:
                logger.debug("No active window detected")
                return
            
            # Query layout manager for layout selection
            layout_name = self._layout_manager.select_layout(window_info)
            
            logger.debug(
                f"Window '{window_info.class_}' → Layout '{layout_name}'"
            )
            
            # Apply layout to all devices if changed
            for device_id in self._devices:
                current = self._current_layouts.get(device_id)
                if current != layout_name:
                    self._apply_layout(device_id, layout_name)
        
        except Exception as e:
            logger.exception(f"Error handling window change: {e}")
    
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
            logger.warning(f"Layout not found: {layout_name}")
            return
        
        # Check if already current (unless forced)
        if not force:
            current = self._current_layouts.get(device_id)
            if current == layout_name:
                logger.debug(f"Layout '{layout_name}' already active on {device_id}")
                return
        
        # Apply layout
        try:
            layout.apply()
            self._current_layouts[device_id] = layout_name
            logger.info(f"✓ Applied layout '{layout_name}' to device {device_id}")
        
        except Exception as e:
            logger.exception(f"Error applying layout '{layout_name}' to {device_id}: {e}")
    
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
                logger.warning(f"Unknown action type: {action_type}")
        
        except Exception as e:
            logger.exception(f"Error executing action {action_type}: {e}")
    
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
