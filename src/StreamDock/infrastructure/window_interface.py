"""
Abstract interface for window management operations.

Defines the OS-agnostic contract for querying and controlling windows.
Business-logic code should depend on this interface, never on concrete
implementations such as LinuxWindowManager.
"""

from abc import ABC, abstractmethod
from typing import Optional

from StreamDock.domain.Models import WindowInfo


class WindowInterface(ABC):
    """
    Abstract base for window management.

    Defines three operations that any platform implementation must support:
      - Querying the currently focused window
      - Searching for a window by its WM class
      - Bringing a window to the foreground

    Design pattern: Strategy / Dependency Injection.
    Concrete implementations live alongside this interface in the
    ``infrastructure`` layer (e.g. ``LinuxWindowManager``).
    """

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """
        Return information about the currently focused window.

        Contract:
          - Must use non-interactive OS APIs only (no mouse-click methods).
          - Returns ``None`` if the query fails or no window is focused.
          - The returned ``WindowInfo.method`` field identifies the tool used.
        """

    @abstractmethod
    def search_window_by_class(self, class_name: str) -> Optional[str]:
        """
        Search for a window by its WM_CLASS name.

        Args:
            class_name: The window class to search for (case-insensitive).

        Returns:
            The window ID of the first match, or ``None`` if not found.
        """

    @abstractmethod
    def activate_tray_app(self, app_name: str) -> bool:
        """
        Attempt to activate a minimized-to-tray application directly.

        Args:
            app_name: The application identifier to match on DBus or tray properties.

        Returns:
            ``True`` if a tray icon was found and activated, ``False`` otherwise.
        """

    @abstractmethod
    def search_window_by_name(self, name: str) -> Optional[str]:
        """
        Search for a window by its visible title (name), ignoring class.

        This is usually a fallback when searching by class fails.

        Args:
            name: The window title string (or substring) to search for
        Returns:
            OS-specific window ID as string if found, None otherwise
        """
        pass

    @abstractmethod
    def activate_window(self, window_id: str) -> bool:
        """
        Bring the window identified by *window_id* to the foreground.

        Args:
            window_id: Platform-specific window identifier.

        Returns:
            ``True`` on success, ``False`` otherwise.
        """
