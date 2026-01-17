# Release & QA Playbook

This document outlines the mandatory quality assurance procedures for the StreamDockForLinux project. Every release must pass these checks to ensure stability, security, and robustness.

## 1. Automated Verification
- [ ] **Unit Tests**: Run `pytest tests/ -v`. Must be 100% green.
- [ ] **Coverage**: Verify coverage is > 80% with `pytest --cov=src/StreamDock tests/`.
- [ ] **Linting**: No new errors from `flake8` or `pylint`. Consult with the developer who to proceed with the linting, in case of warnings or errors.

## 2. Stability & Robustness (Manual)
- [ ] **Cold Boot**: Plug the device while the application is NOT running. Start the app. Verify it connects immediately.
- [ ] **Hot Plug**: Unplug the device while the application IS running. Wait 5 seconds. Plug it back in. Verify the app re-detects and restores the layout.
- [ ] **Long Run**: Keep the application running for at least 1 hour. Verify memory usage (`top` or `ps`) remains stable.
- [ ] **Suspend/Resume**: Put the system to sleep. Wake it up. Verify the device restores brightness and layout within 5 seconds of resume.

## 3. Security Audit
- [ ] **Config Sanitization**: Verify that `config.yml` cannot execute arbitrary bash commands (unless explicitly permitted via `RUN_COMMAND`).
- [ ] **Asset Validation**: Ensure icon paths in the config are localized to the system and do not allow directory traversal (e.g., `../../../etc/passwd`).
- [ ] **Permission Leak**: Verify the application does NOT require `sudo` to run if udev rules are correctly installed.

## 4. Hardware/UX Consistency
- [ ] **Brightness Granularity**: Verify brightness steps (0-100) are smooth and that 0 actually turns off the screen.
- [ ] **Icon Rendering**: Check that high-resolution PNGs are correctly scaled and centered on the physical keys.
- [ ] **Key Responsiveness**: Press multiple keys rapidly. Ensure no lag or skipped actions.
- [ ] **Layout Matching**: Open multiple windows (Browser, Terminal, Editor). Verify the layout switches correctly and matches the `config.yml` patterns.

## 5. Deployment Safety
- [ ] **udev Rule Verification**: Run `ls -l /dev/hidraw*` (or check udev monitor) to ensure permissions are `0666` and the device is accessible.
- [ ] **Dependencies**: Verify `hidapi`, `dbus-python`, and `PyGObject` are listed in `requirements.txt`.

---

> [!IMPORTANT]
> Failure of a single item in the "Stability" or "Security" sections is a blocker for any release.
