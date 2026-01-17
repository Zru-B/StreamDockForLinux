# ADR-003: D-Bus for Session & Hardware State Monitoring

- **Status**: Accepted
- **Date**: 2026-01-15

## Context
The application needs to respond to system-level events such as screen locking (to turn off the device screen) and unlocking (to restore the active layout).

## Decision
We use D-Bus signals from `org.freedesktop.ScreenSaver` or equivalent providers (KWin, GNOME Shell) to monitor session state.

The `LockMonitor` class listens for:
- `ActiveChanged` (Boolean)
- `Locked` / `Unlocked` signals.

## Consequences
- **Dependency**: Requires `dbus-python` and `PyGObject` on the host system.
- **Robustness**: Re-connection logic must be triggered after an unlock event, as USB power management might have suspended the device during sleep.
- **Environment**: Different desktop environments use different D-Bus paths; the code must be defensive and try multiple common destinations.
