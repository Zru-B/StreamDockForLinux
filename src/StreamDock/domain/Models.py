"""
Data models for StreamDock window monitoring.

This module contains dataclass definitions used by the WindowMonitor
for window detection and application pattern matching.
"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WindowInfo:
    """
    Information about a detected window.

    Attributes:
        title: The window title
        class: The window class/application name (simplified from class_name)
        raw: Raw output from the detection method
        method: Detection method used (kdotool, kwin_scripting, etc.)
        window_id: Unique window identifier (optional)
        pid: Process ID (optional, for debugging only)
        timestamp: Time of detection (auto-generated)
    """
    title: str
    class_: str  # Using class_ to avoid Python keyword conflict
    raw: str = ""
    method: str = "unknown"
    window_id: Optional[str] = None
    pid: Optional[int] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def class_name(self) -> str:
        """Backward compatibility property for class_name."""
        return self.class_

    def __eq__(self, other) -> bool:
        """
        Compare windows based on title, class, and ID only.
        PID is NOT included as different instances of same app should match.
        """
        if not isinstance(other, WindowInfo):
            return False
        return (
            self.title == other.title and
            self.class_ == other.class_ and
            self.window_id == other.window_id
        )

    def __hash__(self) -> int:
        """Hash based on title, class, and ID only (not PID)."""
        return hash((self.title, self.class_, self.window_id))

    def is_valid(self) -> bool:
        """Check if window info contains valid data."""
        return bool(self.title or self.class_)

    def get(self, key: str) -> str:
        """
        Get attribute value by key name for backward compatibility.

        Supports both 'class' and 'class_name' keys.
        """
        if key == "title":
            return self.title
        
        if key == "class_name" or key == "class":
            return self.class_
        elif key == "raw":
            return self.raw
        elif key == "method":
            return self.method
        elif key == "window_id":
            return self.window_id or ""
        elif key == "pid":
            return str(self.pid) if self.pid else ""
        else:
            raise KeyError(key)

    def to_dict(self) -> dict:
        """Convert to dictionary for backward compatibility."""
        return {
            'title': self.title,
            'class': self.class_,
            'class_name': self.class_,  # Duplicate for compatibility
            'raw': self.raw,
            'window_id': self.window_id,
            'pid': self.pid,
            'method': self.method,
            'timestamp': self.timestamp
        }
