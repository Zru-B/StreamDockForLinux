# Development

## Setup and tests

```bash
python -m venv --system-site-packages venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/
```

The suite runs headless: `tests/conftest.py` forces Qt's `offscreen` platform
and a scratch `XDG_CONFIG_HOME`, so it never touches your desktop, your
configuration or a real device. Every commit should leave it green.

## Layout of the code

```
src/
  main.py                 entry point (GUI; --headless, --minimized, --check-deps)
  StreamDock/
    domain/               plain data and the Key/Layout objects the device runs
    infrastructure/       OS and hardware: USB, window detection, input, D-Bus, MPRIS
    business_logic/       rules: actions, layout selection, system events
    orchestration/        DeviceOrchestrator - owns the devices and serialises writes
    application/          Application wires it together; config loading/validation
    devices/, transport/  device drivers and the ctypes libhidapi transport
    widgets/              widget runtime, registry, validator, built-in widgets
    ui/                   the PyQt6 application (editor, device bar, tray)
  streamdock_sdk/         the public widget SDK (see widgets.md)
```

### Layer rules

Dependencies point downward; a lower layer never imports a higher one.

| Layer | May import | Must not import |
|---|---|---|
| `infrastructure/` | `domain/`, stdlib, OS libraries | anything above it |
| `business_logic/` | `domain/`, infrastructure *interfaces* | concrete infrastructure classes (`LinuxSystemInterface`, ...) |
| `orchestration/` | the layers below | `application/`, `ui/` |
| `application/` | everything below | `ui/` |
| `ui/` | everything | - |

Only `ui/` uses Qt; the runtime layers must stay importable without it.

Business logic receives its OS dependencies (`SystemInterface`,
`WindowInterface`, `HardwareInterface`) through its constructor, and tests
pass `MagicMock(spec=...)` in their place, so no test touches the real OS.
Porting to another desktop means implementing `SystemInterface` and
`WindowInterface` and wiring them up in `application/application.py`.

### Where things live

| To change... | Look in |
|---|---|
| an action type | `business_logic/action_type.py`, `action_executor.py` |
| config validation | `application/configuration_manager.py` |
| the editor's config model (load/save, renames, usage) | `application/config_document.py` |
| window-rule matching | `business_logic/layout_manager.py` |
| device writes and layout switching | `orchestration/device_orchestrator.py` |
| a built-in widget | `widgets/builtin/` |
