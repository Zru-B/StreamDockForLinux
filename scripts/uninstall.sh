#!/usr/bin/env bash
# scripts/uninstall.sh — Remove StreamDock system integration files.
#
# Removes the udev rule, the desktop entry and its icon.
#
# Requires sudo for system-level operations.

set -euo pipefail

APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "Removing StreamDock system integration"
echo ""

# ── udev rule ───────────────────────────────────────────────────────────────

echo "[1/3] Removing udev rule"
sudo rm -f /etc/udev/rules.d/99-streamdock.rules
sudo udevadm control --reload-rules

# ── Desktop entry ───────────────────────────────────────────────────────────

echo "[2/3] Removing launcher"
rm -f "$APPLICATIONS_DIR/streamdock.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "[3/3] Removing icon"
rm -f "$ICON_DIR/streamdock.svg"
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
echo "✓ Uninstall complete."
echo ""
echo "Your configuration files were not touched."
