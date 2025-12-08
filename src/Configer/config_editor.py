#!/usr/bin/env python3
"""
StreamDock Configuration Editor
A GUI tool for creating and editing StreamDock configurations

Usage:
    python config_editor.py [config_file.yml]
"""

import sys

from config_editor_main import ConfigEditorMainWindow
from PyQt6.QtWidgets import QApplication


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName("StreamDock Configuration Editor")
    app.setOrganizationName("StreamDock")

    window = ConfigEditorMainWindow()

    # If a config file is provided as argument, load it
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
        window.load_config(config_file)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
