"""
Application layer for StreamDock.

This package provides application-level components for configuration
management and bootstrap.
"""

from .configuration_manager import ConfigurationManager, StreamDockConfig

__all__ = ['ConfigurationManager', 'StreamDockConfig']
