#!/usr/bin/env bash
# scripts/install.sh — Install StreamDock system integration files.
#
# Sets up:
#   /usr/local/bin/streamdock-udev-helper    udev helper (start/stop user service)
#   /etc/udev/rules.d/99-streamdock.rules    USB device permissions + auto-start
#   ~/.config/systemd/user/streamdock.service  per-user service unit
#
# Run from anywhere; the project root is derived from this script's location.
# Requires sudo for system-level operations (udev rule + helper install).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRIB_DIR="$PROJECT_DIR/contrib"

# ── Preflight checks ────────────────────────────────────────────────────────

VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $PROJECT_DIR/.venv"
    echo ""
    echo "Create it first:"
    echo "  python -m venv --system-site-packages .venv"
    echo "  .venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "Installing StreamDock system integration"
echo "  Project : $PROJECT_DIR"
echo "  User    : $(whoami)"
echo ""

# ── Step 1: udev helper script ──────────────────────────────────────────────

echo "[1/4] Installing udev helper → /usr/local/bin/streamdock-udev-helper"
sudo install -m 755 "$CONTRIB_DIR/streamdock-udev-helper" \
    /usr/local/bin/streamdock-udev-helper

# ── Step 2: udev rule ───────────────────────────────────────────────────────

echo "[2/4] Installing udev rule → /etc/udev/rules.d/99-streamdock.rules"
sudo install -m 644 "$CONTRIB_DIR/99-streamdock.rules" \
    /etc/udev/rules.d/99-streamdock.rules
sudo udevadm control --reload-rules
# Trigger only the StreamDock device nodes — avoids re-processing everything
sudo udevadm trigger --attr-match=idVendor=6603

# ── Step 3: systemd user service ────────────────────────────────────────────

echo "[3/4] Generating systemd user service → ~/.config/systemd/user/streamdock.service"
mkdir -p "$HOME/.config/systemd/user"
sed "s|@@PROJECT_DIR@@|$PROJECT_DIR|g" \
    "$CONTRIB_DIR/streamdock.service.template" \
    > "$HOME/.config/systemd/user/streamdock.service"
systemctl --user daemon-reload

# ── Step 4: plugdev group membership ────────────────────────────────────────

echo "[4/4] Checking plugdev group membership..."
if id -nG | grep -qw plugdev; then
    echo "       ✓ $(whoami) is already in the plugdev group"
else
    echo "       ⚠  $(whoami) is not in the plugdev group."
    echo "          Add with:  sudo usermod -aG plugdev $(whoami)"
    echo "          Then log out and back in for it to take effect."
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo "✓ Installation complete."
echo ""
echo "The application will start automatically when the device is plugged in."
echo ""
echo "Optional — also start at login (independent of device plug):"
echo "  systemctl --user enable streamdock.service"
echo ""
echo "Start manually right now:"
echo "  systemctl --user start streamdock.service"
echo ""
echo "Check status / logs:"
echo "  systemctl --user status streamdock.service"
echo "  journalctl --user -u streamdock.service -f"
