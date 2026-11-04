#!/usr/bin/env bash
# scripts/streamdock-launcher.sh — Start StreamDock from a menu or autostart entry.
#
# A desktop launcher gets neither the shell's PATH nor an activated venv, and
# hides anything printed on failure. This script picks the right interpreter,
# keeps a log, and reports a failed start as a desktop notification.
#
# Interpreter, first found: $STREAMDOCK_PYTHON, <project>/.venv, <project>/venv,
# python3 on PATH. Arguments are passed to main.py (e.g. --minimized).
# Log: ${XDG_STATE_HOME:-~/.local/state}/streamdock/launcher.log

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

PYTHON="${STREAMDOCK_PYTHON:-}"
if [ -z "$PYTHON" ]; then
    for candidate in "$PROJECT_DIR/.venv/bin/python" "$PROJECT_DIR/venv/bin/python"; do
        if [ -x "$candidate" ]; then
            PYTHON="$candidate"
            break
        fi
    done
fi
PYTHON="${PYTHON:-python3}"

# Menu launches can miss PATH entries a login shell adds, where tools such
# as kdotool are often installed.
for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    case ":$PATH:" in
        *":$dir:"*) ;;
        *) [ -d "$dir" ] && PATH="$PATH:$dir" ;;
    esac
done
export PATH

LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/streamdock"
LOG_FILE="$LOG_DIR/launcher.log"
mkdir -p "$LOG_DIR"
# Keep one previous run for comparison.
[ -f "$LOG_FILE" ] && mv -f "$LOG_FILE" "$LOG_FILE.1"

{
    echo "$(date '+%F %T') starting: $PYTHON $PROJECT_DIR/src/main.py $*"
} >"$LOG_FILE"

cd "$PROJECT_DIR/src" || exit 1
"$PYTHON" "$PROJECT_DIR/src/main.py" "$@" >>"$LOG_FILE" 2>&1
status=$?

if [ "$status" -ne 0 ]; then
    message="StreamDock exited with code $status. See $LOG_FILE"
    if command -v notify-send >/dev/null 2>&1; then
        notify-send --app-name=StreamDock --icon=streamdock "StreamDock failed to start" "$message"
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title StreamDock --error "$message"
    fi
fi
exit "$status"
