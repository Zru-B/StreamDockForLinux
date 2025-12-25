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
