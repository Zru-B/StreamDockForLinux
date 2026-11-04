#!/usr/bin/env bash
# scripts/uninstall.sh — Remove StreamDock system integration files.
#
# Removes the udev rule, the desktop and autostart entries, the icon and the
# launcher log.
#
# Options:
#   --no-udev   Keep the udev rule (no sudo); remove only the launcher files
#
# Requires sudo for the udev rule only.

set -euo pipefail

REMOVE_UDEV=1
while [ $# -gt 0 ]; do
    case "$1" in
        --no-udev) REMOVE_UDEV=0; shift ;;
        -h|--help) sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "Removing StreamDock system integration"
echo ""

# ── udev rule ───────────────────────────────────────────────────────────────

if [ "$REMOVE_UDEV" -eq 1 ]; then
    echo "[1/3] Removing udev rule"
    sudo rm -f /etc/udev/rules.d/70-streamdock.rules /etc/udev/rules.d/99-streamdock.rules
    sudo udevadm control --reload-rules
else
    echo "[1/3] Keeping udev rule (--no-udev)"
fi

# ── Desktop entry ───────────────────────────────────────────────────────────

echo "[2/3] Removing launcher"
rm -f "$APPLICATIONS_DIR/streamdock.desktop" \
      "${XDG_CONFIG_HOME:-$HOME/.config}/autostart/streamdock.desktop"
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/streamdock/launcher.log"{,.1}
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
