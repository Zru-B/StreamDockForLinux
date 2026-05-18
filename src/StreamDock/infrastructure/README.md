# `infrastructure/` — OS & Hardware Abstraction Layer

This layer owns all direct interactions with the **operating system and hardware**.
It has no business rules; it merely exposes clean, mockable interfaces upward.

## Boundary rules

| Rule | Detail |
|---|---|
| **May import** | `domain/`, Python stdlib, third-party OS libs (dbus, hid) |
| **Must not import** | `business_logic/`, `orchestration/`, `application/` |
| **Consumed by** | `business_logic/` and `orchestration/` through abstract interfaces only |

## Key abstractions

| Interface | Concrete | Responsibility |
|---|---|---|
| `SystemInterface` | `LinuxSystemInterface` | Input simulation, media keys, volume, lock monitoring |
| `WindowInterface` | `LinuxWindowManager` | Focused-window detection, window activation |
| `HardwareInterface` | `USBHardware` | StreamDeck USB communication |

## Adding a new OS

1. Implement `SystemInterface` and `WindowInterface` for the target OS.
2. Wire them up in `application/application.py` — no other file should change.
