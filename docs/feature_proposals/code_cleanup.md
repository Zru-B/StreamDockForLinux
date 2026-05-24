# Code Cleanup Proposal

This document outlines functionality and test classes that have been identified as potentially unused or completely dead code during a static analysis sweep (via `vulture` and `grep`). The aggressive removal of these items was deferred.

They are logged here for future consideration.

## 1. Unused Image Helpers
`src/StreamDock/image_helpers/pil_helper.py`
- **Suspects:** `create_image`, `create_touchscreen_image`, `create_scaled_image`, `create_scaled_touchscreen_image`, and `to_native_seondscreen_format`.
- **Reasoning:** A structural trace confirms none of the rendering logic in `business_logic` or the execution flow ever imports or calls them. They appear to be lingering boilerplate.

## 2. Deprecated Stream Dock Commands
`src/StreamDock/devices/stream_dock.py`
- **Suspects:** Legacy unused methods: `whileread`, `clear_icon`, `set_seconds`.
- **Reasoning:** A direct repository search for these specific method names yields **ZERO** calls outside of their local `def ...:` declarations. They are not called by hardware pipelines or layouts.

## 3. False-Positive Test Methods (Over-testing)
### `src/StreamDock/devices/stream_dock.py` & `stream_dock_293_v3.py`
- **Suspect:** `get_serial_number`
- **Reasoning:** This method is mapped and mocked inside `test_stream_dock.py` and `test_concurrency.py`. However, the actual main application folders (`orchestration/`, `business_logic/`, `infrastructure/`) confirm it is **never physically called during the live runtime** of the application. It acts purely as a vanity metric for tests.

### `src/StreamDock/infrastructure/device_registry.py`
- **Suspects:** `enumerate_and_register`, `get_device_count`
- **Reasoning:** Like the serial method, these methods are thoroughly interrogated in `test_device_registry.py` but are entirely unutilized by the system lifecycle in `device_orchestrator.py` or `main.py`.

### `src/StreamDock/infrastructure/system_interface.py` & `linux_system_interface.py`
- **Suspect:** `send_media_key`
- **Reasoning:** Defined heavily in both the abstract layer and concrete Linux layers, and heavily tested inside `test_system_interface.py`. Unfortunately, a `grep_search` verifies `action_executor.py` and key handlers never actually trigger this interface inside the runtime application.
