#!/usr/bin/env bash
# scripts/install.sh — Install StreamDock system integration files.
#
# Sets up:
#   /etc/udev/rules.d/70-streamdock.rules              USB device permissions
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

echo "[1/3] Installing udev rule → /etc/udev/rules.d/70-streamdock.rules"
sudo install -m 644 "$CONTRIB_DIR/70-streamdock.rules" \
    /etc/udev/rules.d/70-streamdock.rules
# Earlier versions installed the rule as 99-streamdock.rules, which runs too
# late for its uaccess tag to take effect and relied on a plugdev group.
if [ -e /etc/udev/rules.d/99-streamdock.rules ]; then
    echo "       Removing the old /etc/udev/rules.d/99-streamdock.rules"
    echo "       (copy any lines you added to it into 70-streamdock.rules)"
    sudo rm -f /etc/udev/rules.d/99-streamdock.rules
fi
sudo udevadm control --reload-rules
# Trigger only the StreamDock device nodes — avoids re-processing everything
sudo udevadm trigger --attr-match=idVendor=6603

# ── Step 2: desktop entry ───────────────────────────────────────────────────

echo "[2/3] Installing launcher → $APPLICATIONS_DIR/streamdock.desktop"
mkdir -p "$APPLICATIONS_DIR"

# The template wraps each Exec argument in double quotes. Inside them the
# Desktop Entry spec wants \ " ` $ backslash-escaped, and that backslash is
# itself string-escaped once more (so a literal \ becomes four); % is doubled
# so it is not read as a field code.
desktop_quoted_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\\\\\/g' -e 's/["`$]/\\\\&/g' -e 's/%/%%/g'
}

# Make a value safe as the replacement of a sed s|...|...| command.
sed_replacement_escape() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

EXEC_PROJECT_DIR="$(sed_replacement_escape "$(desktop_quoted_escape "$PROJECT_DIR")")"
EXEC_PYTHON="$(sed_replacement_escape "$(desktop_quoted_escape "$VENV_PYTHON")")"
sed -e "s|@@PROJECT_DIR@@|$EXEC_PROJECT_DIR|g" \
    -e "s|@@PYTHON@@|$EXEC_PYTHON|g" \
    "$CONTRIB_DIR/streamdock.desktop.template" \
    > "$APPLICATIONS_DIR/streamdock.desktop"
chmod 644 "$APPLICATIONS_DIR/streamdock.desktop"

echo "[3/3] Installing icon → $ICON_DIR/streamdock.svg"
mkdir -p "$ICON_DIR"
install -m 644 "$CONTRIB_DIR/streamdock.svg" "$ICON_DIR/streamdock.svg"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

# ── Done ────────────────────────────────────────────────────────────────────

echo ""
echo "✓ Installation complete."
echo ""
echo "The device is now accessible to whoever is logged in at the local seat;"
echo "no group membership is needed. Replug the deck if it was already connected."
echo ""
echo "Launch StreamDock from your application menu, or run:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py"
echo ""
echo "To run the controller without the GUI:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py --headless"
