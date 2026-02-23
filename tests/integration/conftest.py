"""Shared fixtures for integration tests."""
import pytest
from unittest.mock import Mock
from StreamDock.infrastructure.hardware_interface import DeviceInfo
from StreamDock.infrastructure.device_registry import DeviceRegistry
from StreamDock.business_logic.layout_manager import LayoutManager
from StreamDock.business_logic.system_event_monitor import SystemEventMonitor
from StreamDock.domain.Models import WindowInfo


@pytest.fixture
def mock_hardware():
    """Mock hardware interface for integration tests."""
    hardware = Mock()
    hardware.enumerate_devices = Mock(return_value=[])
    hardware.open_device = Mock(return_value=True)
    hardware.close_device = Mock()
    hardware.set_brightness = Mock()
    hardware.send_image = Mock()
    hardware.clear_device = Mock()
    hardware.is_device_connected = Mock(return_value=True)
    return hardware


@pytest.fixture
def mock_system():
    """Mock system interface for integration tests."""
    system = Mock()
    system.get_active_window = Mock(return_value=WindowInfo(
        class_="TestApp",
        title="Test Window",
        raw="TestApp"
    ))
    system.poll_lock_state = Mock(return_value=False)
    return system


@pytest.fixture
def mock_registry():
    """Mock device registry for integration tests."""
    registry = Mock()
    registry.get_all_devices = Mock(return_value=[])
    return registry


@pytest.fixture
def registry(mock_hardware):
    """Device registry with mock hardware."""
    return DeviceRegistry(hardware_interface=mock_hardware)


@pytest.fixture
def sample_device_info():
    """Sample device info for testing."""
    return DeviceInfo(
        vendor_id=0x6603,
        product_id=0x1006,
        serial_number="ABC123",
        path="1-2.1:1.0",
        manufacturer="TestMfg",
        product="TestDevice"
    )


@pytest.fixture
def layout_manager():
    """Layout manager with default layout."""
    return LayoutManager(default_layout_name="default")


@pytest.fixture
def event_monitor(mock_system):
    """System event monitor."""
    return SystemEventMonitor(
        system_interface=mock_system,
        verification_delay=0.1
    )
