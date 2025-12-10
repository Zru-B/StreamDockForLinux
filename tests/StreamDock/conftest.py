import pytest
import sys
import os
from unittest.mock import MagicMock

# Add src to python path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../src')))

@pytest.fixture
def mock_device():
    """Fixture that returns a mock StreamDock device."""
    device = MagicMock()
    device.id.return_value = "mock_device_id"
    device.path = b"mock_path"
    device.vendor_id = 0x1234
    device.product_id = 0x5678
    
    # Mock close/open methods
    device.open = MagicMock()
    device.close = MagicMock()
    device.init = MagicMock()
    device.clearAllIcon = MagicMock()
    
    return device

@pytest.fixture
def mock_window_monitor():
    """Fixture that returns a mock WindowMonitor."""
    monitor = MagicMock()
    monitor.running = False
    return monitor
