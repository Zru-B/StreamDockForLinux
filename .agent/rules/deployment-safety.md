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

## Security and Secrets Management
- **Never Hardcode Secrets**: Never commit API keys, passwords, or tokens to version control.
- **Environment Variables**: Use environment variables or secure config files (ignored by git) for sensitive data.
- **Sanitize Logs**: Never log sensitive information (passwords, tokens, full file paths with user data).

## File Permissions and Ownership
- **Created Files**: Files created by the application should have appropriate permissions (0644 for config, 0600 for sensitive data).
- **Directories**: Created directories should be 0755 unless they contain sensitive data.
- **User Ownership**: Files should be owned by the user running the application, not root.

## Resource Cleanup
- **Error Path Cleanup**: Ensure resources are cleaned up even in error conditions (use `try/finally` or context managers).
- **Thread Cleanup**: If using threads, ensure they are properly joined or daemonized.
- **Signal Handlers**: Implement signal handlers (SIGINT, SIGTERM) to gracefully shutdown and cleanup resources.
- **Device Handles**: Always close HID device handles, even if an exception occurs.

## Dependency Security
- **Review Dependencies**: Regularly review `requirements.txt` for outdated or vulnerable packages.
- **Pin Versions**: Pin major and minor versions in `requirements.txt` to avoid unexpected changes.
- **Security Scanning**: Use tools like `pip-audit` or `safety` to check for known vulnerabilities.
- **Minimal Dependencies**: Only include necessary dependencies. Remove unused packages.
