"""
Data models for StreamDock window monitoring.

This module contains dataclass definitions used by the WindowMonitor
for window detection and application pattern matching.
"""

from dataclasses import dataclass


@dataclass
class WindowInfo:
    """
    Information about a detected window.
    
    Attributes:
        title: The window title
        class_name: The window class/application name
        raw: Raw output from the detection method
        method: Detection method used (kdotool, kwin_scripting, etc.)
    """
    title: str
    class_name: str
    raw: str
    method: str


@dataclass
class AppPattern:
    """
    Pattern definition for application detection and normalization.
    
    Attributes:
        keywords: List of keywords to search for in class name or title (case-insensitive)
        normalized_name: The normalized application name to return when matched
        exact_matches: List of exact strings to match against class name (case-sensitive)
    """
    keywords: list[str]
    normalized_name: str
    exact_matches: list[str] | None = None

    def __init__(self, keywords: list[str], normalized_name: str, exact_matches: list[str] | None = None):
        self.keywords = keywords
        self.normalized_name = normalized_name
        self.exact_matches = exact_matches

    def match(self, class_name: str, title: str = "") -> bool:
        """
        Check if the pattern matches the given class name and title.
        
        :param class_name: Raw window class name
        :param title: Optional window title for additional context
        :return: True if the pattern matches, False otherwise
        """
        class_lower = class_name.lower()
        title_lower = title.lower() if title else ""
        
        # Check exact matches first (case-sensitive)
        if self.exact_matches:
            if class_name in self.exact_matches:
                return True
        
        # Check keywords in both class name and title (case-insensitive)
        for keyword in self.keywords:
            if keyword in class_lower or keyword in title_lower:
                return True
        
        return False

    def __str__(self) -> str:
        return f"{self.normalized_name} ({', '.join(self.keywords)})"

