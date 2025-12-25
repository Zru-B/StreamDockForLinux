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
