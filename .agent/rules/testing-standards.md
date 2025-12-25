# StreamDockForLinux - Testing Standards

## Testing Framework
- **Primary Framework**: `pytest`
- **Mocking**: Use `unittest.mock` or `pytest-mock` to simulate hardware behavior.

## Mocking Protocols

### 1. Hardware Isolation
Never run tests that attempt to open real HID devices unless they are specifically marked as integration tests and run in a controlled environment.
- Mock `hid.device` and `pyudev.Context`.
- Mock D-Bus interfaces for `LockMonitor` tests.

### 2. Configuration Testing
- Test the `ConfigLoader` against a variety of valid and invalid YAML files.
- Ensure `ConfigValidationError` is raised with helpful error messages.

## Test Organization
- Place tests in a `tests/` directory (create if it doesn't exist).
- **Configuration Samples**: Use a `tests/configs/` sub-directory to store sample YAML configuration files.
  - These samples should cover different scenarios (e.g., `media_layout.yml`, `window_rules.yml`, `invalid_syntax.yml`).
  - Use these files in your test fixtures rather than defining complex dictionaries in the code.
- Name test files `test_*.py`.
- Use fixtures for common setup (e.g., mock device manager).

## Running Tests
```bash
pytest tests/
```

## Test Coverage
- **Target Coverage**: Aim for at least 80% code coverage for non-UI code.
- **Critical Path Coverage**: Hardware communication and configuration loading must have 100% coverage.
- **Coverage Tools**: Use `pytest-cov` to measure coverage: `pytest --cov=src tests/`
- **Coverage Reports**: Review coverage reports regularly to identify untested code paths.

## Test Naming Conventions
- **Descriptive Names**: Test names should describe what is being tested and the expected outcome.
- **Pattern**: Use `test_<function>_<scenario>_<expected_result>` format.
- **Examples**:
  - `test_config_loader_invalid_yaml_raises_validation_error()`
  - `test_device_manager_reconnect_after_disconnect_succeeds()`

## Assertion Best Practices
- **Specific Assertions**: Use specific assertions (e.g., `assert value == expected` not `assert value`).
- **Assertion Messages**: Always include descriptive messages for complex assertions.
- **Example**:
  ```python
  assert brightness >= 0 and brightness <= 100, f"Brightness {brightness} out of valid range [0, 100]"
  ```
- **Multiple Assertions**: Each test should verify one behavior. If multiple assertions are needed, ensure they all relate to the same behavior.

## Continuous Integration
- **Automated Testing**: All tests must pass in CI before merging.
- **Test on Multiple Python Versions**: Target Python 3.10, 3.11, and 3.12.
- **Fail Fast**: Configure CI to fail immediately on first test failure to save time.

## Test Maintenance
- **Refactoring and Test Updates**: When refactoring a function, always update its unit tests immediately:
  - Update test names if function name or behavior changes
  - Modify assertions to match new return values or state changes
  - Add tests for new edge cases introduced by refactoring
  - Update mock configurations if function dependencies change
- **Removing Dead Code**: When removing obsolete code, also remove its associated tests to prevent test suite bloat.
- **Signature Changes**: If a function signature changes (parameters added/removed/renamed), update all tests that call it.
- **Behavior Preservation**: If refactoring is meant to preserve behavior, existing tests should still pass. If tests break, either fix the refactoring or update tests with clear justification.
- **Test-First Refactoring**: For complex refactoring, consider updating tests first to define expected behavior, then refactor code to pass updated tests.

## Test Types and Strategy

This section defines the different types of tests for the StreamDockForLinux project, their scope, and execution cadence.

### 1. Unit Tests (Mocked)
**Scope**: Test individual functions and classes in complete isolation.
- Mock all hardware dependencies (`hid.device`, `pyudev.Context`)
- Mock system dependencies (D-Bus, filesystem)
- Fast execution (milliseconds per test)
- High coverage target: 80% overall, 100% for critical paths

**What They Validate**:
- Function logic correctness
- Edge case handling
- Error conditions and exceptions
- Type safety and contract compliance

**Execution Cadence**:
- ✅ On every commit (pre-commit hook)
- ✅ In CI/CD pipeline on every push
- ✅ Before opening pull requests

### 2. Integration Tests (Mocked)
**Scope**: Test multiple components working together without real hardware.
- `ConfigLoader` → `DeviceManager` → `Layout` interactions
- Window monitoring → layout switching flow
- Lock monitor → device state management
- Still use mocks for hardware layer

**What They Validate**:
- Data flows correctly between components
- Components respect each other's contracts
- Configuration propagates through the system
- State management across module boundaries

**Execution Cadence**:
- ✅ In CI/CD pipeline on every push
- ✅ Before merging to main branch
- Run after unit tests pass

### 3. Configuration Tests
**Scope**: Validate YAML parsing and configuration handling.
- Use real config files from `tests/configs/`
- Test valid configurations (layouts, keys, window rules)
- Test invalid configurations (malformed YAML, missing fields, invalid values)
- Verify `ConfigValidationError` messages are helpful

**What They Validate**:
- YAML parsing correctness
- Schema validation
- Error messages for user guidance
- Default value handling

**Execution Cadence**:
- ✅ In CI/CD pipeline on every push
- ✅ When config schema changes

### 4. Python Version Compatibility Tests
**Scope**: Ensure code runs on Python 3.10, 3.11, and 3.12.
- Use `tox` or `pyenv` for local testing
- GitHub Actions for automated CI testing
- Run same test suite on each Python version

**What They Validate**:
- No Python version-specific syntax issues
- Dependencies compatible with all versions
- Type hints work across versions

**Execution Cadence**:
- ✅ In CI/CD on every push (automated)
- 📋 Locally before major releases
- Only on a single OS (e.g. Ubuntu latest)

### 5. Hardware Integration Tests (Real Device Required)
**Scope**: Test actual hardware communication with connected StreamDock.
- Real HID communication
- LED updates and brightness control
- Key press detection
- Device reconnection handling

**What They Validate**:
- Hardware commands work as expected
- Timing and synchronization
- Device state consistency
- USB communication reliability

**Execution Cadence**:
- 🔧 Manual, on-demand (mark with `@pytest.mark.hardware`)
- Run before releases
- Skip in CI (no hardware access)
- After changing HID communication code

**How to Run**:
```bash
pytest -m hardware tests/
```

### 6. End-to-End Tests (Real Device Required)
**Scope**: Complete user workflows from start to finish.
- Launch app → press key → app executes → verify result
- Window switch → layout change → verify layout applied
- Lock screen → device turns off → unlock → device turns on

**What They Validate**:
- User scenarios work as expected
- Real-world usage patterns
- Integration with actual system (X11/Wayland, D-Bus, etc.)

**Execution Cadence**:
- 🔧 Manual, before major releases
- After significant refactoring
- When adding new user-facing features

### 7. Performance & Stress Tests (Real Device Required)
**Scope**: Verify performance under load.
- Rapid key press handling
- Continuous layout switching
- Memory usage during extended operation
- Long-running stability (hours)

**What They Validate**:
- No memory leaks
- Acceptable latency (<100ms for key response)
- Stable over extended use
- Resource cleanup correctness

**Execution Cadence**:
- 📋 Periodically (monthly or before releases)
- When performance regressions suspected
- After major architectural changes

### 8. Regression Tests
**Scope**: Tests for previously fixed bugs.
- Each bug fix should get a regression test
- Tag with issue number: `@pytest.mark.regression` and `@pytest.mark.issue123`

**What They Validate**:
- Fixed bugs don't resurface
- Refactoring doesn't reintroduce old issues

**Execution Cadence**:
- ✅ Same as unit tests (every commit, CI/CD)
- Part of the standard test suite

### 9. Reconnection & Recovery Tests (Real Device Required)
**Scope**: Device disconnect/reconnect scenarios.
- Unplug device during operation
- USB reset and recovery
- Multiple replug cycles
- Error recovery from corrupted state

**What They Validate**:
- Graceful handling of device loss
- Successful reconnection
- No file descriptor leaks
- State restoration after reconnection

**Execution Cadence**:
- 🔧 Manual, when changing device management code
- Before releases
- When investigating device stability issues

### 10. Multi-Device Tests (Mocked)
**Scope**: Simulate multiple StreamDock devices.
- Mock multiple `hid.device` instances
- Test device enumeration
- Verify isolated state management

**What They Validate**:
- Code can handle multiple devices (even if you only have one)
- Device isolation (actions on device A don't affect device B)

**Execution Cadence**:
- 📋 Optional, when implementing multi-device support
- Run in CI if implemented

### OS Compatibility Testing

**Current Approach**: Manual documentation of tested platforms.
- Document OS/Python combinations you've personally tested
- Rely on community feedback for untested platforms

**If OS-Specific Issues Arise**:
- Use local VM (VirtualBox/QEMU) to reproduce
- Pass USB device through to VM
- Fix and validate on the specific distro
- Document the fix and tested platform

**Why Not CI for OS Compatibility?**
- GitHub Actions has no USB hardware access
- Would only test mocked code (limited value)
- False sense of security for hardware issues
- Manual VM testing is more reliable when needed

## Test Execution Summary

| Test Type | Frequency | Environment | Hardware Required |
|-----------|-----------|-------------|-------------------|
| Unit Tests | Every commit | Local + CI | No |
| Integration Tests | Every commit | Local + CI | No |
| Config Tests | Every commit | Local + CI | No |
| Python Version Tests | Every push | CI | No |
| Hardware Integration | Before release | Local | Yes |
| End-to-End | Before release | Local | Yes |
| Performance/Stress | Monthly/Pre-release | Local | Yes |
| Regression Tests | Every commit | Local + CI | No |
| Reconnection Tests | On-demand | Local | Yes |
| Multi-Device Tests | Optional | Local + CI | No (mocked) |

**Legend**:
- ✅ Automated (runs in CI)
- 🔧 Manual (developer-initiated)
- 📋 Periodic (scheduled or milestone-based)
