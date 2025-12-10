#!/usr/bin/env python3
"""
Helper script to simulate window focus changes for StreamDock.
Usage:
    ./simulate_window.py "Application Name"
    ./simulate_window.py "Window Title|Application Class"
"""
import sys
import os

SIMULATION_FILE = "/tmp/streamdock_fake_window"

def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <Window Info>")
        print("Example: ./simulate_window.py Firefox")
        print("Example: ./simulate_window.py 'New Tab - Firefox|Firefox'")
        sys.exit(1)

    window_info = sys.argv[1]
    
    try:
        with open(SIMULATION_FILE, "w") as f:
            f.write(window_info)
        print(f"Set active window to: '{window_info}'")
    except Exception as e:
        print(f"Error writing to simulation file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
