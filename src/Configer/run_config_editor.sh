#!/bin/bash
# Quick start script for StreamDock Configuration Editor

# Check if PyQt6 is installed
python3 -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Error: PyQt6 is not installed"
    echo "Install it with: pip install PyQt6"
    exit 1
fi

# Check if Pillow is installed
python3 -c "import PIL" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Error: Pillow is not installed"
    echo "Install it with: pip install Pillow"
    exit 1
fi

# Run the configuration editor
python3 config_editor.py "$@"
