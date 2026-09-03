#!/usr/bin/env bash
# scripts/install.sh — Install StreamDock system integration files.
#
# Sets up:
#   /etc/udev/rules.d/99-streamdock.rules              USB device permissions
#   ~/.local/share/applications/streamdock.desktop     application launcher
#   ~/.local/share/icons/.../streamdock.svg            launcher icon
#
# Run from anywhere; the project root is derived from this script's location.
# Requires sudo for the udev rule only.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRIB_DIR="$PROJECT_DIR/contrib"

APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

# ── Preflight checks ────────────────────────────────────────────────────────

# Accept either layout: the docs create venv/, older installs used .venv/.
VENV_PYTHON=""
for candidate in "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/venv/bin/python"; do
    if [ -x "$candidate" ]; then
        VENV_PYTHON="$candidate"
        break
    fi
done

if [ -z "$VENV_PYTHON" ]; then
    echo "Error: No virtual environment found at $PROJECT_DIR/.venv or $PROJECT_DIR/venv"
    echo ""
    echo "Create one first:"
    echo "  python -m venv --system-site-packages venv"
    echo "  venv/bin/pip install -r requirements.txt"
    exit 1
fi

echo "Installing StreamDock system integration"
echo "  Project : $PROJECT_DIR"
echo "  Python  : $VENV_PYTHON"
echo "  User    : $(whoami)"
echo ""

# ── Step 1: udev rule ───────────────────────────────────────────────────────

echo "[1/4] Installing udev rule → /etc/udev/rules.d/99-streamdock.rules"
sudo install -m 644 "$CONTRIB_DIR/99-streamdock.rules" \
    /etc/udev/rules.d/99-streamdock.rules
sudo udevadm control --reload-rules
# Trigger only the StreamDock device nodes — avoids re-processing everything
sudo udevadm trigger --attr-match=idVendor=6603

# ── Step 2: desktop entry ───────────────────────────────────────────────────

echo "[2/4] Installing launcher → $APPLICATIONS_DIR/streamdock.desktop"
mkdir -p "$APPLICATIONS_DIR"
sed -e "s|@@PROJECT_DIR@@|$PROJECT_DIR|g" \
    -e "s|@@PYTHON@@|$VENV_PYTHON|g" \
    "$CONTRIB_DIR/streamdock.desktop.template" \
    > "$APPLICATIONS_DIR/streamdock.desktop"
chmod 644 "$APPLICATIONS_DIR/streamdock.desktop"

echo "[3/4] Installing icon → $ICON_DIR/streamdock.svg"
mkdir -p "$ICON_DIR"
install -m 644 "$CONTRIB_DIR/streamdock.svg" "$ICON_DIR/streamdock.svg"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

# ── Step 4: plugdev group membership ────────────────────────────────────────

echo "[4/4] Checking plugdev group membership..."
if id -nG | grep -qw plugdev; then
    echo "       ✓ $(whoami) is already in the plugdev group"
else
    echo "       ⚠  $(whoami) is not in the plugdev group."
    echo "          Add with:  sudo usermod -aG plugdev $(whoami)"
    echo "          Then log out and back in for it to take effect."
fi

# ── Migration note ──────────────────────────────────────────────────────────

if [ -f "$HOME/.config/systemd/user/streamdock.service" ]; then
    echo ""
    echo "⚠  A streamdock.service from a previous version is still installed."
    echo "   It would fight the application for the device. Remove it with:"
    echo "     ./scripts/uninstall.sh"
    echo "   then re-run this script."
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo "✓ Installation complete."
echo ""
echo "Launch StreamDock from your application menu, or run:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py"
echo ""
echo "To run the controller without the GUI:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py --headless"
