# Development Guide

This document explains how to set up your development environment, run tests, and contribute to StreamDock.

## 1. Setting Up the Environment

We recommend using a virtual environment to keep dependencies isolated.

### Prerequisites

- Python 3.10+
- `pip`
- System libraries (see `README.md` for distribution-specific instructions)
    - `hidapi`, `libusb`
    - `cairo` (for `cairosvg`)
    - `gobject-introspection` (for `PyGObject` / `dbus-python`)

### Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/Zru-B/StreamDockForLinux.git
    cd StreamDockForLinux
    ```

2.  **Create a virtual environment:**
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
    *Note: If you encounter issues with system packages like dbus, you might need:*
    ```bash
    python3 -m venv --system-site-packages .venv
    ```

3.  **Install dependencies:**
    ```bash
    # Install runtime requirements
    pip install -r requirements.txt
    
    # Install development tools (testing, linting, etc.)
    pip install -r requirements-dev.txt
    ```

## 2. Development Workflow

We use standard Python tools to ensure code quality.

### Code Style

We follow [PEP 8](https://peps.python.org/pep-0008/) and use `black` for formatting and `isort` for import sorting.

**Format code:**
```bash
black src
isort src
```

### Linting

We use `pylint` to catch errors and enforce coding standards.

**Run linter:**
```bash
pylint src/StreamDock
```

### Type Checking

We use `mypy` for static type checking.

**Run type checker:**
```bash
mypy src
```

## 3. Testing

We use `pytest` for unit and integration testing.

**Run all tests:**
```bash
pytest
```

**Run tests with coverage:**
```bash
pytest --cov=src
```

## 4. Project Structure

- `src/`: Main source code
    - `main.py`: Entry point
    - `StreamDock/`: Core package
        - `DeviceManager.py`: Handles device connection/disconnection
        - `StreamDock.py`: Main controller logic
        - `Configuration.py`: YAML config parser
        - `WindowMonitor.py`: Detects active window changes
- `tests/`: Test suite (create this directory if adding new tests)
