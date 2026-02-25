"""
System interface abstraction for StreamDock.

This module provides the abstract interface for operating system interactions,
including window management, input simulation, lock monitoring, and media controls.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Union

# Re-export WindowInfo from Models for convenience
from StreamDock.domain.Models import WindowInfo


class SystemInterface(ABC):
    """
    Abstract interface for operating system interactions.

    This interface abstracts all OS-level operations (window management,
    input simulation, D-Bus communication, etc.) from the business logic.

    Design Pattern: Strategy pattern - allows different OS implementations
    Testing: Can be mocked for testing business logic without real OS
    """

    # ==================== Tool Availability ====================

    @abstractmethod
    def is_kdotool_available(self) -> bool:
        """
        Check if kdotool is available (Wayland/KDE window manipulation).

        Returns:
            True if kdotool is installed and functional

        Design Contract:
            - Result should be cached for performance
            - Used to determine which tool to use for window operations
        """
        pass

    @abstractmethod
    def is_xdotool_available(self) -> bool:
        """
        Check if xdotool is available (X11 window manipulation).

        Returns:
            True if xdotool is installed and functional

        Design Contract:
            - Result should be cached for performance
            - Fallback when kdotool is not available
        """
        pass

    @abstractmethod
    def is_dbus_available(self) -> bool:
        """
        Check if dbus-send is available (D-Bus communication).

        Returns:
            True if dbus-send is available

        Design Contract:
            - Required for media controls and lock monitoring
        """
        pass

    @abstractmethod
    def is_pactl_available(self) -> bool:
        """
        Check if pactl is available (PulseAudio/PipeWire volume control).

        Returns:
            True if pactl is available

        Design Contract:
            - Required for volume control actions
        """
        pass

    # ==================== Window Operations ====================

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """
        Get information about the currently active window.

        Returns:
            WindowInfo object with window details, or None if failed

        Design Contract:
            - Should try kdotool first, fallback to xdotool
            - Returns None if no tools available or window detection fails
            - WindowInfo should include title, class_name, and method used
        """
        pass

    @abstractmethod
    def search_window_by_class(self, class_name: str) -> Optional[str]:
        """
        Search for a window by its class name.

        Args:
            class_name: Window class name to search for

        Returns:
            Window ID if found, None otherwise

        Design Contract:
            - Should use available tool (kdotool or xdotool)
            - Returns first matching window
        """
        pass

    @abstractmethod
    def activate_window(self, window_id: str) -> bool:
        """
        Activate (focus) a window by its ID.

        Args:
            window_id: Window ID to activate

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Should use available tool (kdotool or xdotool)
            - Returns False if no tools available
        """
        pass

    # ==================== Input Simulation ====================

    @abstractmethod
    def send_key_combo(self, key_sequence: str) -> bool:
        """
        Send a keyboard shortcut.

        Args:
            key_sequence: Key combination (e.g., 'ctrl+c', 'alt+tab')

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Uses xdotool or kdotool depending on availability
            - Returns False if no input tools available
        """
        pass

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """
        Type text into the active window.

        Args:
            text: Text to type

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Uses xdotool for text input
            - Handles special characters properly
        """
        pass

    @abstractmethod
    def execute_command(self, command: str) -> bool:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute

        Returns:
            True if command executed successfully, False otherwise

        Design Contract:
            - Runs command in background (non-blocking)
            - Returns False if command fails
            - Logs errors but doesn't raise exceptions
        """
        pass

    # ==================== Lock/Unlock Monitoring ====================

    @abstractmethod
    def poll_lock_state(self) -> bool:
        """
        Poll the current screen lock state.

        Returns:
            True if screen is locked, False if unlocked

        Design Contract:
            - Queries D-Bus screensaver interface
            - Tries KDE interface first, fallbacks to GNOME
            - Returns False on error (assume unlocked if can't determine)
        """
        pass

    @abstractmethod
    def start_lock_monitor(self, callback: Callable[[bool], None]) -> bool:
        """
        Start monitoring screen lock/unlock events.

        Args:
            callback: Function to call when lock state changes.
                     Called with True for lock, False for unlock.

        Returns:
            True if monitoring started successfully, False otherwise

        Design Contract:
            - Uses D-Bus signal monitoring
            - Callback should be called on separate thread
            - Only one monitor can be active at a time
        """
        pass

    @abstractmethod
    def stop_lock_monitor(self) -> None:
        """
        Stop monitoring lock/unlock events.

        Design Contract:
            - Safe to call even if monitoring not started
            - Cleans up D-Bus connections
            - Stops background thread
        """
        pass

    # ==================== Media Controls ====================

    @abstractmethod
    def send_media_key(self, key: str) -> bool:
        """
        Send a media control key.

        Args:
            key: Media key name ('PlayPause', 'Next', 'Previous', 'Stop', 'Play', 'Pause')

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Uses D-Bus MPRIS interface when available
            - Fallback to xdotool/kdotool key simulation
            - Returns False if no method available
        """
        pass

    @abstractmethod
    def set_volume(self, volume: Union[int, str]) -> bool:
        """
        Set system volume level.

        Args:
            volume: Volume level (0-100) or relative adjustment (e.g., "+5%", "-5%")

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Uses pactl (PulseAudio/PipeWire)
            - Clamps absolute volume to 0-100 range
            - Supports relative adjustments as strings
            - Returns False if pactl not available
        """
        pass

    @abstractmethod
    def toggle_mute(self) -> bool:
        """
        Toggle system mute state.

        Returns:
            True if successful, False otherwise

        Design Contract:
            - Uses pactl (PulseAudio/PipeWire)
            - Returns False if pactl not available
        """
        pass
