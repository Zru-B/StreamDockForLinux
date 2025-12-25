# StreamDockForLinux - Style Guide

## Python Standards

### 1. General Style
- Follow **PEP 8** for code formatting.
- Use 4 spaces for indentation.
- Maximum line length: 120 characters (slightly relaxed from PEP 8 for readability).

### 2. Type Hinting
- **Mandatory**: Use type hints for all function arguments and return values.
- Example:
  ```python
  def process_image(path: str, brightness: int = 50) -> Image.Image:
      ...
  ```

### 3. Naming Conventions
- **Classes**: PascalCase (e.g., `DeviceManager`).
- **Functions/Methods**: snake_case (e.g., `update_brightness`).
- **Variables**: snake_case (e.g., `current_layout`).
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_BRIGHTNESS`).

### 4. Documentation
- Use Google-style docstrings for all public classes and functions.
- Every module should have a top-level docstring explaining its purpose.

### 5. Error Handling
- Use specific exceptions (e.g., `FileNotFoundError`, `ValueError`).
- Create custom exception classes in `src/StreamDock/ConfigLoader.py` or similar if project-specific errors are needed.
- Always log exceptions using the `logging` module before raising or handling.

## Project Patterns
- **Hardware Abstraction**: Keep hardware communication (HID) isolated from application logic.
- **YAML over Hardcoding**: Prefer adding settings to `config.yml` rather than hardcoding values in Python.

### 6. Logging Standards
- **Use the `logging` Module**: Avoid `print()` statements. Use the project-standard logger.
- **Log Levels**: Use appropriate levels for each message:
  - **DEBUG**: Technical details, internal state changes, and hardware communication bytes. Include raw data chunks when troubleshooting.
  - **INFO**: High-level application milestones (e.g., "Device Found", "Layout Changed").
  - **WARNING**: Non-critical issues that don't stop the app (e.g., "Optional dependency missing", "Config value out of range, using default").
  - **ERROR**: Critical failures that require attention (e.g., "USB Connection Lost", "Invalid YAML syntax").
- **Debugging Data**: During development or when implementing new features, include verbose debug logs that capture:
  - Input parameters.
  - Transformation steps.
  - Return values or hardware responses.
- **Contextual Logging**: Include identifiers where possible (e.g., device serial, layout name) to make logs searchable.

### 7. Code Reuse and Refactoring
- **Update Tests When Refactoring**: Always update corresponding unit tests when refactoring a function. Tests must reflect new signatures, behaviors, and edge cases.
- **Prioritize Reuse**: Before implementing new logic, thoroughly search the existing codebase for similar functionality. Reuse or refactor existing classes and functions.
- **Continuous Refactoring**: If an existing function almost meets your needs, refactor it to be more generic rather than creating a near-duplicate.
- **Dead Code Prevention**: Ensure that changes do not leave orphaned or redundant code paths. Cleanup unused imports, variables, and functions as you go.
- **Maintainability First**: Write code that is easy to modify later. Stick to established project patterns to ensure consistency.

### 8. Input Validation and Defensive Programming
- **Validate All Inputs**: Always validate function parameters, user inputs, and configuration data at the boundaries of your application.
- **Fail Fast**: Raise exceptions early when invalid data is detected rather than allowing it to propagate.
- **Use Type Checking**: Leverage type hints with runtime validation (e.g., `isinstance()` checks) for critical paths.
- **Sanitize External Data**: Never trust data from config files, network, or user input. Validate format, range, and type.

### 9. Resource Management
- **Use Context Managers**: Always use `with` statements for file operations, network connections, and device handles.
- **Explicit Cleanup**: Implement `__enter__` and `__exit__` methods for custom resources.
- **File Descriptor Limits**: Be mindful of OS limits. Close resources promptly, especially in loops.
- **Example**:
  ```python
  with open(config_path, 'r') as f:
      config = yaml.safe_load(f)
  ```

### 10. Constants and Configuration
- **No Magic Numbers**: Define constants at module level with descriptive names (e.g., `MAX_BRIGHTNESS = 100`).
- **Configuration Over Hardcoding**: Move tunable values to `config.yml` rather than embedding them in code.
- **Enumerations**: Use `enum.Enum` for sets of related constants (e.g., device states, action types).

### 11. Function Design
- **Single Responsibility**: Each function should do one thing well. If a function has more than one clear purpose, split it.
- **Function Length**: Keep functions under 50 lines when possible. If longer, consider refactoring.
- **Parameter Count**: Limit to 5 parameters. If more are needed, use a dataclass or configuration object.
- **Return Early**: Use early returns to reduce nesting and improve readability.
