"""
Business logic layer for StreamDock.

This package provides pure business logic components with no infrastructure dependencies,
following the layered architecture design.
"""

from .layout_manager import LayoutManager, LayoutRule
from .system_event_monitor import SystemEvent, SystemEventMonitor

__all__ = ['SystemEventMonitor', 'SystemEvent', 'LayoutManager', 'LayoutRule']
