#!/usr/bin/env bash
# scripts/uninstall.sh — Remove StreamDock system integration files.
#
# Removes the udev rule, the desktop entry and its icon, plus any
# streamdock.service and udev helper left over from earlier versions, which
# would otherwise keep competing with the application for the device.
#
# Requires sudo for system-level operations.

set -euo pipefail

APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
UNIT_FILE="$HOME/.config/systemd/user/streamdock.service"

echo "Removing StreamDock system integration"
echo ""

# ── Legacy auto-start (removed in the unified application) ──────────────────

if [ -f "$UNIT_FILE" ]; then
    echo "[1/4] Removing legacy systemd user service"
    systemctl --user stop streamdock.service 2>/dev/null || true
    systemctl --user disable streamdock.service 2>/dev/null || true
    rm -f "$UNIT_FILE"
    systemctl --user daemon-reload 2>/dev/null || true
else
    echo "[1/4] No legacy systemd user service found"
fi

if [ -e /usr/local/bin/streamdock-udev-helper ]; then
    echo "      Removing legacy udev helper"
    sudo rm -f /usr/local/bin/streamdock-udev-helper
fi

# ── udev rule ───────────────────────────────────────────────────────────────

echo "[2/4] Removing udev rule"
sudo rm -f /etc/udev/rules.d/99-streamdock.rules
sudo udevadm control --reload-rules

# ── Desktop entry ───────────────────────────────────────────────────────────

echo "[3/4] Removing launcher"
rm -f "$APPLICATIONS_DIR/streamdock.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "[4/4] Removing icon"
rm -f "$ICON_DIR/streamdock.svg"
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
echo "✓ Uninstall complete."
echo ""
echo "Your configuration files were not touched."
