"""
Tests for StreamDock simulation mode.

Simulation mode allows testing window detection without actual window switching.
"""
import os

import pytest

from StreamDock.window_monitor import WindowMonitor

SIMULATION_FILE = "/tmp/streamdock_fake_window"


@pytest.fixture
def simulate_window():
    """
    Fixture to simulate window focus changes for testing WindowMonitor.
    
    Usage in tests:
        def test_something(simulate_window):
            simulate_window("Firefox")
            simulate_window("New Tab - Firefox|Firefox")
    
    The fixture automatically cleans up the simulation file after the test.
    """
    def _simulate(window_info: str):
        """
        Write window info to simulation file.
        
        Args:
            window_info: Either "Application" or "Title|Class" format
        """
        with open(SIMULATION_FILE, "w") as f:
            f.write(window_info)
    
    yield _simulate
    
    # Cleanup after test
    if os.path.exists(SIMULATION_FILE):
        os.remove(SIMULATION_FILE)


@pytest.fixture
def clear_simulation():
    """Remove simulation file if it exists."""
    if os.path.exists(SIMULATION_FILE):
        os.remove(SIMULATION_FILE)
    yield
    if os.path.exists(SIMULATION_FILE):
        os.remove(SIMULATION_FILE)


def test_simulation_mode_basic(simulate_window):
    """Test that simulation mode reads from file."""
    # Create monitor in simulation mode
    monitor = WindowMonitor(poll_interval=0.1, simulation_mode=True)
    
    # Simulate Firefox window
    simulate_window("Firefox")
    
    # Get window info
    info = monitor.get_active_window_info()
    
    assert info is not None
    assert info.class_name == "Firefox"
    assert info.method == "simulation"


def test_simulation_mode_with_title(simulate_window):
    """Test simulation mode with title|class format."""
    monitor = WindowMonitor(simulation_mode=True)
    
    # Use detailed format
    simulate_window("New Tab - Firefox|Mozilla Firefox")
    
    info = monitor.get_active_window_info()
    
    assert info is not None
    assert info.title == "New Tab - Firefox"
    assert info.class_name == "Mozilla Firefox"
    assert info.method == "simulation"


def test_simulation_mode_no_file(clear_simulation):
    """Test that simulation mode returns None when file doesn't exist."""
    monitor = WindowMonitor(simulation_mode=True)
    
    info = monitor.get_active_window_info()
    
    assert info is None
