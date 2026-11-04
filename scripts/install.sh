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
#
# Options:
#   --python PATH   Interpreter to launch with, e.g. --python "$(command -v python)"
#                   from the shell where `python src/main.py` works. Default:
#                   the project's .venv or venv, else python3 on PATH.
#   --autostart     Also start StreamDock minimized at login
#                   (~/.config/autostart/streamdock.desktop)
#   --no-udev       Skip the udev rule (no sudo); install only the launcher

set -euo pipefail

usage() {
    sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

PYTHON_ARG=""
AUTOSTART=0
INSTALL_UDEV=1
while [ $# -gt 0 ]; do
    case "$1" in
        --python)    PYTHON_ARG="${2:?--python needs a path}"; shift 2 ;;
        --python=*) PYTHON_ARG="${1#--python=}"; shift ;;
        --autostart) AUTOSTART=1; shift ;;
        --no-udev)   INSTALL_UDEV=0; shift ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTRIB_DIR="$PROJECT_DIR/contrib"

APPLICATIONS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

# ── Preflight checks ────────────────────────────────────────────────────────

# A menu launcher does not get the shell's PATH or an activated venv/pyenv, so
# the interpreter is resolved here and written into the launcher as a full path.
CANDIDATE="$PYTHON_ARG"
if [ -z "$CANDIDATE" ]; then
    # Accept either layout: the docs create venv/, older installs used .venv/.
    for candidate in "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/venv/bin/python"; do
        if [ -x "$candidate" ]; then
            CANDIDATE="$candidate"
            break
        fi
    done
fi
CANDIDATE="${CANDIDATE:-python3}"

# sys.executable turns a pyenv shim or bare command name into the real
# interpreter, and keeps a venv's own bin/python (so its packages still load).
if ! VENV_PYTHON="$("$CANDIDATE" -c 'import sys; print(sys.executable)' 2>/dev/null)" \
        || [ -z "$VENV_PYTHON" ]; then
    echo "Error: cannot run Python interpreter '$CANDIDATE'" >&2
    exit 1
fi

if ! "$VENV_PYTHON" -c 'import PyQt6, yaml, PIL, pyudev, cairosvg' 2>/dev/null; then
    echo "Error: $VENV_PYTHON is missing StreamDock's dependencies." >&2
    echo "" >&2
    echo "If 'python src/main.py' works in your terminal, re-run this from there with:" >&2
    echo "  $0 --python \"\$(command -v python)\"" >&2
    echo "" >&2
    echo "Or create a venv in the project first:" >&2
    echo "  python -m venv --system-site-packages venv" >&2
    echo "  venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

echo "Installing StreamDock system integration"
echo "  Project : $PROJECT_DIR"
echo "  Python  : $VENV_PYTHON"
echo "  User    : $(whoami)"
echo ""

# ── Step 1: udev rule ───────────────────────────────────────────────────────

if [ "$INSTALL_UDEV" -eq 1 ]; then
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
else
    echo "[1/3] Skipping udev rule (--no-udev)"
fi

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

# write_entry DEST EXTRA_ARGS
write_entry() {
    sed -e "s|@@PROJECT_DIR@@|$EXEC_PROJECT_DIR|g" \
        -e "s|@@PYTHON@@|$EXEC_PYTHON|g" \
        -e "s|@@ARGS@@|$2|g" \
        "$CONTRIB_DIR/streamdock.desktop.template" > "$1"
    chmod 644 "$1"
}

chmod +x "$SCRIPT_DIR/streamdock-launcher.sh"
write_entry "$APPLICATIONS_DIR/streamdock.desktop" ""

AUTOSTART_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/streamdock.desktop"
if [ "$AUTOSTART" -eq 1 ]; then
    echo "       Autostart (minimized) → $AUTOSTART_FILE"
    mkdir -p "$(dirname "$AUTOSTART_FILE")"
    write_entry "$AUTOSTART_FILE" " --minimized"
fi

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
if [ "$INSTALL_UDEV" -eq 1 ]; then
    echo "The device is now accessible to whoever is logged in at the local seat;"
    echo "no group membership is needed. Replug the deck if it was already connected."
    echo ""
fi
echo "Launch StreamDock from your application menu (output goes to"
echo "  ${XDG_STATE_HOME:-$HOME/.local/state}/streamdock/launcher.log), or run:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py"
echo ""
echo "To run the controller without the GUI:"
echo "  $VENV_PYTHON $PROJECT_DIR/src/main.py --headless"
