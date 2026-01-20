# Coverage Requirements

## Overview

This document defines the code coverage requirements for the StreamDock layered architecture migration. Coverage targets are set per layer based on testability and criticality.

---

## Coverage Targets by Layer

### Infrastructure Layer: **90% Coverage**

**Rationale:** Infrastructure layer is critical for system stability but requires heavy mocking. 90% ensures thorough testing while acknowledging some edge cases may be difficult to test without real hardware.

**Critical Paths (100% Required):**
- Device reconnection logic in `DeviceRegistry`
- USB path change detection and handling
- Device enumeration and discovery
- Handle lifecycle management

**Components:**
| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| `HardwareInterface` (abstract) | 100% | Critical |
| `USBHardware` (implementation) | 90% | High |
| `SystemInterface` (abstract) | 100% | Critical |
| `LinuxSystemInterface` (implementation) | 85% | High |
| `DeviceRegistry` | 95% | **Critical** |

**Excluded from Coverage:**
- Platform-specific fallback code (e.g., macOS/Windows stubs)
- Debug logging statements
- Unreachable error handlers for hardware failures

---

### Business Logic Layer: **95% Coverage**

**Rationale:** Business logic should be pure and highly testable. 95% coverage ensures all logic paths are validated. This is the easiest layer to test.

**Critical Paths (100% Required):**
- Layout selection logic in `LayoutManager`
- Action execution routing in `ActionExecutor`
- Event dispatching in `SystemEventMonitor`
- Window rule matching

**Components:**
| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| `LayoutManager` | 95% | **Critical** |
| `ActionExecutor` | 95% | **Critical** |
| `SystemEventMonitor` | 95% | **Critical** |
| Data classes (`LayoutConfig`, `WindowRule`, etc.) | 90% | Medium |

**Excluded from Coverage:**
- Simple property getters/setters
- `__repr__` and `__str__` methods
- Type checking guards (already validated by type hints)

---

### Orchestration Layer: **85% Coverage**

**Rationale:** Orchestration layer involves complex coordination and state management. 85% acknowledges the difficulty of testing all timing scenarios and race conditions.

**Critical Paths (100% Required):**
- Lock/unlock device state management
- Button press routing
- Layout switching coordination
- Device state restoration

**Components:**
| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| `DeviceOrchestrator` | 85% | **Critical** |

**Excluded from Coverage:**
- Rare race condition handlers
- Performance optimization paths
- Debug/diagnostic code

---

### Application Layer: **80% Coverage**

**Rationale:** Application layer is primarily wiring and bootstrapping. Focus on configuration validation rather than dependency injection mechanics.

**Critical Paths (100% Required):**
- Configuration file validation
- YAML schema compliance
- Dependency injection wiring (basic validation)

**Components:**
| Component | Target Coverage | Priority |
|-----------|----------------|----------|
| `ConfigurationManager` | 90% | High |
| `Application` (bootstrap) | 75% | Medium |

**Excluded from Coverage:**
- Error message formatting
- Logging configuration
- CLI argument parsing (if applicable)

---

## Overall Project Coverage

### Minimum Thresholds

**Per-Layer Minimums:**
- Infrastructure: ≥ 90%
- Business Logic: ≥ 95%
- Orchestration: ≥ 85%
- Application: ≥ 80%

**Overall Project Minimum:** ≥ 87%

**Critical Paths:** 100% (no exceptions)

---

## Coverage Enforcement

### Automated Checks

#### Pre-Commit Hook
```bash
#!/bin/bash
# .git/hooks/pre-commit

# Run tests with coverage
pytest tests/ -m "not hardware" --cov=src/StreamDock --cov-report=term-missing --cov-fail-under=87

if [ $? -ne 0 ]; then
    echo "❌ Coverage below 87% threshold"
    exit 1
fi
```

#### CI Pipeline
```yaml
# .github/workflows/test.yml
- name: Run tests with coverage
  run: |
    pytest tests/ -m "not hardware" \
      --cov=src/StreamDock \
      --cov-report=xml \
      --cov-report=term-missing \
      --cov-fail-under=87

- name: Upload coverage to Codecov
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
    fail_ci_if_error: true
```

### Coverage Reporting

#### Generate HTML Report
```bash
pytest tests/ --cov=src/StreamDock --cov-report=html
# Open htmlcov/index.html in browser
```

#### Generate Terminal Report
```bash
pytest tests/ --cov=src/StreamDock --cov-report=term-missing
```

#### Per-Layer Coverage
```bash
# Infrastructure
pytest tests/infrastructure/ --cov=src/StreamDock/infrastructure --cov-report=term

# Business
pytest tests/business/ --cov=src/StreamDock/business --cov-report=term

# Orchestration
pytest tests/integration/ --cov=src/StreamDock/orchestration --cov-report=term

# Application
pytest tests/application/ --cov=src/StreamDock/application --cov-report=term
```

---

## Coverage Gap Analysis

### Identifying Gaps

**Step 1: Generate Coverage Report**
```bash
pytest tests/ --cov=src/StreamDock --cov-report=term-missing
```

**Step 2: Review Missing Lines**
Look for patterns:
- **Uncovered error handlers** → Add negative test cases
- **Uncovered edge cases** → Add boundary tests
- **Uncovered branches** → Add conditional tests

**Step 3: Prioritize Gaps**
- **Critical path gaps** → Fix immediately (blocker)
- **Business logic gaps** → Fix before merge (high priority)
- **Error handling gaps** → Fix before release (medium priority)
- **Debug code gaps** → Document as excluded (low priority)

### Example Gap Analysis

```
Name                                Stmts   Miss  Cover   Missing
-----------------------------------------------------------------
StreamDock/business/layout_manager    120      6    95%   45-48, 92, 105
StreamDock/infrastructure/device_reg  156      8    95%   201-205, 234-236
StreamDock/orchestration/orchestrator 98     15    85%   67-72, 145-150, 189
-----------------------------------------------------------------
TOTAL                                 374     29    92%
```

**Action Plan:**
1. `layout_manager.py:45-48` - Add test for invalid layout name
2. `device_registry.py:201-205` - Add test for duplicate device detection
3. `orchestrator.py:67-72` - Add test for rapid lock/unlock sequence

---

## Critical Path Identification

### Definition
Critical paths are code paths that:
1. Handle user data or state
2. Manage device lifecycle
3. Execute user-triggered actions
4. Handle system events

### Identified Critical Paths

**Path 1: Device Reconnection**
```
DeviceRegistry._on_device_added() 
  → DeviceRegistry._recognize_device()
    → DeviceRegistry._update_handle()
```
**Coverage Requirement:** 100%
**Test:** `tests/infrastructure/test_device_registry.py::test_device_path_change_reconnection`

**Path 2: Button Press → Action Execution**
```
HardwareInterface.read_input()
  → DeviceOrchestrator.handle_button_press()
    → ActionExecutor.execute_action()
      → SystemInterface.execute_command()
```
**Coverage Requirement:** 100%
**Test:** `tests/integration/test_button_press_flow.py`

**Path 3: Lock Event → Device Standby**
```
SystemInterface.monitor_screen_lock()
  → SystemEventMonitor._dispatch_lock_event()
    → DeviceOrchestrator._on_screen_lock()
      → DeviceRegistry.get_device_handle()
        → HardwareInterface.set_brightness()
```
**Coverage Requirement:** 100%
**Test:** `tests/integration/test_lock_unlock_cycle.py`

**Path 4: Window Change → Layout Switch**
```
SystemInterface.get_active_window()
  → SystemEventMonitor._on_window_change()
    → DeviceOrchestrator._on_window_change()
      → LayoutManager.select_layout_for_window()
        → DeviceOrchestrator._switch_layout()
```
**Coverage Requirement:** 100%
**Test:** `tests/integration/test_window_layout_switching.py`

---

## Edge Cases to Test

### Infrastructure Layer
- [ ] Device disconnected during operation
- [ ] Multiple devices with same VID/PID
- [ ] USB path changes during read/write
- [ ] D-Bus connection failure and recovery
- [ ] Missing system tools (xdotool, kdotool)
- [ ] Invalid device responses

### Business Logic Layer
- [ ] Layout with no keys
- [ ] Window rule with invalid regex
- [ ] Action with missing parameters
- [ ] Circular layout references
- [ ] Empty configuration
- [ ] Unknown action type

### Orchestration Layer
- [ ] Lock during layout switch
- [ ] Button press during lock
- [ ] Rapid lock/unlock cycles
- [ ] Device disconnect during lock
- [ ] Multiple events in quick succession

### Application Layer
- [ ] Missing configuration file
- [ ] Malformed YAML syntax
- [ ] Invalid configuration schema
- [ ] Missing required fields
- [ ] Duplicate layout names

---

## Performance Testing

### Requirements
While not part of code coverage, performance tests ensure no regressions:

**Metrics to Track:**
- Layout switch latency: < 500ms
- Button press response: < 100ms
- Lock detection: < 50ms
- Device enumeration: < 200ms

**Performance Test Example:**
```python
import time
import pytest

@pytest.mark.performance
def test_layout_switch_performance():
    """Performance contract: Layout switches within 500ms."""
    start = time.time()
    orchestrator.switch_layout('device1', 'new_layout')
    elapsed = time.time() - start
    
    assert elapsed < 0.5, f"Layout switch took {elapsed:.3f}s (limit: 0.500s)"
```

---

## Test Suite Execution Time

**Target:** All automated tests should complete in < 10 seconds

**Current Breakdown (Estimated):**
- Infrastructure tests: ~2s
- Business logic tests: ~1s
- Orchestration tests: ~3s
- Application tests: ~2s
- **Total: ~8s**

**Optimization Strategies:**
- Use `pytest-xdist` for parallel execution
- Mock slow I/O operations
- Share expensive fixtures across tests
- Mark slow tests for optional execution

---

## Exclusions and Exceptions

### Excluded from Coverage Requirements

**1. Generated Code**
- Auto-generated protocol buffers
- Auto-generated stubs

**2. Debug and Diagnostic Code**
```python
if DEBUG:  # pragma: no cover
    print(f"Debug info: {data}")
```

**3. Platform-Specific Fallbacks**
```python
if sys.platform == 'darwin':  # pragma: no cover
    # macOS-specific code (not tested on Linux)
    pass
```

**4. Unreachable Error Handlers**
```python
try:
    validated_data = schema.validate(data)
except ValidationError:  # Already tested
    raise
except Exception as e:  # pragma: no cover
    # Should never happen, defensive programming
    logger.critical(f"Unexpected error: {e}")
```

### Marking Exclusions
Use `# pragma: no cover` comment to exclude specific lines/blocks:

```python
def some_function():
    if rare_condition:  # pragma: no cover
        handle_rare_case()
```

---

## Summary

**Coverage Philosophy:**
- **Infrastructure (90%):** Critical for stability, thorough testing required
- **Business Logic (95%):** Pure logic, should be fully tested
- **Orchestration (85%):** Complex coordination, some edge cases acceptable
- **Application (80%):** Wiring code, focus on validation

**Enforcement:**
- Automated checks in CI (fail on < 87%)
- Pre-commit hooks (optional, recommended)
- Regular coverage reviews during development

**Success Criteria:**
- ✅ All critical paths at 100%
- ✅ Overall project ≥ 87%
- ✅ Each layer meets minimum
- ✅ No regressions in coverage
