#!/usr/bin/env python3
"""
StreamDock main application with YAML configuration support.
"""
from StreamDock.DeviceManager import DeviceManager
from StreamDock.WindowMonitor import WindowMonitor
from StreamDock.LockMonitor import LockMonitor
from StreamDock.ConfigLoader import ConfigLoader, ConfigValidationError
import threading
import time
import sys
import os


def main():
    """Main application entry point."""
    
    # Parse command-line arguments for config file
    config_file = 'config.yml'
    
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        # Use config.yml in the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_file = os.path.join(script_dir, 'config.yml')
    
    # Load configuration
    try:
        config_loader = ConfigLoader(config_file)
        config_loader.load()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ConfigValidationError as e:
        print(f"Configuration validation error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading configuration: {e}")
        sys.exit(1)
    
    # Initialize device manager
    deviceManager = DeviceManager()
    streamdocks = deviceManager.enumerate()
    
    # Start listening thread
    t = threading.Thread(target=deviceManager.listen)
    t.daemon = True
    t.start()
    
    if len(streamdocks) == 0:
        print("No Stream Dock devices found. Please connect a device and try again.")
        sys.exit(1)
    
    for device in streamdocks:
        device.open()
        device.init()

        # device.set_touchscreen_image("/home/zrubi/Development_Private/StreamDock/img/zrubi_logo.jpg")

        # Initialize window monitor
        window_monitor = WindowMonitor(poll_interval=0.5)
        
        # Apply configuration to device
        try:
            default_layout, all_layouts = config_loader.apply(device, window_monitor)
            
            # Initialize lock monitor (from config setting) with default layout, all layouts, and window monitor
            lock_monitor = LockMonitor(
                device, 
                enabled=config_loader.lock_monitor_enabled, 
                current_layout=default_layout,
                all_layouts=all_layouts,
                window_monitor=window_monitor if config_loader.config.get('windows_rules') else None
            )
            
            # Apply the default layout
            default_layout.apply()
            
            # Start window monitoring if rules were configured
            if config_loader.config.get('windows_rules'):
                window_monitor.start()
            
            # Start lock monitoring
            lock_monitor.start()
            
        except ConfigValidationError as e:
            print(f"Error applying configuration: {e}")
            device.close()
            sys.exit(1)
        except Exception as e:
            print(f"Error applying configuration: {e}")
            device.close()
            sys.exit(1)
        
        # Keep the program running to process key events
        print("\nStreamDock is ready. Press Ctrl+C to exit.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            if config_loader.config.get('windows_rules'):
                window_monitor.stop()
            lock_monitor.stop()
            device.close()

if __name__ == "__main__":
    main()
