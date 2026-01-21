"""
Orchestration layer for StreamDock.

This package provides orchestration components that coordinate between
infrastructure, business logic, and device management.
"""

from .device_orchestrator import DeviceOrchestrator

__all__ = ['DeviceOrchestrator']
