#!/usr/bin/env bash
# scripts/uninstall.sh — Remove StreamDock system integration files.
#
# Reverses everything done by scripts/install.sh.
# Requires sudo for system-level removals.

set -euo pipefail

echo "Uninstalling StreamDock system integration..."
echo ""

# Stop and disable the service if it is running
if systemctl --user is-active --quiet streamdock.service 2>/dev/null; then
    echo "[1/4] Stopping streamdock.service..."
    systemctl --user stop streamdock.service
else
    echo "[1/4] streamdock.service is not running — skipping stop"
fi

if systemctl --user is-enabled --quiet streamdock.service 2>/dev/null; then
    echo "[2/4] Disabling streamdock.service..."
    systemctl --user disable streamdock.service
else
    echo "[2/4] streamdock.service is not enabled — skipping disable"
fi

echo "[3/4] Removing systemd user service..."
rm -f "$HOME/.config/systemd/user/streamdock.service"
systemctl --user daemon-reload

echo "[4/4] Removing udev rule and helper..."
sudo rm -f /etc/udev/rules.d/99-streamdock.rules
sudo rm -f /usr/local/bin/streamdock-udev-helper
sudo udevadm control --reload-rules

echo ""
echo "✓ Uninstallation complete."
