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
- Name test files `test_*.py`.
- Use fixtures for common setup (e.g., mock device manager).

## Running Tests
```bash
pytest tests/
```
