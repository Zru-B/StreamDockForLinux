"""
Business logic layer for StreamDock.

This package provides pure business logic components with no infrastructure dependencies,
following the layered architecture design.
"""

from .system_event_monitor import SystemEventMonitor, SystemEvent

__all__ = ['SystemEventMonitor', 'SystemEvent']
