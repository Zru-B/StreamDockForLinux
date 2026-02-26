"""
Abstract interfaces for system-level operations.

This module defines the OS-agnostic contracts for interacting with the
underlying system (e.g., simulating input, controlling volume, checking
process status).

Window-specific operations are separated into ``WindowInterface``.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

# Re-export WindowInfo for convenience since both interfaces use it
from StreamDock.domain.Models import WindowInfo


class SystemInterface(ABC):
    """
    Abstract base class defining the hardware-agnostic OS interface.

    This interface provides methods for simulating input, controlling
    media/volume, monitoring screen lock state, and checking process status.
    """

    # ==================== Process / Execution ====================

    @abstractmethod
    def execute_command(self, command: str) -> bool:
        """
        Execute a shell command asynchronously in the background.

        Args:
            command: The exact shell command string to execute
        Returns:
            True if successfully started, False on failure
        """
        pass

    @abstractmethod
    def is_process_running(self, process_name: str) -> bool:
        """
        Check if a process with exactly the given name is currently running.

        Args:
            process_name: The exact name of the executable (e.g., 'firefox')
        Returns:
            True if at least one instance is running, False otherwise.
        """
        pass

    # ==================== Input Simulation ====================

    @abstractmethod
    def send_key_combo(self, key_sequence: str) -> bool:
        """
        Send a sequence of key presses to the active window.

        Args:
            key_sequence: A plus-separated string of keys (e.g., 'ctrl+c')
        Returns:
            True if sent successfully, False on failure
        """
        pass

    @abstractmethod
    def type_text(self, text: str) -> bool:
        """
        Type a string of text into the active window.

        Args:
            text: The plain text string to type
        Returns:
            True if typed successfully, False on failure
        """
        pass

    # ==================== Lock Monitoring ====================

    @abstractmethod
    def poll_lock_state(self) -> bool:
        """
        Synchronously check if the screen is currently locked.

        Returns:
            True if locked, False if unlocked or unknown
        """
        pass

    @abstractmethod
    def start_lock_monitor(self, callback: Callable[[bool], None]) -> bool:
        """
        Start monitoring for screen lock/unlock events in the background.

        Args:
            callback: A function that accepts a boolean (True=locked)
        Returns:
            True if monitoring started successfully, False on failure
        """
        pass

    @abstractmethod
    def stop_lock_monitor(self) -> None:
        """Stop the background lock monitor if running."""
        pass

    # ==================== Media Controls ====================

    @abstractmethod
    def send_media_key(self, key: str) -> bool:
        """
        Send a specific media control key press.

        Args:
            key: One of 'PlayPause', 'Next', 'Previous', 'Stop', etc.
        Returns:
            True if sent successfully, False on failure
        """
        pass

    @abstractmethod
    def set_volume(self, volume: int | str) -> bool:
        """
        Set the system audio volume.

        Args:
            volume: An integer percentage (0-100) or a relative string
                    (e.g., '+5%', '-10%')
        Returns:
            True if volume was changed, False on failure
        """
        pass

    @abstractmethod
    def toggle_mute(self) -> bool:
        """
        Toggle the system audio mute state.

        Returns:
            True if successfully toggled, False on failure
        """
        pass
