# `business_logic/` — Core Application Logic

This layer contains the **rules and behaviours** of the StreamDock application,
expressed in terms of domain concepts.  It knows nothing about how the OS
works, which USB library is used, or which window-detection tool is installed.

## Boundary rules

| Rule | Detail |
|---|---|
| **May import** | `domain/`, abstract interfaces from `infrastructure/` |
| **Must not import** | Concrete infrastructure classes (`LinuxSystemInterface`, `LinuxWindowManager`, `USBHardware`, etc.) |
| **Consumed by** | `orchestration/`, `application/` |

## Key components

| Component | Responsibility |
|---|---|
| `SystemEventMonitor` | Polls OS events (active window, lock state); dispatches callbacks |
| `ActionExecutor` | Executes actions (launch app, send key, set volume, …) triggered by button presses |
| `LayoutManager` | Resolves which profile/layout is active for the current window |

## Testing strategy

All components receive their OS dependencies through constructor injection
(`SystemInterface`, `WindowInterface`, `HardwareInterface`).  Tests replace
these with `MagicMock(spec=…)` instances — no real OS calls ever run.
