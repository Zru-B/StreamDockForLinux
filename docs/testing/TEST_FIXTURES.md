# Test Fixtures and Mocks

## Overview

This document provides reusable test fixtures, mock objects, and common test data for testing the StreamDock layered architecture. Fixtures are organized by layer to promote consistency and reduce duplication.

---

## Infrastructure Layer Fixtures

### Mock HardwareInterface

```python
# tests/fixtures/infrastructure.py
import pytest
from unittest.mock import Mock, MagicMock
from StreamDock.infrastructure.hardware_interface import HardwareInterface, DeviceInfo
from StreamDock.infrastructure.system_interface import SystemInterface

@pytest.fixture
def mock_hardware_interface():
    """Mock HardwareInterface for testing components that depend on hardware."""
    mock = Mock(spec=HardwareInterface)
    
    # Configure common return values
    mock.enumerate_devices.return_value = [
        DeviceInfo(vendor_id=0x1234, product_id=0x5678, serial_number='TEST001', path='/dev/hidraw0')
    ]
    mock.open_device.return_value = Mock(name='device_handle')
    mock.read_input.return_value = None  # No input by default
    
    return mock

@pytest.fixture
def mock_device_handle():
    """Mock device handle for low-level operations."""
    handle = Mock()
    handle.is_valid = True
    handle.path = '/dev/hidraw0'
    return handle
```

### Mock SystemInterface

```python
@pytest.fixture
def mock_system_interface():
    """Mock SystemInterface for testing business logic and orchestration."""
    mock = Mock(spec=SystemInterface)
    
    # Tool availability
    mock.is_kdotool_available.return_value = True
    mock.is_xdotool_available.return_value = False
    mock.is_dbus_available.return_value = True
    
    # Default window info
    mock.get_active_window.return_value = WindowInfo(
        class_name='unknown',
        title='Unknown Window',
        is_focused=True
    )
    
    # Lock state
    mock.poll_lock_state.return_value = False  # Unlocked by default
    
    return mock
```

### Mock DeviceRegistry

```python
@pytest.fixture
def mock_device_registry():
    """Mock DeviceRegistry for orchestration testing."""
    mock = Mock()
    
    # Default: one device discovered
    mock.discover_devices.return_value = ['test_device_1']
    mock.is_device_connected.return_value = True
    mock.get_device_handle.return_value = Mock(name='test_handle')
    
    return mock
```

---

## Business Logic Layer Fixtures

### Sample Layouts

```python
# tests/fixtures/business.py
import pytest
from StreamDock.business_logic.layout_config import LayoutConfig, KeyConfig, WindowRule

@pytest.fixture
def sample_layouts():
    """Sample layout configurations for testing."""
    return {
        'default': LayoutConfig(
            name='default',
            keys=[
                KeyConfig(key_number=0, text='Home', on_press_actions=[('CHANGE_LAYOUT', 'media')]),
                KeyConfig(key_number=1, text='Firefox', on_press_actions=[('APPLICATION', 'firefox')]),
                KeyConfig(key_number=2, text='Terminal', on_press_actions=[('COMMAND', 'gnome-terminal')]),
            ],
            clear_all=False
        ),
        'media': LayoutConfig(
            name='media',
            keys=[
                KeyConfig(key_number=0, text='Play/Pause', on_press_actions=[('MEDIA_CONTROL', 'PlayPause')]),
                KeyConfig(key_number=1, text='Next', on_press_actions=[('MEDIA_CONTROL', 'Next')]),
                KeyConfig(key_number=2, text='Back', on_press_actions=[('CHANGE_LAYOUT', 'default')]),
            ],
            clear_all=False
        ),
        'firefox': LayoutConfig(
            name='firefox',
            keys=[
                KeyConfig(key_number=0, text='New Tab', on_press_actions=[('KEY_COMBO', 'ctrl+t')]),
                KeyConfig(key_number=1, text='Close Tab', on_press_actions=[('KEY_COMBO', 'ctrl+w')]),
                KeyConfig(key_number=2, text='Default', on_press_actions=[('CHANGE_LAYOUT', 'default')]),
            ],
            clear_all=False
        )
    }

@pytest.fixture
def empty_layout():
    """Empty layout for edge case testing."""
    return LayoutConfig(name='empty', keys=[], clear_all=True)
```

### Sample Window Rules

```python
@pytest.fixture
def sample_window_rules():
    """Sample window matching rules."""
    return [
        WindowRule(pattern='firefox', layout_name='firefox', match_field='class', is_regex=False),
        WindowRule(pattern='chrome', layout_name='firefox', match_field='class', is_regex=False),
        WindowRule(pattern='spotify', layout_name='media', match_field='class', is_regex=False),
        WindowRule(pattern='.*', layout_name='default', match_field='class', is_regex=True),  # Catch-all
    ]
```

### Mock Components

```python
@pytest.fixture
def mock_layout_manager():
    """Mock LayoutManager for orchestration testing."""
    mock = Mock()
    mock.get_current_layout.return_value = 'default'
    mock.select_layout_for_window.return_value = None
    mock.render_layout.return_value = None
    return mock

@pytest.fixture
def mock_action_executor():
    """Mock ActionExecutor for orchestration testing."""
    mock = Mock()
    mock.execute_action.return_value = None
    return mock

@pytest.fixture
def mock_system_event_monitor():
    """Mock SystemEventMonitor for orchestration testing."""
    mock = Mock()
    mock.start_monitoring.return_value = None
    mock.stop_monitoring.return_value = None
    return mock
```

---

## Orchestration Layer Fixtures

### DeviceState

```python
# tests/fixtures/orchestration.py
import pytest
from StreamDock.orchestration.device_orchestrator import DeviceState, PowerMode

@pytest.fixture
def sample_device_state():
    """Sample device state for testing."""
    return DeviceState(
        current_layout='default',
        saved_brightness=80,
        power_mode=PowerMode.ACTIVE
    )

@pytest.fixture
def locked_device_state():
    """Device state during screen lock."""
    return DeviceState(
        current_layout='default',
        saved_brightness=80,
        power_mode=PowerMode.STANDBY
    )
```

### Full Orchestrator Setup

```python
@pytest.fixture
def orchestrator_setup(mock_device_registry, mock_layout_manager, 
                       mock_action_executor, mock_system_event_monitor):
    """Complete orchestrator setup with all mocked dependencies."""
    from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator
    
    orchestrator = DeviceOrchestrator(
        device_registry=mock_device_registry,
        layout_manager=mock_layout_manager,
        action_executor=mock_action_executor,
        event_monitor=mock_system_event_monitor
    )
    
    # Return orchestrator with mocks for verification
    return {
        'orchestrator': orchestrator,
        'registry': mock_device_registry,
        'layouts': mock_layout_manager,
        'actions': mock_action_executor,
        'events': mock_system_event_monitor
    }
```

---

## Application Layer Fixtures

### Sample Configuration Files

```python
# tests/fixtures/application.py
import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def minimal_config_file(tmp_path):
    """Minimal valid configuration file."""
    config_file = tmp_path / "config.yml"
    config_file.write_text("""
layouts:
  default:
    keys:
      - key_number: 0
        text: "Test"
        on_press:
          - action: COMMAND
            command: "echo test"
""")
    return str(config_file)

@pytest.fixture
def full_config_file(tmp_path):
    """Complete configuration with all features."""
    config_file = tmp_path / "config.yml"
    config_file.write_text("""
device:
  brightness: 80
  default_layout: default

layouts:
  default:
    keys:
      - key_number: 0
        text: "Home"
        on_press:
          - action: CHANGE_LAYOUT
            layout: media
      - key_number: 1
        image: "/path/to/image.png"
        on_press:
          - action: APPLICATION
            application: firefox

  media:
    keys:
      - key_number: 0
        text: "Play"
        on_press:
          - action: MEDIA_CONTROL
            control: PlayPause

window_rules:
  - pattern: firefox
    layout: firefox
    match_field: class
""")
    return str(config_file)

@pytest.fixture
def invalid_config_file(tmp_path):
    """Invalid YAML for testing error handling."""
    config_file = tmp_path / "bad_config.yml"
    config_file.write_text("""
invalid: yaml: content:
  - missing: quotes:
""")
    return str(config_file)
```

---

## Common Test Data

### Window Information

```python
# tests/fixtures/common.py
import pytest
from StreamDock.domain.Models import WindowInfo

@pytest.fixture
def firefox_window():
    """Firefox window for testing layout switching."""
    return WindowInfo(
        class_name='firefox',
        title='Mozilla Firefox',
        is_focused=True,
        pid=12345
    )

@pytest.fixture
def spotify_window():
    """Spotify window for testing media layout."""
    return WindowInfo(
        class_name='spotify',
        title='Spotify - Song Name',
        is_focused=True,
        pid=54321
    )

@pytest.fixture
def terminal_window():
    """Terminal window for testing."""
    return WindowInfo(
        class_name='gnome-terminal',
        title='Terminal',
        is_focused=True,
        pid=99999
    )
```

### Device Information

```python
@pytest.fixture
def stream_deck_device_info():
    """Standard Stream Deck device info."""
    return DeviceInfo(
        vendor_id=0x0fd9,
        product_id=0x0063,
        serial_number='AL00Z1A00001',
        path='/dev/hidraw0'
    )

@pytest.fixture
def multiple_devices():
    """Multiple device scenario."""
    return [
        DeviceInfo(vendor_id=0x0fd9, product_id=0x0063, serial_number='DEVICE001', path='/dev/hidraw0'),
        DeviceInfo(vendor_id=0x0fd9, product_id=0x0063, serial_number='DEVICE002', path='/dev/hidraw1'),
    ]
```

---

## Test Scenarios (Fixtures)

### Lock/Unlock Scenario

```python
@pytest.fixture
def lock_unlock_scenario(orchestrator_setup):
    """Pre-configured scenario for testing lock/unlock cycle."""
    setup = orchestrator_setup
    orchestrator = setup['orchestrator']
    
    # Initialize device state
    orchestrator._device_states['test_device_1'] = DeviceState(
        current_layout='default',
        saved_brightness=100,
        power_mode=PowerMode.ACTIVE
    )
    
    return setup
```

### Window Change Scenario

```python
@pytest.fixture
def window_change_scenario(orchestrator_setup, firefox_window):
    """Pre-configured scenario for testing window-based layout switching."""
    setup = orchestrator_setup
    
    # Configure layout manager to return firefox layout
    setup['layouts'].select_layout_for_window.return_value = 'firefox'
    
    return {
        **setup,
        'window': firefox_window
    }
```

---

## Pytest Configuration

### conftest.py Structure

```python
# tests/conftest.py
"""Shared fixtures for all tests."""

import pytest
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Import fixture modules
pytest_plugins = [
    'tests.fixtures.infrastructure',
    'tests.fixtures.business',
    'tests.fixtures.orchestration',
    'tests.fixtures.application',
    'tests.fixtures.common',
]

# pytest configuration
def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring real hardware"
    )
    config.addinivalue_line(
        "markers", "regression: mark test as regression test for specific issue"
    )
    config.addinivalue_line(
        "markers", "performance: mark test as performance test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
```

### pytest.ini

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

markers =
    hardware: tests requiring real hardware (skipped in CI)
    regression: regression tests for specific issues
    performance: performance tests
    integration: integration tests

# Minimum coverage (enforced in CI)
addopts =
    -v
    --strict-markers
    --tb=short
    --cov-branch
```

---

## Fixture Organization

### Directory Structure

```
tests/
├── conftest.py                      # Main fixture configuration
├── fixtures/
│   ├── __init__.py
│   ├── infrastructure.py            # Infrastructure layer fixtures
│   ├── business.py                  # Business logic layer fixtures
│   ├── orchestration.py             # Orchestration layer fixtures
│   ├── application.py               # Application layer fixtures
│   └── common.py                    # Shared fixtures
├── infrastructure/
│   ├── test_hardware_interface.py
│   ├── test_system_interface.py
│   └── test_device_registry.py
├── business/
│   ├── test_layout_manager.py
│   ├── test_action_executor.py
│   └── test_system_event_monitor.py
├── integration/
│   ├── test_device_orchestrator.py
│   ├── test_lock_unlock_cycle.py
│   └── test_window_change_flow.py
└── application/
    ├── test_configuration_manager.py
    └── test_application_lifecycle.py
```

---

## Usage Examples

### Using Fixtures in Tests

```python
# tests/business/test_layout_manager.py
import pytest
from StreamDock.business_logic.layout_manager import LayoutManager

def test_layout_selection_with_sample_data(sample_layouts, sample_window_rules, firefox_window):
    """Example of using multiple fixtures."""
    manager = LayoutManager(sample_layouts)
    
    for rule in sample_window_rules:
        manager.add_window_rule(rule)
    
    selected = manager.select_layout_for_window(firefox_window)
    
    assert selected == 'firefox'

def test_orchestrator_lock_cycle(lock_unlock_scenario):
    """Example of using scenario fixture."""
    setup = lock_unlock_scenario
    orchestrator = setup['orchestrator']
    
    # Trigger lock
    orchestrator._on_screen_lock()
    
    # Verify device powered down
    assert setup['device_states']['test_device_1'].power_mode == PowerMode.STANDBY
```

---

## Best Practices

### ✅ Do

- **Reuse fixtures** - Don't duplicate fixture setup across tests
- **Keep fixtures focused** - One fixture per concern
- **Use pytest-lazy-fixture** - For parameterized fixtures
- **Document fixtures** - Add docstrings explaining what they provide
- **Scope appropriately** - Use `function`, `class`, `module`, or `session` scope

### ❌ Don't

- **Don't put logic in fixtures** - Keep them simple data providers
- **Don't create interdependent fixtures** - Maintain independence where possible
- **Don't modify shared fixtures** - Create new instances if mutation needed
- **Don't overuse `autouse`** - Explicit is better than implicit

---

## Summary

**Fixture Categories:**
1. **Infrastructure** - Mock hardware and system interfaces
2. **Business Logic** - Sample layouts, rules, and business data
3. **Orchestration** - Complete component setups for integration testing
4. **Application** - Configuration files and bootstrap scenarios
5. **Common** - Shared test data (windows, devices)

**Organization:**
- Centralized in `tests/fixtures/`
- Imported via `pytest_plugins` in `conftest.py`
- Documented with docstrings
- Reusable across test layers
