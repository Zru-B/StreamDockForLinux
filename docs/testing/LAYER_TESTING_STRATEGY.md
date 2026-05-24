# Layer Testing Strategy

## Overview

This document defines the testing approach for each layer in the StreamDock layered architecture. Each layer has specific testing requirements based on its responsibilities and dependencies.

## Core Testing Principles

1. **Test at the right layer** - Unit tests for business logic, integration tests for orchestration
2. **Mock external dependencies** - Infrastructure should be mockable, business logic should be pure
3. **Design contracts over implementation** - Tests should survive refactoring
4. **Fast feedback loops** - Tests should run quickly and provide clear failure messages

---

## Infrastructure Layer Testing

### Characteristics
- **Zero business logic** - Pure I/O and system interaction
- **Heavy mocking required** - Real hardware/OS not used in unit tests
- **Integration tests separate** - Hardware tests marked and manual

### Testing Strategy

#### Unit Tests (Automated)
- **Target Coverage:** 90%
- **Mock Strategy:** Mock all OS/hardware interactions
- **Test Focus:** Protocol logic, state management, error handling

**Example: HardwareInterface Tests**
```python
import pytest
from unittest.mock import Mock, patch
from StreamDock.infrastructure.hardware_interface import USBHardware

class TestUSBHardware:
    @pytest.fixture
    def mock_hidapi(self):
        with patch('StreamDock.infrastructure.usb_hardware.hid') as mock:
            yield mock
    
    def test_enumerate_devices_returns_correct_format(self, mock_hidapi):
        """Design contract: enumerate_devices returns DeviceInfo objects."""
        mock_hidapi.enumerate.return_value = [
            {'vendor_id': 0x1234, 'product_id': 0x5678, 'serial_number': 'ABC123'}
        ]
        
        hardware = USBHardware()
        devices = hardware.enumerate_devices(0x1234, 0x5678)
        
        assert len(devices) == 1
        assert devices[0].vendor_id == 0x1234
        assert devices[0].serial_number == 'ABC123'
    
    def test_device_reconnection_updates_handle(self, mock_hidapi):
        """Critical: Device path changes handled transparently."""
        # Test the reconnection logic without real USB
        pass
```

#### Integration Tests (Manual, Hardware Required)
- **Marker:** `@pytest.mark.hardware`
- **Run manually:** `pytest -m hardware`
- **Test Focus:** Real device interaction, timing requirements

**Example: Real Hardware Test**
```python
@pytest.mark.hardware
def test_brightness_change_visible_on_device():
    """Verify brightness changes are actually visible on real hardware."""
    with RealDevice() as device:
        device.set_brightness(100)
        time.sleep(0.1)  # Allow device to update
        # Manual verification: Device is at full brightness
        
        device.set_brightness(0)
        time.sleep(0.1)
        # Manual verification: Device is dark
```

### Test Organization
```
tests/infrastructure/
├── test_hardware_interface.py      # USBHardware tests (mocked)
├── test_system_interface.py        # LinuxSystemInterface tests (mocked)
├── test_device_registry.py         # DeviceRegistry tests (mocked)
└── test_hardware_integration.py    # Real hardware tests (@pytest.mark.hardware)
```

---

## Business Logic Layer Testing

### Characteristics
- **Pure logic** - No I/O, no side effects
- **Minimal mocking** - Only interface mocks for SystemInterface dependencies
- **Highly testable** - Should be easiest to test

### Testing Strategy

#### Unit Tests (Automated)
- **Target Coverage:** 95%
- **Mock Strategy:** Only mock injected interfaces (SystemInterface)
- **Test Focus:** Logic correctness, edge cases, state transitions

**Example: LayoutManager Tests**
```python
from StreamDock.business_logic.layout_manager import LayoutManager
from StreamDock.business_logic.layout_config import LayoutConfig, WindowRule

class TestLayoutManager:
    @pytest.fixture
    def layout_manager(self):
        layouts = {
            'default': LayoutConfig(name='default', keys=[]),
            'firefox': LayoutConfig(name='firefox', keys=[])
        }
        return LayoutManager(layouts)
    
    def test_select_layout_for_window_matches_class(self, layout_manager):
        """Design contract: Window class matches trigger layout switch."""
        rule = WindowRule(pattern='firefox', layout_name='firefox', match_field='class')
        layout_manager.add_window_rule(rule)
        
        window_info = WindowInfo(class_name='firefox', title='Mozilla Firefox')
        selected = layout_manager.select_layout_for_window(window_info)
        
        assert selected == 'firefox'
    
    def test_select_layout_returns_none_when_no_match(self, layout_manager):
        """Edge case: No matching rule returns None."""
        window_info = WindowInfo(class_name='unknown', title='Unknown App')
        selected = layout_manager.select_layout_for_window(window_info)
        
        assert selected is None
```

#### Logical Tests (Automated)
- **Test Focus:** Complex scenarios, rule combinations, state machines
- **No I/O:** Pure logic validation

**Example: Complex Layout Selection**
```python
def test_layout_selection_priority_order():
    """Test that more specific rules take precedence."""
    manager = LayoutManager(layouts)
    manager.add_window_rule(WindowRule(pattern='.*', layout_name='default'))  # Catch-all
    manager.add_window_rule(WindowRule(pattern='firefox', layout_name='firefox'))  # Specific
    
    # Specific rule should win
    window = WindowInfo(class_name='firefox')
    assert manager.select_layout_for_window(window) == 'firefox'
```

### Test Organization
```
tests/business/
├── test_layout_manager.py           # Layout selection logic
├── test_action_executor.py          # Action execution logic
├── test_system_event_monitor.py    # Event routing logic
└── test_layout_selection_rules.py  # Complex scenario tests
```

---

## Orchestration Layer Testing

### Characteristics
- **Coordination logic** - Bridges multiple layers
- **Integration focus** - Tests interaction between components
- **All dependencies mocked** - No real hardware or OS

### Testing Strategy

#### Integration Tests (Automated)
- **Target Coverage:** 85%
- **Mock Strategy:** Mock all dependencies (Registry, LayoutManager, ActionExecutor, EventMonitor)
- **Test Focus:** Coordination flows, event handling, state management

**Example: DeviceOrchestrator Tests**
```python
from unittest.mock import Mock
from StreamDock.orchestration.device_orchestrator import DeviceOrchestrator

class TestDeviceOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        registry = Mock()
        layouts = Mock()
        actions = Mock()
        events = Mock()
        return DeviceOrchestrator(registry, layouts, actions, events)
    
    def test_screen_lock_saves_state_and_powers_down(self, orchestrator):
        """Design contract: Lock event saves device state and powers down."""
        orchestrator._registry.discover_devices.return_value = ['device1']
        orchestrator._device_states['device1'] = DeviceState(
            current_layout='default',
            saved_brightness=80,
            power_mode=PowerMode.ACTIVE
        )
        
        orchestrator._on_screen_lock()
        
        # Verify state was saved
        assert orchestrator._device_states['device1'].saved_brightness == 80
        # Verify device was powered down
        orchestrator._set_power_mode.assert_called_with('device1', PowerMode.STANDBY)
    
    def test_button_press_routes_to_action_executor(self, orchestrator):
        """Design contract: Button press triggers action execution."""
        orchestrator.handle_button_press('device1', button_index=5)
        
        # Verify action executor was called with correct action
        orchestrator._actions.execute_action.assert_called_once()
```

### Test Organization
```
tests/integration/
├── test_device_orchestrator.py      # Orchestration logic (all mocked)
├── test_lock_unlock_cycle.py        # Full lock/unlock flow
└── test_window_change_flow.py       # Window-triggered layout change
```

---

## Application Layer Testing

### Characteristics
- **Bootstrap and wiring** - Dependency injection
- **Configuration parsing** - YAML validation
- **End-to-end validation** - Full system tests

### Testing Strategy

#### Unit Tests (Automated)
- **Target Coverage:** 90%
- **Test Focus:** Configuration validation, YAML parsing, dependency wiring

**Example: ConfigurationManager Tests**
```python
from StreamDock.application.configuration_manager import ConfigurationManager

class TestConfigurationManager:
    def test_load_valid_config(self, tmp_path):
        """Design contract: Valid YAML loads without errors."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("""
layouts:
  default:
    keys: []
""")
        
        config = ConfigurationManager(str(config_file))
        layouts = config.get_layouts()
        
        assert 'default' in layouts
    
    def test_invalid_config_raises_validation_error(self, tmp_path):
        """Edge case: Invalid config raises clear error."""
        config_file = tmp_path / "bad_config.yml"
        config_file.write_text("invalid: yaml: content:")
        
        with pytest.raises(ConfigValidationError):
            ConfigurationManager(str(config_file))
```

#### End-to-End Tests (Automated with Mocks)
- **Test Focus:** Full application lifecycle, component wiring

**Example: Application Lifecycle**
```python
def test_application_initializes_all_components():
    """Design contract: Application wires all components correctly."""
    app = Application('tests/configs/minimal.yml')
    
    # Verify all components were created
    assert app._orchestrator is not None
    assert app._event_monitor is not None
    # etc.
```

### Test Organization
```
tests/application/
├── test_configuration_manager.py    # Config parsing and validation
└── test_application_lifecycle.py    # Bootstrap and wiring

tests/e2e/
└── test_full_application_flow.py    # Complete scenarios
```

---

## Test Type Selection Guide

### When to Use Each Test Type

| Scenario | Test Type | Layer | Mocking |
|----------|-----------|-------|---------|
| USB protocol logic | Unit | Infrastructure | Heavy (mock hidapi) |
| Layout selection rules | Unit | Business | None (pure logic) |
| Lock/unlock coordination | Integration | Orchestration | All dependencies |
| Real device brightness | Hardware | Infrastructure | None (real device) |
| Config file parsing | Unit | Application | None |
| Full user scenario | E2E | Application | Minimal |

---

## Coverage Requirements

### Per-Layer Targets
- **Infrastructure:** 90% (critical path: 100%)
- **Business Logic:** 95% (pure logic should be fully tested)
- **Orchestration:** 85% (complex coordination)
- **Application:** 90% (configuration validation)

### Critical Paths (Must be 100%)
- Device reconnection logic (DeviceRegistry)
- Button press handling (DeviceOrchestrator → ActionExecutor)
- Layout switching (LayoutManager)
- Lock/unlock cycle (SystemEventMonitor → DeviceOrchestrator)

---

## Test Execution

### Running Tests

```bash
# All automated tests
pytest tests/

# Specific layer
pytest tests/infrastructure/
pytest tests/business/
pytest tests/integration/
pytest tests/application/

# With coverage
pytest --cov=src/StreamDock tests/ --cov-report=term-missing

# Hardware tests (manual)
pytest -m hardware tests/

# Specific test
pytest tests/business/test_layout_manager.py::TestLayoutManager::test_select_layout_for_window
```

### Continuous Integration
```bash
# CI should run (no hardware tests)
pytest tests/ -m "not hardware" --cov=src/StreamDock --cov-fail-under=85
```

---

## Anti-Patterns to Avoid

### ❌ Don't: Test Implementation Details
```python
def test_layout_manager_internal_cache():
    manager.load_layout('default')
    assert manager._cache['default'] is not None  # ❌ Testing internal detail
```

### ✅ Do: Test Design Contracts
```python
def test_layout_manager_loads_layout():
    layout = manager.load_layout('default')
    assert layout.name == 'default'  # ✅ Testing observable behavior
```

### ❌ Don't: Mock Everything in Business Logic
```python
def test_layout_selection(mock_layout, mock_rule, mock_window):
    # ❌ Pure logic doesn't need mocking!
    pass
```

### ✅ Do: Test Pure Logic Directly
```python
def test_layout_selection():
    manager = LayoutManager(real_layouts)
    window = WindowInfo(class_name='firefox')
    selected = manager.select_layout_for_window(window)
    assert selected == 'firefox'  # ✅ No mocking needed
```

---

## Summary

**Key Takeaways:**
1. **Infrastructure** - Mock heavily, test protocol logic
2. **Business Logic** - Minimal mocking, test pure logic
3. **Orchestration** - Mock all dependencies, test coordination
4. **Application** - Test configuration and wiring

**Success Metrics:**
- 90%+ coverage across all layers
- 100% coverage on critical paths
- All tests pass on every commit
- Hardware tests pass before release
