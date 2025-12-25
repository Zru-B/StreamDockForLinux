# StreamDockForLinux - Deployment & Safety

## Hardware Safety
- **Brightness**: Avoid setting brightness to 100% for extended periods to prevent LED burn-in.
- **Reconnection**: Ensure the application handles device disconnection and reconnection gracefully without crashing or leaking file descriptors.

## System Safety

### 1. udev Rules
- When modifying udev rules, always provide a "rollback" path.
- Warn the user that udev changes require root privileges (`sudo`) and a rule reload.
- **CRITICAL**: Verify VID/PID before suggesting rule changes to avoid impacting other HID devices.

### 2. Process Detachment
- Use `nohup` and `&` when launching applications from StreamDock actions to ensure they survive if the main script stops.
- Avoid shell=True in `subprocess` calls unless absolutely necessary for pipe support.

### 3. D-Bus Integration
- Ensure `LockMonitor` fails gracefully if the D-Bus service (e.g., KDE ScreenSaver) is unavailable.
